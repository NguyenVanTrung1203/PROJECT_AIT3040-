"""Fixture-only trusted replay to encounter boundary; not a production provider."""
from dataclasses import dataclass
from itertools import combinations
from types import MappingProxyType
import hashlib
import json
import math
import threading
import uuid
import time

import numpy as np

from backend.app.replay_api import ReplayAPI, ReplaySource, CreateSessionRequest, ControlRequest
from scripts.contract_identity_reference import canonical_vessel_id, pair_and_online_roles, encounter_id
from src.data.track_buffer import validate_track_snapshot_runtime

SOURCE = 's5-01-synthetic-denmark-v1'
START = '2024-11-01T00:00:00Z'
END = '2024-11-01T00:21:00Z'
FEATURES = ('own_relative_east_nm', 'own_relative_north_nm', 'east_velocity_kn', 'north_velocity_kn')


def _events():
    """Deterministic synthetic observations, explicitly not real AIS."""
    result = []
    # A/B approach; C/D diverge. E starts late to exercise unavailable coverage.
    ships = [('a', 55.70, 12.45, 90, 0), ('b', 55.70, 12.55, 270, 0),
             ('c', 55.75, 12.50, 0, 0), ('d', 55.65, 12.50, 180, 0),
             ('e', 55.72, 12.50, 0, 5)]
    for minute in range(21):
        for name, lat, lon, cog, first in ships:
            if minute < first:
                continue
            delta = (minute - first) * 0.1
            angle = math.radians(cog)
            result.append({'timestamp_utc': f'2024-11-01T00:{minute:02d}:00Z',
                'vessel_id': f'simulated:s5-01:{name}', 'mmsi': None,
                'source_type': 'SYNTHETIC_AIS', 'is_simulated': True,
                'latitude': lat + delta * math.cos(angle) / 60,
                'longitude': lon + delta * math.sin(angle) / (60 * math.cos(math.radians(lat))),
                'sog_kn': 6.0, 'cog_deg': float(cog),
                'provenance': {'source_file': SOURCE, 'source_row': len(result) + 1}})
    return result


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class Snapshot:
    session_id: str
    session_version: int
    snapshot_id: str
    anchor_utc: str
    source_identity: str
    fixture_sha256: str
    tracks: tuple
    evaluation_generation: int | None = None


@dataclass(frozen=True)
class Candidate:
    pair_id: str
    vessels: tuple
    session_id: str
    session_version: int
    snapshot_id: str
    anchor_utc: str
    unavailable_reason: str | None


@dataclass(frozen=True)
class Coverage:
    expected: int
    evaluated: int
    eligible: int
    unavailable: int
    candidates: tuple


@dataclass(frozen=True)
class Encounter:
    candidate: Candidate
    encounter_id: str
    tracks: tuple


@dataclass(frozen=True)
class Features:
    encounter: Encounter
    history: np.ndarray
    anchors_en: np.ndarray
    origin_lat_lon: tuple
    sog_cog: tuple
    frame: str = 'common_EN_origin_A_t-9'
    feature_order: tuple = FEATURES


def candidate_ids(ids, max_vessels):
    if isinstance(max_vessels, bool) or not isinstance(max_vessels, int) or max_vessels < 2:
        raise ValueError('invalid vessel bound')
    if len(ids) > max_vessels:
        raise ValueError('VESSEL_BOUND_EXCEEDED')
    canonical = [canonical_vessel_id(x, {'simulated'}) for x in ids]
    if len(canonical) != len(set(canonical)):
        raise ValueError('DUPLICATE_VESSEL_ID')
    canonical.sort(key=lambda x: x.encode('utf-8'))
    return tuple(pair_and_online_roles(a, b, {'simulated'}) for a, b in combinations(canonical, 2))


