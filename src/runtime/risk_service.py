"""Process-local fixture risk/alert harness; no public HTTP or real-AIS trust."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
import threading
import uuid

import numpy as np

from scripts.contract_identity_reference import encounter_id, pair_and_online_roles
from src.risk.adapter import ref, verify_reference
from src.runtime.config import resolve_threshold, LOCK_ID
from src.runtime.m5a_service import M5aRuntime, RuntimeUnavailable
from src.runtime.trusted_fixture import FixtureProvider


def _utc_plus(value, minutes):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00')) + timedelta(minutes=minutes)
    return dt.isoformat().replace('+00:00', 'Z')


def _decision(score, threshold):
    if threshold is None:
        return None
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in (score, threshold)):
        raise RuntimeUnavailable('DECISION_INPUT_INVALID')
    return score >= threshold


def _risk_components(features, forecast):
    """Feed only trusted causal history and forecast to the unchanged V4 reference."""
    verify_reference()
    history = features.history.astype(np.float64)
    anchors = features.anchors_en
    positions = history[:, :, :2] + anchors[:, None, :]
    velocity = history[:, :, 2:]
    sogcog = np.asarray(features.sog_cog, dtype=np.float64)
    predictions = np.stack([v.en for v in forecast.vessels])
    if (history.shape != (2, 10, 4) or anchors.shape != (2, 2) or
            sogcog.shape != (2, 10, 2) or predictions.shape != (2, 15, 2) or
            not all(np.isfinite(z).all() for z in (history, anchors, sogcog, predictions))):
        raise RuntimeUnavailable('RISK_INPUT_INVALID')
    roles, scenes = ref.infer_roles(positions[None], velocity[None])
    rule = ref.rule_component(sogcog[None, :, :, 1], sogcog[None, :, :, 0], roles)
    scores, details = ref.calculate({'last': anchors[None], 'vel': velocity[None], 'rule': rule}, predictions[None])
    values = [float(scores[k][0]) for k in ('Current-CPA', 'GRU-P-CPA', 'CC-DRI')] + [float(rule[0])]
    if any(not math.isfinite(x) or not 0 <= x <= 1 for x in values):
        raise RuntimeUnavailable('RISK_SCORE_INVALID')
    low_velocity = float(np.sum((velocity[1, -1] - velocity[0, -1]) ** 2)) <= 1e-9
    return {'current_dcpa_nm': float(details['dcpa_nm'][0]),
            'current_tcpa_minutes': None if low_velocity else float(details['tcpa_raw_min'][0]),
            'current_tcpa_clipped_minutes': None if low_velocity else float(details['tcpa_clipped_min'][0]),
            'current_cpa_status': 'UNDEFINED_LOW_RELATIVE_VELOCITY' if low_velocity else 'AVAILABLE',
            'predicted_min_distance_nm': float(details['pred_dmin_nm'][0]),
            'predicted_closest_time_minutes': int(details['pred_tmin'][0]),
            'predicted_cpa_status': 'AVAILABLE', 'current_cpa_score': values[0],
            'predicted_cpa_score': values[1], 'risk_score': values[2], 'rule_score': values[3],
            'scene': str(scenes[0]), 'role': str(roles[0])}


def _forecast_wire(features, result):
    en = np.stack([v.en for v in result.vessels])
    geographic = all(v.lat_lon is not None for v in result.vessels)
    return {'schema_version': '1.0.0', 'forecast_timestamps': list(result.timestamps),
            'forecast_displacement_en_nm': (en - features.anchors_en[:, None, :]).tolist(),
            'forecast_common_en_nm': en.tolist(),
            'forecast_lat_lon': np.stack([v.lat_lon for v in result.vessels]).tolist() if geographic else None,
            'geographic_availability': 'SIMULATED' if geographic else 'UNAVAILABLE',
            'coordinate_origin': {'origin_latitude': features.origin_lat_lon[0],
                'origin_longitude': features.origin_lat_lon[1], 'origin_timestamp': _utc_plus(result.anchor_utc, -9),
                'origin_vessel_id': result.vessels[0].vessel_id, 'coordinate_method': 'LOCAL_DEGREES_COS_LAT0',
                'coordinate_unit': 'nautical_mile', 'coordinate_dtype': 'float64',
                'geographic_mapping_status': 'VERIFIED_SIMULATED' if geographic else 'UNAVAILABLE'},
            'anchor_positions_en_nm': features.anchors_en.tolist()}


class AlertManager:
    """State is process-local; caller owns session/snapshot lock during apply."""
    def __init__(self):
        self._lock = threading.RLock()
        self._open = {}
        self._history = []
        self._latest = {}

    def apply(self, risk):
        key = (risk['replay_session_id'], risk['pair_id'])
        stamp = risk['anchor_timestamp']
        with self._lock:
            if stamp <= self._latest.get(key, ''):
                return
            self._latest[key] = stamp
            prior = self._open.get(key)
            decision = risk['alert_triggered']
            if prior is None and decision is not True:
                return
            if prior is None:
                prior = {'schema_version': '1.0.0', 'alert_id': str(uuid.uuid4()),
                    'replay_session_id': key[0], 'pair_id': key[1],
                    'opened_encounter_id': risk['encounter_id'], 'vessel_ids': list(risk['vessel_ids']),
                    'opened_at': stamp, 'closed_at': None}
                self._open[key] = prior
                self._history.append(prior)
            prior.update({'updated_at': stamp, 'latest_evaluation_timestamp': stamp,
                          'latest_encounter_id': risk['encounter_id']})
            if decision is None:
                prior.update(alert_status='DATA_UNAVAILABLE', status_reason='DATA_UNAVAILABLE', values_are_last_valid=True)
                return
            prior.update({name: risk[name] for name in ('risk_score', 'threshold', 'predicted_min_distance_nm',
                          'predicted_closest_time_minutes', 'current_dcpa_nm', 'current_tcpa_minutes')})
            prior.update(active_model=risk['model_status']['active_model'], values_as_of=stamp,
                         values_are_last_valid=False, status_reason='THRESHOLD_MET' if decision else 'THRESHOLD_NOT_MET',
                         alert_status='ACTIVE' if decision else 'RESOLVED', closed_at=None if decision else stamp)
            if not decision:
                del self._open[key]

    def list(self, session_id):
        with self._lock:
            return deepcopy([a for a in self._history if a['replay_session_id'] == session_id])

    def clone(self):
        cloned = AlertManager()
        with self._lock:
            cloned._open = deepcopy(self._open)
            cloned._history = deepcopy(self._history)
            cloned._latest = deepcopy(self._latest)
        return cloned


@dataclass
class BatchStage:
    owner: object
    harness: object
    base_revision: int
    results: list = field(default_factory=list)
    closed: bool = False

    def evaluate(self, snapshot, candidate, request_id, token):
        if self.closed:
            raise RuntimeUnavailable('BATCH_STAGE_CLOSED')
        result = self.harness.evaluate(snapshot, candidate, request_id, batch_token=token)
        self.results.append(deepcopy(result))
        return result


class FixtureRiskHarness:
    """Evaluate only a candidate issued by the same provider as the M5a service."""
    def __init__(self, provider, model):
        if type(provider) is not FixtureProvider or type(model) is not M5aRuntime or model._provider is not provider:
            raise RuntimeUnavailable('PROVIDER_MISMATCH')
        self._provider, self._model = provider, model
        self._alerts = AlertManager()
        self._cache = {}
        self._requests = {}
        self._lock = threading.RLock()
        self._evaluation_lock = threading.RLock()
        self._state_revision = 0

    def evaluate(self, snapshot, candidate, request_id, *, batch_token=None):
        # Serialise fixture evaluations for idempotency without holding the replay lock.
        with self._evaluation_lock:
            return self._evaluate(snapshot, candidate, request_id, batch_token=batch_token)

    def _evaluate(self, snapshot, candidate, request_id, *, batch_token=None):
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            raise RuntimeUnavailable('INVALID_REQUEST_ID')
        try:
            with self._provider._lock:
                encounter, reason = self._provider.encounter(snapshot, candidate)
                if (candidate.pair_id, candidate.vessels) != pair_and_online_roles(*candidate.vessels, {'simulated'}):
                    raise ValueError('pair mismatch')
                expected_encounter = encounter_id(snapshot.session_id, candidate.pair_id, snapshot.anchor_utc)
                identity = (snapshot.session_id, snapshot.session_version, snapshot.snapshot_id,
                            snapshot.anchor_utc, candidate.pair_id, expected_encounter)
        except (ValueError, AttributeError, TypeError) as exc:
            raise RuntimeUnavailable('UNTRUSTED_INPUT') from exc
        # Same encounter ID at a different snapshot is an identity conflict, not a cache hit.
        with self._lock:
            old = self._requests.get((snapshot.session_id, request_id))
            if old is not None and old != identity:
                raise RuntimeUnavailable('REQUEST_ID_CONFLICT')
            stored = self._cache.get(expected_encounter)
            if stored is not None and stored[0] != identity:
                raise RuntimeUnavailable('ENCOUNTER_SNAPSHOT_CONFLICT')
        result = None
        features = None
        if reason is None:
            features = self._provider.features(snapshot, encounter)
            try:
                if batch_token is None:
                    result = self._model.predict(snapshot, candidate, features)
                else:
                    result = self._model.predict(snapshot, candidate, features, batch_token=batch_token)
            except RuntimeUnavailable as exc:
                if str(exc) != 'ARTIFACT_INTEGRITY_FAILURE':
                    raise
                reason = 'ARTIFACT_INTEGRITY_FAILURE'
            if result is not None:
                if (result.session_id, result.session_version, result.snapshot_id, result.anchor_utc,
                    result.pair_id, result.encounter_id) != identity or result.lock_id != LOCK_ID:
                    raise RuntimeUnavailable('FORECAST_BINDING_MISMATCH')
                if result.timestamps != tuple(_utc_plus(snapshot.anchor_utc, i) for i in range(1, 16)):
                    raise RuntimeUnavailable('FORECAST_TIME_MISMATCH')
                if tuple(v.vessel_id for v in result.vessels) != candidate.vessels:
                    raise RuntimeUnavailable('FORECAST_VESSEL_MISMATCH')
                if result.status != 'AVAILABLE' or any(v.qc_status != 'PASS' or v.en is None for v in result.vessels):
                    reason = 'FORECAST_UNAVAILABLE'
                elif len({v.active_model for v in result.vessels}) != 1 or result.vessels[0].active_model not in ('M5a', 'CV'):
                    reason = 'MIXED_OR_UNKNOWN_MODEL'
        component = None if reason else _risk_components(features, result)
        active = None if reason else result.vessels[0].active_model
        # Resolver re-verifies lock and authority. Failure does not become a false alert.
        resolved = (self._model.resolve_batch_threshold(batch_token, (active, active))
                    if active and batch_token is not None else
                    resolve_threshold(self._model._config, (active, active)) if active else None)
        threshold = float(resolved.threshold) if resolved and resolved.available else None
        decision = _decision(component['risk_score'], threshold) if component else None
        wire_model = 'M5A' if active == 'M5a' else active
        fallback = active == 'CV'
        calibration = 'CALIBRATED' if threshold is not None else 'NOT_CALIBRATED'
        missing_history = reason == 'INSUFFICIENT_OR_INVALID_HISTORY'
        status = {'schema_version': '1.0.0', 'requested_model': 'M5A', 'active_model': wire_model,
                  'model_version': LOCK_ID if active else None, 'artifact_version': LOCK_ID if active else None,
                  'inference_status': 'SUCCESS' if active else ('NOT_RUN' if missing_history else 'FORECAST_UNAVAILABLE'),
                  'data_status': 'INSUFFICIENT_DATA' if missing_history else 'VALID',
                  'fallback_used': fallback, 'fallback_reason': '; '.join(sorted({v.fallback_reason for v in result.vessels if v.fallback_reason})) if fallback else None,
                  'calibration_status': calibration}
        response = {'schema_version': '1.0.0', 'request_id': request_id, 'encounter_id': expected_encounter,
                    'pair_id': candidate.pair_id, 'replay_session_id': snapshot.session_id,
                    'vessel_ids': list(candidate.vessels), 'vessel_roles': ['A', 'B'],
                    'anchor_timestamp': snapshot.anchor_utc, 'evaluated_at': snapshot.anchor_utc,
                    'current_dcpa_nm': None, 'current_tcpa_minutes': None, 'current_tcpa_clipped_minutes': None,
                    'current_cpa_status': 'UNAVAILABLE', 'predicted_min_distance_nm': None,
                    'predicted_closest_time_minutes': None, 'predicted_closest_timestamp': None,
                    'predicted_cpa_status': 'UNAVAILABLE', 'predicted_cpa_score': None, 'current_cpa_score': None,
                    'rule_score': None, 'risk_score': None, 'threshold': threshold,
                    'threshold_version': LOCK_ID if threshold is not None else None, 'calibration_status': calibration,
                    'threshold_model': wire_model if threshold is not None else None, 'alert_triggered': decision,
                    'decision_status': 'DECIDED' if decision is not None else ('INSUFFICIENT_DATA' if missing_history else 'UNAVAILABLE' if reason else 'NOT_CALIBRATED'),
                    'decision_reason': reason or ('THRESHOLD_APPLIED' if decision is not None else 'AUTHORITY_UNAVAILABLE'),
                    'forecast': _forecast_wire(features, result) if component else None,
                    'forecast_status': 'AVAILABLE' if component else ('NOT_RUN' if missing_history else 'UNAVAILABLE'),
                    'projection_status': 'APPLIED' if component else 'NOT_RUN', 'model_status': status}
        if component:
            response.update({k: v for k, v in component.items() if k not in ('scene', 'role')})
            response['predicted_closest_timestamp'] = _utc_plus(snapshot.anchor_utc, component['predicted_closest_time_minutes'])
        # Atomic recheck, deduplication, alert commit and publication under provider lock.
        with self._provider._lock, self._model._state_lock, self._lock:
            try:
                if self._model._closed:
                    raise RuntimeUnavailable('SERVICE_CLOSED')
                self._provider.encounter(snapshot, candidate)
                verify_reference()
                if batch_token is not None:
                    self._model._assert_batch_token(batch_token, snapshot, candidate)
                elif active:
                    again = resolve_threshold(self._model._config, (active, active))
                    if (again.available, again.threshold) != (resolved.available, resolved.threshold):
                        raise RuntimeUnavailable('AUTHORITY_CHANGED')
            except ValueError as exc:
                raise RuntimeUnavailable('STALE_RESULT_DISCARDED') from exc
            old = self._requests.get((snapshot.session_id, request_id))
            if old is not None and old != identity:
                raise RuntimeUnavailable('REQUEST_ID_CONFLICT')
            stored = self._cache.get(expected_encounter)
            if stored is not None:
                if stored[0] != identity:
                    raise RuntimeUnavailable('ENCOUNTER_SNAPSHOT_CONFLICT')
                old_response = stored[1]
                if (old_response['model_status']['active_model'] != response['model_status']['active_model'] or
                    old_response['threshold'] != response['threshold'] or
                    old_response['risk_score'] != response['risk_score'] or
                    old_response['alert_triggered'] != response['alert_triggered']):
                    raise RuntimeUnavailable('EVALUATION_CONFLICT')
                self._requests[(snapshot.session_id, request_id)] = identity
                self._state_revision += 1
                return deepcopy(stored[1])
            self._alerts.apply(response)
            self._requests[(snapshot.session_id, request_id)] = identity
            self._cache[expected_encounter] = (identity, deepcopy(response))
            self._state_revision += 1
            return deepcopy(response)

    def begin_batch_stage(self):
        """Lock readers/writers and create a private copy for atomic publication."""
        if not self._evaluation_lock.acquire(blocking=False):
            raise RuntimeUnavailable('EVALUATION_BUSY')
        try:
            with self._lock:
                staged = FixtureRiskHarness(self._provider, self._model)
                staged._cache = deepcopy(self._cache)
                staged._requests = deepcopy(self._requests)
                staged._alerts = self._alerts.clone()
                staged._state_revision = self._state_revision
                return BatchStage(self, staged, self._state_revision)
        except Exception:
            self._evaluation_lock.release()
            raise

    def invalidate_stale_anchor_cache(self, snapshot):
        """Drop only older bindings for this exact session/anchor before reevaluation.

        A PAUSED manual result and a subsequent PLAY batch can refer to the same
        semantic encounter while carrying a new session generation and snapshot
        ID. They must be recomputed under the new binding rather than treated as
        a cache hit or rejected because of the old binding.
        """
        with self._evaluation_lock:
            with self._provider._lock:
                self._provider._check(snapshot)
                with self._lock:
                    def stale(identity):
                        return (identity[0] == snapshot.session_id and
                                identity[3] == snapshot.anchor_utc and
                                (identity[1] != snapshot.session_version or
                                 identity[2] != snapshot.snapshot_id))

                    stale_keys = [key for key, (identity, _response) in self._cache.items()
                                  if stale(identity)]
                    stale_requests = [key for key, identity in self._requests.items()
                                      if stale(identity)]
                    for key in stale_keys:
                        del self._cache[key]
                    for key in stale_requests:
                        del self._requests[key]
                    if stale_keys or stale_requests:
                        self._state_revision += 1
                    return len(stale_keys), len(stale_requests)

    def publish_batch_stage(self, stage, snapshot, token):
        if not isinstance(stage, BatchStage) or stage.owner is not self or stage.closed:
            raise RuntimeUnavailable('BATCH_STAGE_INVALID')
        try:
            with self._provider._lock, self._model._state_lock, self._lock:
                if (self._model._closed or self._state_revision != stage.base_revision or
                        self._model._active_batch_token is not token):
                    raise RuntimeUnavailable('BATCH_PUBLICATION_INVALID')
                self._provider._check(snapshot)
                self._model._assert_batch_token(token)
                self._cache = stage.harness._cache
                self._requests = stage.harness._requests
                with self._alerts._lock, stage.harness._alerts._lock:
                    self._alerts._open = stage.harness._alerts._open
                    self._alerts._history = stage.harness._alerts._history
                    self._alerts._latest = stage.harness._alerts._latest
                self._state_revision += 1
                self._model._active_batch_token = None
                stage.closed = True
                return deepcopy(stage.results)
        finally:
            if not stage.closed:
                stage.closed = True
            self._evaluation_lock.release()

    def discard_batch_stage(self, stage):
        if not isinstance(stage, BatchStage) or stage.owner is not self or stage.closed:
            return
        stage.closed = True
        self._evaluation_lock.release()

    def alerts_for_session(self, session_id):
        return self._alerts.list(session_id)

    def alerts(self, snapshot):
        with self._provider._lock:
            self._provider._check(snapshot)
            return self._alerts.list(snapshot.session_id)
