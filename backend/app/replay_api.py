"""Contract-shaped local Replay V1 API adapter over the T09 in-memory core.

This adapter is intentionally process-local. It is suitable for T12 integration
and verification, not a durable multi-worker production deployment.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable, Iterable, Mapping
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from src.data.replay_session_core import ReplaySessionCore, SessionCoreError, SessionView
from src.data.replay_time import ReplayTimeError, parse_utc_ns, utc_iso_ns
from src.data.track_buffer import SourceIdentityVerifier, TrackBufferError


UTC_REPLAY_START = "2024-11-01T00:00:00Z"
UTC_REPLAY_END = "2024-11-01T00:10:00Z"
DEMO_SOURCE_ID = "fixture-denmark-10m-v1"
SNAPSHOT_TTL_SECONDS = 300
# Nine one-minute history intervals plus the inclusive 60-second source-age bound.
REPLAY_HISTORY_LOOKBACK_NS = 10 * 60 * 1_000_000_000


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: StrictStr = Field(min_length=1)
    start_time: StrictStr | None = None

    @model_validator(mode="after")
    def utc_start(self):
        if self.start_time is not None:
            _require_wire_utc(self.start_time, "start_time")
        return self


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: StrictStr
    expected_version: StrictInt = Field(ge=0)
    target_time: StrictStr | None = None

    @model_validator(mode="after")
    def valid_shape(self):
        if self.action not in {"PLAY", "PAUSE", "RESUME", "RESET", "SEEK"}:
            raise ValueError("action is not in the Replay V1 enum")
        has_target = "target_time" in self.model_fields_set
        if self.action == "SEEK":
            if not has_target or self.target_time is None:
                raise ValueError("SEEK requires target_time")
            _require_wire_utc(self.target_time, "target_time")
        elif has_target:
            raise ValueError("target_time is permitted only for SEEK")
        return self


@dataclass(frozen=True)
class ReplaySource:
    source_id: str
    start_time: str
    end_time: str
    event_loader: Callable[[], Iterable[Mapping[str, Any]]]
    identity_verifier: SourceIdentityVerifier | None = None


@dataclass(frozen=True)
class _PinnedSnapshot:
    snapshot_id: str
    session_id: str
    simulation_time: str
    created_at: float
    items: tuple[dict[str, Any], ...]


def _require_wire_utc(value: str, field: str) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must use the Contract V1 UTC Z form")
    try:
        return parse_utc_ns(value, field=field)
    except ReplayTimeError as exc:
        raise ValueError(str(exc)) from exc


def _event_timestamp_ns(event: Mapping[str, Any]) -> int:
    return parse_utc_ns(event.get("timestamp_utc"), field="event timestamp")


@lru_cache(maxsize=8)
def _schema_validator(definition: str) -> Draft202012Validator:
    root = Path(__file__).resolve().parents[2] / "contracts"
    base = "https://schemas.ait3040.invalid/contracts/"
    registry = Registry()
    for name in ("common", "track_snapshot", "replay"):
        document = json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(document)
        document["$id"] = base + f"{name}.schema.json"
        registry = registry.with_resource(document["$id"], Resource.from_contents(document))
    return Draft202012Validator({"$ref": base + "replay.schema.json#/$defs/" + definition},
                                registry=registry, format_checker=FormatChecker())


class ReplayAPI:
    """Source registry, session adapter, and short-lived immutable page pins."""

    durable = False

    def __init__(self, sources: Iterable[ReplaySource], *, monotonic: Callable[[], float] = time.monotonic,
                 snapshot_ttl_seconds: int = SNAPSHOT_TTL_SECONDS, max_snapshots: int = 10_000):
        self.sources = {source.source_id: source for source in sources}
        self.monotonic = monotonic
        self.snapshot_ttl_seconds = snapshot_ttl_seconds
        self.max_snapshots = max_snapshots
        self._cores: dict[str, ReplaySessionCore] = {}
        self._session_sources: dict[str, str] = {}
        self._session_vessels: dict[str, set[str]] = {}
        self._populated: set[str] = set()
        self._source_events: dict[str, list[Mapping[str, Any]]] = {}
        self._session_event_cursor: dict[str, int] = {}
        self._playback_clocks: dict[str, tuple[float, int]] = {}
        self._snapshots: dict[str, _PinnedSnapshot] = {}
        self._expired_snapshots: dict[str, float] = {}
        self._lock = threading.RLock()

    def create_session(self, request: CreateSessionRequest) -> SessionView:
        source = self.sources.get(request.source_id)
        if source is None:
            raise APIProblem(503, "SOURCE_UNAVAILABLE", "Replay source is not registered")
        events = self._load_ordered_events(source)
        core = self._core_for(source)
        try:
            session = core.create(source.source_id, source.start_time, source.end_time,
                                  start_time=request.start_time)
            self._populate(core, session.session_id, source, events, session.simulation_time)
        except SessionCoreError as exc:
            raise APIProblem(exc.status_code, exc.code, str(exc)) from exc
        except (TrackBufferError, ReplayTimeError) as exc:
            raise APIProblem(503, "SOURCE_INVALID", str(exc)) from exc
        self._validate_session(session)
        return session

    def get_session(self, session_id: str) -> SessionView:
        core = self._core_for_session(session_id)
        try:
            view = self._sync_playback_clock(core, session_id)
        except SessionCoreError as exc:
            raise APIProblem(exc.status_code, exc.code, str(exc)) from exc
        if view.status == "EXPIRED":
            raise APIProblem(410, "SESSION_EXPIRED", "Replay session has expired")
        self._validate_session(view)
        return view

    def control(self, session_id: str, request: ControlRequest,
                idempotency_key: str | None) -> SessionView:
        core = self._core_for_session(session_id)
        try:
            before = self._sync_playback_clock(core, session_id)
            source_id = before.source_id
        except SessionCoreError as exc:
            raise APIProblem(exc.status_code, exc.code, str(exc)) from exc
        source = self.sources.get(source_id)
        if source is None:
            raise APIProblem(503, "SOURCE_UNAVAILABLE", "Replay source is not registered")
        try:
            result = core.control(session_id, request.action,
                                  expected_version=request.expected_version,
                                  target_time=request.target_time,
                                  idempotency_key=idempotency_key)
        except SessionCoreError as exc:
            raise APIProblem(exc.status_code, exc.code, str(exc)) from exc
        with self._lock:
            if result.session_id != session_id or result.status != "PLAYING":
                self._playback_clocks.pop(session_id, None)
            elif before.status != "PLAYING":
                self._playback_clocks[session_id] = (
                    self.monotonic(), parse_utc_ns(result.simulation_time, field="simulation_time"))
        if result.session_id != session_id:
            with self._lock:
                populated = result.session_id in self._populated
            if not populated:
                with self._lock:
                    events = self._source_events.get(source.source_id)
                if events is None:
                    events = self._load_ordered_events(source)
                try:
                    self._populate(core, result.session_id, source, events, result.simulation_time)
                except (TrackBufferError, ReplayTimeError) as exc:
                    raise APIProblem(503, "SOURCE_INVALID", str(exc)) from exc
        self._validate_session(result)
        return result

    def _sync_playback_clock(self, core: ReplaySessionCore, session_id: str) -> SessionView:
        """Advance a PLAYING session from backend monotonic elapsed time on REST activity.

        Polling is the scheduler for this in-memory fixture runtime: no browser wall clock
        is used as AIS/simulation time, and no background thread is needed. A dormant
        session catches up from its server-side baseline on the next read/control.
        """
        view = core.get(session_id)
        if view.status != "PLAYING":
            with self._lock:
                self._playback_clocks.pop(session_id, None)
            return view
        now = self.monotonic()
        with self._lock:
            baseline = self._playback_clocks.get(session_id)
            if baseline is None:
                baseline = (now, parse_utc_ns(view.simulation_time, field="simulation_time"))
                self._playback_clocks[session_id] = baseline
        started_at, simulation_start_ns = baseline
        elapsed_seconds = max(0, int(now - started_at))
        if elapsed_seconds == 0:
            return view
        source = self.sources.get(view.source_id)
        if source is None:
            return view
        source_end_ns = parse_utc_ns(source.end_time, field="source_end")
        target_ns = min(simulation_start_ns + elapsed_seconds * 1_000_000_000, source_end_ns)
        if target_ns <= parse_utc_ns(view.simulation_time, field="simulation_time"):
            return view
        try:
            with self._lock:
                self._ingest_through(core, session_id, target_ns)
                updated = core.advance_clock(session_id, utc_iso_ns(target_ns))
        except SessionCoreError as exc:
            raise APIProblem(exc.status_code, exc.code, str(exc)) from exc
        except TrackBufferError as exc:
            raise APIProblem(503, "SOURCE_INVALID", str(exc)) from exc
        if updated.status != "PLAYING":
            with self._lock:
                self._playback_clocks.pop(session_id, None)
        return updated

    def list_tracks(self, session_id: str, *, limit: int, offset: int,
                    snapshot_id: str | None) -> dict[str, Any]:
        view = self.get_session(session_id)
        if offset > 0 and snapshot_id is None:
            raise APIProblem(422, "SNAPSHOT_REQUIRED", "snapshot_id is required when offset is greater than zero")
        pinned = self._snapshot_for(session_id, snapshot_id) if snapshot_id is not None else None
        if pinned is None:
            pinned = self._pin_current(session_id, view.simulation_time)
        body = {
            "items": list(pinned.items[offset:offset + limit]),
            "total": len(pinned.items), "limit": limit, "offset": offset,
            "snapshot_id": pinned.snapshot_id, "simulation_time": pinned.simulation_time,
        }
        _schema_validator("track_list").validate(body)
        return body

    def get_track(self, session_id: str, vessel_id: str, *, snapshot_id: str | None) -> dict[str, Any]:
        view = self.get_session(session_id)
        pinned = self._snapshot_for(session_id, snapshot_id) if snapshot_id is not None else None
        if snapshot_id is not None and pinned is None:
            raise APIProblem(404, "SNAPSHOT_NOT_FOUND", "Snapshot does not belong to this session")
        if pinned is None:
            pinned = self._pin_current(session_id, view.simulation_time)
        track = next((item for item in pinned.items if item["vessel_id"] == vessel_id), None)
        if track is None:
            raise APIProblem(404, "VESSEL_NOT_FOUND", "Track was not found in the selected session snapshot")
        _schema_validator("production_track").validate(track)
        return track

    def _core_for(self, source: ReplaySource) -> ReplaySessionCore:
        with self._lock:
            core = self._cores.get(source.source_id)
            if core is None:
                core = ReplaySessionCore(identity_verifier=source.identity_verifier)
                self._cores[source.source_id] = core
            return core

    def _core_for_session(self, session_id: str) -> ReplaySessionCore:
        try:
            parsed = uuid.UUID(session_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise APIProblem(404, "SESSION_NOT_FOUND", "Replay session was not found") from exc
        if str(parsed) != session_id:
            raise APIProblem(404, "SESSION_NOT_FOUND", "Session ID must be a lowercase canonical UUID")
        with self._lock:
            for core in self._cores.values():
                if session_id in core.session_ids:
                    return core
        raise APIProblem(404, "SESSION_NOT_FOUND", "Replay session was not found")

    def _load_ordered_events(self, source: ReplaySource) -> list[Mapping[str, Any]]:
        try:
            events = list(source.event_loader())
            start_ns, end_ns = parse_utc_ns(source.start_time), parse_utc_ns(source.end_time)
            timestamps = [parse_utc_ns(event.get("timestamp_utc"), field="event timestamp") for event in events]
            if timestamps != sorted(timestamps):
                raise ValueError("Replay source events must be ordered by selected source timestamp")
            if any(value < start_ns or value >= end_ns for value in timestamps):
                raise ValueError("Replay source event falls outside its registered time range")
            return events
        except (OSError, ValueError, TypeError, ReplayTimeError) as exc:
            raise APIProblem(503, "SOURCE_INVALID", f"Replay source validation failed: {exc}") from exc

    def _populate(self, core: ReplaySessionCore, session_id: str, source: ReplaySource,
                  events: list[Mapping[str, Any]], anchor: str) -> None:
        """Seed only causal history for a new session; later events follow the clock."""
        anchor_ns = parse_utc_ns(anchor, field="simulation_time")
        first_needed_ns = anchor_ns - REPLAY_HISTORY_LOOKBACK_NS
        first_index = bisect_left(events, first_needed_ns, key=_event_timestamp_ns)
        with self._lock:
            self._source_events[source.source_id] = events
            self._session_sources[session_id] = source.source_id
            self._session_vessels[session_id] = {
                str(event["vessel_id"]) for event in events
            }
            self._session_event_cursor[session_id] = first_index
        self._ingest_through(core, session_id, anchor_ns)
        with self._lock:
            self._populated.add(session_id)

    def _ingest_through(self, core: ReplaySessionCore, session_id: str, target_ns: int) -> None:
        """Ingest source events only through the authoritative replay clock."""
        with self._lock:
            source_id = self._session_sources.get(session_id)
            events = self._source_events.get(source_id) if source_id is not None else None
            cursor = self._session_event_cursor.get(session_id)
            if events is None or cursor is None:
                raise TrackBufferError("replay event stream is not registered for session")
            end_index = bisect_right(events, target_ns, key=_event_timestamp_ns)
            while cursor < end_index:
                core.ingest(session_id, events[cursor])
                cursor += 1
                self._session_event_cursor[session_id] = cursor

    def _pin_current(self, session_id: str, simulation_time: str) -> _PinnedSnapshot:
        core = self._core_for_session(session_id)
        vessel_ids = self._session_vessels.get(session_id, set())
        tracks = []
        for vessel_id in sorted(vessel_ids, key=lambda value: value.encode("utf-8")):
            try:
                track = core.snapshot(session_id, vessel_id, anchor=simulation_time)
            except SessionCoreError as exc:
                raise APIProblem(exc.status_code, exc.code, str(exc)) from exc
            if track is not None:
                tracks.append(track)
        with self._lock:
            self._purge_snapshots()
            if len(self._snapshots) >= self.max_snapshots:
                raise APIProblem(503, "SNAPSHOT_CAPACITY", "Snapshot cache is at capacity")
            snapshot = _PinnedSnapshot(str(uuid.uuid4()), session_id, simulation_time,
                                       self.monotonic(), tuple(tracks))
            self._snapshots[snapshot.snapshot_id] = snapshot
            return snapshot

    def _snapshot_for(self, session_id: str, snapshot_id: str | None) -> _PinnedSnapshot | None:
        if snapshot_id is None:
            return None
        try:
            parsed = uuid.UUID(snapshot_id)
        except (ValueError, TypeError) as exc:
            raise APIProblem(404, "SNAPSHOT_NOT_FOUND", "Snapshot was not found") from exc
        if str(parsed) != snapshot_id:
            raise APIProblem(404, "SNAPSHOT_NOT_FOUND", "Snapshot ID must be a lowercase canonical UUID")
        with self._lock:
            self._purge_snapshots()
            snapshot = self._snapshots.get(snapshot_id)
            if snapshot is None:
                if snapshot_id in self._expired_snapshots:
                    raise APIProblem(410, "SNAPSHOT_EXPIRED", "Replay snapshot has expired")
                raise APIProblem(404, "SNAPSHOT_NOT_FOUND", "Snapshot was not found")
            if snapshot.session_id != session_id:
                raise APIProblem(404, "SNAPSHOT_NOT_FOUND", "Snapshot does not belong to this session")
            return snapshot

    def _purge_snapshots(self) -> None:
        now = self.monotonic()
        expired = [key for key, value in self._snapshots.items()
                   if now - value.created_at >= self.snapshot_ttl_seconds]
        for key in expired:
            del self._snapshots[key]
            self._expired_snapshots[key] = now + self.snapshot_ttl_seconds
        for key, expires_at in list(self._expired_snapshots.items()):
            if now >= expires_at:
                del self._expired_snapshots[key]

    @staticmethod
    def _validate_session(view: SessionView) -> None:
        _schema_validator("session_response").validate(view.as_contract_response())


class APIProblem(Exception):
    def __init__(self, status_code: int, error_code: str, message: str,
                 details: dict[str, Any] | None = None):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details


def demo_source() -> ReplaySource:
    fixture = Path(__file__).resolve().parent / "fixtures" / "t12_replay_events.json"

    def load_events():
        return json.loads(fixture.read_text(encoding="utf-8"))

    return ReplaySource(DEMO_SOURCE_ID, UTC_REPLAY_START, UTC_REPLAY_END, load_events)


def get_replay_api(request: Request) -> ReplayAPI:
    return request.app.state.replay_api


router = APIRouter(prefix="/api/v1/replay/sessions", tags=["replay-v1"])


def _raise_problem(problem: APIProblem) -> None:
    raise HTTPException(problem.status_code, detail={
        "error_code": problem.error_code,
        "message": problem.message,
        "details": problem.details,
    })


@router.post("", status_code=201)
def create_replay_session(body: CreateSessionRequest, response: Response,
                          replay_api: ReplayAPI = Depends(get_replay_api)):
    try:
        view = replay_api.create_session(body)
        response.status_code = 201
        return view.as_contract_response()
    except APIProblem as exc:
        _raise_problem(exc)


@router.get("/{session_id}")
def read_replay_session(session_id: str, replay_api: ReplayAPI = Depends(get_replay_api)):
    try:
        return replay_api.get_session(session_id).as_contract_response()
    except APIProblem as exc:
        _raise_problem(exc)


@router.post("/{session_id}/control")
def control_replay_session(session_id: str, body: ControlRequest,
                           idempotency_key: str | None = Header(default=None, alias="Idempotency-Key",
                                                                 min_length=1, max_length=128),
                           replay_api: ReplayAPI = Depends(get_replay_api)):
    try:
        return replay_api.control(session_id, body, idempotency_key).as_contract_response()
    except APIProblem as exc:
        _raise_problem(exc)


@router.get("/{session_id}/tracks")
def list_replay_tracks(session_id: str,
                       limit: int = Query(default=50, ge=1, le=100),
                       offset: int = Query(default=0, ge=0),
                       snapshot_id: str | None = Query(default=None),
                       replay_api: ReplayAPI = Depends(get_replay_api)):
    try:
        return replay_api.list_tracks(session_id, limit=limit, offset=offset,
                                      snapshot_id=snapshot_id)
    except APIProblem as exc:
        _raise_problem(exc)


@router.get("/{session_id}/tracks/{vessel_id}")
def read_replay_track(session_id: str, vessel_id: str,
                      snapshot_id: str | None = Query(default=None),
                      replay_api: ReplayAPI = Depends(get_replay_api)):
    try:
        return replay_api.get_track(session_id, vessel_id, snapshot_id=snapshot_id)
    except APIProblem as exc:
        _raise_problem(exc)


def build_default_replay_api() -> ReplayAPI:
    return ReplayAPI([demo_source()])