class FixtureProvider:
    """Owns replay and lock. No external replay, event, source, or trust flag accepted."""
    def __init__(self, max_vessels, *, backend_replay=False):
        candidate_ids((), max_vessels)
        self._max_vessels = max_vessels
        self._lock = threading.RLock()
        self._tick = 0.0
        events = _events()
        self._digest = hashlib.sha256(json.dumps(events, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        sources = [ReplaySource(SOURCE, START, END, lambda: _events())]
        if backend_replay:
            from backend.app.replay_api import demo_source
            sources.append(demo_source())
        self._api = ReplayAPI(sources, monotonic=time.monotonic if backend_replay else lambda: self._tick)
        self._session = None
        self._snapshot = None
        self._candidates = ()
        # Features are immutable, provider-issued values bound to the current
        # snapshot and candidate. The cache is discarded whenever that binding
        # changes and is used only to pass the exact same object to inference.
        self._issued_features = {}
        self._evaluation_leases = {}

    def create(self, start_time=START):
        with self._lock:
            self._session = self._api.create_session(CreateSessionRequest(source_id=SOURCE, start_time=start_time))
            self._snapshot = None
            self._candidates = ()
            self._issued_features = {}
            self._evaluation_leases = {}
            return self._session

    def control(self, action, target_time=None):
        with self._lock:
            if self._session is None:
                raise ValueError('SESSION_UNAVAILABLE')
            args = {'action': action, 'expected_version': self._session.version}
            if target_time is not None:
                args['target_time'] = target_time
            key = str(uuid.uuid4()) if action in ('SEEK', 'RESET') else None
            self._session = self._api.control(self._session.session_id, ControlRequest(**args), key)
            self._snapshot = None
            self._candidates = ()
            self._issued_features = {}
            self._evaluation_leases = {}
            return self._session

    def advance(self, seconds):
        with self._lock:
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError('invalid clock increment')
            self._tick += seconds
            self._session = self._api.get_session(self._session.session_id)
            self._snapshot = None
            self._candidates = ()
            self._issued_features = {}
            self._evaluation_leases = {}
            return self._session

    def snapshot(self):
        with self._lock:
            if self._session is None:
                raise ValueError('SESSION_UNAVAILABLE')
            before = self._api.get_session(self._session.session_id)
            page = self._api.list_tracks(before.session_id, limit=self._max_vessels + 1, offset=0, snapshot_id=None)
            after = self._api.get_session(before.session_id)
            if before != after or page['simulation_time'] != before.simulation_time:
                raise ValueError('SESSION_CHANGED')
            if page['total'] > self._max_vessels:
                raise ValueError('VESSEL_BOUND_EXCEEDED')
            ids = [t['vessel_id'] for t in page['items']]
            candidate_ids(ids, self._max_vessels)
            for track in page['items']:
                validate_track_snapshot_runtime(track, simulation_clock=before.simulation_time)
                if track['source_type'] != 'SYNTHETIC_AIS' or track['anchor_timestamp'] != before.simulation_time:
                    raise ValueError('SOURCE_OR_ANCHOR_MISMATCH')
            self._session = after
            self._snapshot = Snapshot(before.session_id, before.version, page['snapshot_id'], before.simulation_time,
                                      SOURCE, self._digest, tuple(_freeze(t) for t in page['items']))
            self._candidates = ()
            self._prune_issued_features()
            return self._snapshot

    def _prune_issued_features(self):
        retained = {entry[0].snapshot_id for entry in self._evaluation_leases.values()}
        if self._snapshot is not None:
            retained.add(self._snapshot.snapshot_id)
        self._issued_features = {key: value for key, value in self._issued_features.items()
                                 if key[2] in retained}

    def evaluation_snapshot(self, session_id, anchor, expected_generation):
        """Issue an immutable minute-grid snapshot lease while PLAYING.

        Clock progression is allowed by the lease. Any replay control increments
        the session version (or creates a successor session) and invalidates it.
        """
        with self._lock:
            if self._session is None or self._session.session_id != session_id:
                raise ValueError('STALE_EVALUATION_SESSION')
            before = self._api.get_session(session_id)
            if (before.status != 'PLAYING' or before.version != expected_generation or
                    before.source_id != SOURCE):
                raise ValueError('STALE_EVALUATION_GENERATION')
            view, raw_tracks = self._api.evaluation_tracks(session_id, anchor)
            after = self._api.get_session(session_id)
            if (view.session_id, view.version, view.status, view.source_id) != (
                    after.session_id, after.version, after.status, after.source_id) or after.version != expected_generation:
                raise ValueError('STALE_EVALUATION_GENERATION')
            if len(raw_tracks) > self._max_vessels:
                raise ValueError('VESSEL_BOUND_EXCEEDED')
            for track in raw_tracks:
                validate_track_snapshot_runtime(track, simulation_clock=anchor)
                if track['source_type'] != 'SYNTHETIC_AIS' or track['anchor_timestamp'] != anchor:
                    raise ValueError('SOURCE_OR_ANCHOR_MISMATCH')
            tracks = tuple(_freeze(track) for track in raw_tracks)
            snapshot = Snapshot(session_id, after.version, str(uuid.uuid4()), anchor, SOURCE,
                                self._digest, tracks, after.version)
            track_map = {track['vessel_id']: track for track in tracks}
            pairs = candidate_ids(list(track_map), self._max_vessels)
            candidates = tuple(Candidate(pair, vessels, session_id, after.version,
                snapshot.snapshot_id, anchor,
                None if all(track_map[v]['data_status'] == 'VALID' for v in vessels)
                else 'INSUFFICIENT_OR_INVALID_HISTORY') for pair, vessels in pairs)
            eligible = sum(candidate.unavailable_reason is None for candidate in candidates)
            coverage = Coverage(len(candidates), len(candidates), eligible,
                                len(candidates) - eligible, candidates)
            self._session = after
            self._evaluation_leases[id(snapshot)] = (snapshot, coverage)
            return snapshot, coverage

    def release_evaluation_snapshot(self, snapshot):
        with self._lock:
            entry = self._evaluation_leases.pop(id(snapshot), None)
            if entry is not None and entry[0] is snapshot:
                for key in [key for key in self._issued_features
                            if key[0] == snapshot.session_id and key[1] == snapshot.session_version
                            and key[2] == snapshot.snapshot_id]:
                    self._issued_features.pop(key, None)

    def _check(self, snapshot):
        lease = self._evaluation_leases.get(id(snapshot)) if snapshot is not None else None
        if lease is not None:
            if lease[0] is not snapshot or snapshot.evaluation_generation != snapshot.session_version:
                raise ValueError('UNTRUSTED_EVALUATION_LEASE')
            view = self._api.get_session(snapshot.session_id)
            if (view.session_id, view.version, view.status, view.source_id) != (
                    snapshot.session_id, snapshot.evaluation_generation, 'PLAYING', snapshot.source_identity):
                raise ValueError('STALE_EVALUATION_LEASE')
            return
        if snapshot is not self._snapshot or snapshot is None:
            raise ValueError('UNTRUSTED_OR_STALE_SNAPSHOT')
        view = self._api.get_session(snapshot.session_id)
        if (view.session_id, view.version, view.simulation_time, view.source_id) != (snapshot.session_id, snapshot.session_version, snapshot.anchor_utc, snapshot.source_identity):
            raise ValueError('STALE_SNAPSHOT')

    def candidates(self, snapshot):
        with self._lock:
            self._check(snapshot)
            lease = self._evaluation_leases.get(id(snapshot))
            if lease is not None:
                return lease[1]
            tracks = {t['vessel_id']: t for t in snapshot.tracks}
            pairs = candidate_ids(list(tracks), self._max_vessels)
            rows = []
            for pair, ids in pairs:
                reason = None if all(tracks[v]['data_status'] == 'VALID' for v in ids) else 'INSUFFICIENT_OR_INVALID_HISTORY'
                rows.append(Candidate(pair, ids, snapshot.session_id, snapshot.session_version, snapshot.snapshot_id, snapshot.anchor_utc, reason))
            self._check(snapshot)
            self._candidates = tuple(rows)
            self._prune_issued_features()
            eligible = sum(c.unavailable_reason is None for c in rows)
            return Coverage(len(pairs), len(rows), eligible, len(rows) - eligible, self._candidates)

    def encounter(self, snapshot, candidate):
        with self._lock:
            self._check(snapshot)
            lease = self._evaluation_leases.get(id(snapshot))
            candidates = lease[1].candidates if lease is not None else self._candidates
            if not any(candidate is c for c in candidates):
                raise ValueError('UNTRUSTED_CANDIDATE')
            if candidate.unavailable_reason:
                return None, candidate.unavailable_reason
            tracks = {t['vessel_id']: t for t in snapshot.tracks}
            selected = tuple(tracks[v] for v in candidate.vessels)
            if any(t['source_type'] != 'SYNTHETIC_AIS' for t in selected):
                return None, 'MIXED_OR_UNTRUSTED_SOURCE'
            self._check(snapshot)
            return Encounter(candidate, encounter_id(snapshot.session_id, candidate.pair_id, snapshot.anchor_utc), selected), None

    def features(self, snapshot, encounter):
        with self._lock:
            self._check(snapshot)
            candidate = encounter.candidate
            rebuilt, reason = self.encounter(snapshot, candidate)
            if reason or rebuilt != encounter:
                raise ValueError('UNTRUSTED_ENCOUNTER')
            histories = [t['history'] for t in encounter.tracks]
            lat0, lon0 = histories[0][0]['latitude'], histories[0][0]['longitude']
            points = np.asarray([[[p['latitude'], p['longitude'], p['sog_kn'], p['cog_deg']] for p in h] for h in histories], dtype=np.float64)
            if points.shape != (2, 10, 4) or not np.isfinite(points).all():
                raise ValueError('INVALID_FEATURES')
            en = np.stack(((points[:, :, 1] - lon0) * 60 * math.cos(math.radians(lat0)), (points[:, :, 0] - lat0) * 60), axis=-1)
            anchors = en[:, -1, :].copy()
            angles = np.deg2rad(points[:, :, 3])
            velocities = np.stack((points[:, :, 2] * np.sin(angles), points[:, :, 2] * np.cos(angles)), axis=-1)
            x = np.concatenate((en - anchors[:, None, :], velocities), axis=-1).astype(np.float32)
            if not np.isfinite(x).all() or not np.isfinite(anchors).all():
                raise ValueError('INVALID_FEATURES')
            # bytes-backed arrays cannot be made writeable by consumers.
            x = np.frombuffer(x.tobytes(), dtype=np.float32).reshape(2, 10, 4)
            anchors = np.frombuffer(anchors.tobytes(), dtype=np.float64).reshape(2, 2)
            self._check(snapshot)
            value = Features(encounter, x, anchors, (lat0, lon0), tuple(tuple((p['sog_kn'], p['cog_deg']) for p in h) for h in histories))
            key = self._features_key(snapshot, encounter)
            self._issued_features[key] = value
            return value

    @staticmethod
    def _features_key(snapshot, encounter):
        candidate = encounter.candidate
        return (snapshot.session_id, snapshot.session_version, snapshot.snapshot_id,
                snapshot.anchor_utc, snapshot.source_identity, snapshot.fixture_sha256,
                id(candidate), candidate.pair_id, candidate.vessels, encounter.encounter_id)

    def is_issued_features(self, snapshot, encounter, features):
        """Accept only the exact immutable feature object issued for this binding."""
        with self._lock:
            self._check(snapshot)
            if (not isinstance(encounter, Encounter) or type(features) is not Features or
                    features.encounter.candidate is not encounter.candidate or
                    features.encounter.encounter_id != encounter.encounter_id or
                    features.encounter.tracks != encounter.tracks):
                return False
            return self._issued_features.get(self._features_key(snapshot, encounter)) is features
