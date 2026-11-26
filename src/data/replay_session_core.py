"""In-memory Contract V1 replay session core (not a persistence/API runtime)."""
from __future__ import annotations

from dataclasses import dataclass
import json
import threading
import time
import uuid
from typing import Any, Callable, Mapping

from src.data.replay_time import ReplayTimeError, parse_utc_ns, utc_iso_ns
from src.data.track_buffer import SourceIdentityVerifier, TrackBuffer, TrackBufferError


SESSION_STATES = {"READY", "PLAYING", "PAUSED", "ENDED", "EXPIRED"}
IDEMPOTENCY_RETENTION_SECONDS = 24 * 60 * 60
TRANSITIONS = {
    "READY": {"PLAY": "PLAYING", "PAUSE": 409, "RESUME": 409},
    "PLAYING": {"PLAY": 409, "PAUSE": "PAUSED", "RESUME": 409},
    "PAUSED": {"PLAY": "PLAYING", "PAUSE": 409, "RESUME": "PLAYING"},
    "ENDED": {"PLAY": 409, "PAUSE": 409, "RESUME": 409},
    "EXPIRED": {"PLAY": 410, "PAUSE": 410, "RESUME": 410},
}


class SessionCoreError(RuntimeError):
    def __init__(self, status_code: int, message: str, *, code: str = "SESSION_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True)
class SessionView:
    session_id: str
    source_id: str
    simulation_time: str
    status: str
    version: int

    def as_contract_response(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "source_id": self.source_id,
            "simulation_time": self.simulation_time,
            "status": self.status,
            "version": self.version,
        }


@dataclass
class _Session:
    session_id: str
    source_id: str
    source_start_ns: int
    source_end_ns: int
    simulation_ns: int
    status: str
    version: int
    buffer: TrackBuffer

    def view(self) -> SessionView:
        return SessionView(self.session_id, self.source_id, utc_iso_ns(self.simulation_ns), self.status, self.version)


@dataclass(frozen=True)
class _IdempotencyRecord:
    payload: str
    result: SessionView
    recorded_at: float


class ReplaySessionCore:
    """Thread-safe process-memory session/session-buffer isolation core.

    Idempotency entries and state disappear at process restart. This class does
    not implement REST routes, transaction storage, or a playback scheduler.
    """

    durable: bool = False

    def __init__(self, *, identity_verifier: SourceIdentityVerifier | None = None,
                 wall_clock: Callable[[], float] = time.time,
                 buffer_options: Mapping[str, Any] | None = None):
        self.identity_verifier = identity_verifier
        self.wall_clock = wall_clock
        self.buffer_options = dict(buffer_options or {})
        self._sessions: dict[str, _Session] = {}
        self._idempotency: dict[tuple[str, str], _IdempotencyRecord] = {}
        self._lock = threading.RLock()

    @property
    def session_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._sessions)

    def create(self, source_id: str, source_start: str, source_end: str,
               *, start_time: str | None = None) -> SessionView:
        if not isinstance(source_id, str) or not source_id.strip():
            raise SessionCoreError(422, "source_id is required", code="INVALID_SOURCE")
        try:
            start_ns = parse_utc_ns(source_start, field="source_start")
            end_ns = parse_utc_ns(source_end, field="source_end")
            simulation_ns = parse_utc_ns(start_time, field="start_time") if start_time is not None else start_ns
        except ReplayTimeError as exc:
            raise SessionCoreError(422, str(exc), code="INVALID_TIME") from exc
        if end_ns <= start_ns or not start_ns <= simulation_ns < end_ns:
            raise SessionCoreError(422, "source range/start_time is invalid", code="INVALID_TIME_RANGE")
        with self._lock:
            session = self._new_session(source_id, start_ns, end_ns, simulation_ns, "READY")
            self._sessions[session.session_id] = session
            return session.view()

    def get(self, session_id: str) -> SessionView:
        with self._lock:
            return self._require_session(session_id).view()

    def ingest(self, session_id: str, event: Mapping[str, Any]) -> str:
        with self._lock:
            session = self._require_session(session_id)
            if session.status in ("ENDED", "EXPIRED"):
                raise SessionCoreError(409 if session.status == "ENDED" else 410,
                                       "cannot ingest into a terminal replay session", code="SESSION_TERMINAL")
            try:
                timestamp_ns = parse_utc_ns(event.get("timestamp_utc"), field="timestamp_utc")
                if not session.source_start_ns <= timestamp_ns < session.source_end_ns:
                    raise SessionCoreError(422, "event is outside the session source range", code="EVENT_OUTSIDE_SOURCE")
                return session.buffer.ingest(event, session_id=session_id)
            except ReplayTimeError as exc:
                raise SessionCoreError(422, str(exc), code="INVALID_EVENT_TIME") from exc
            except TrackBufferError as exc:
                raise SessionCoreError(422, str(exc), code="INVALID_EVENT") from exc

    def record_invalid(self, session_id: str, vessel_id: str, timestamp: str, detail: str) -> None:
        with self._lock:
            session = self._require_session(session_id)
            try:
                session.buffer.record_invalid(vessel_id, timestamp, detail, session_id=session_id)
            except TrackBufferError as exc:
                raise SessionCoreError(422, str(exc), code="INVALID_MARKER") from exc

    def snapshot(self, session_id: str, vessel_id: str, *, anchor: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            session = self._require_session(session_id)
            anchor_value = anchor or utc_iso_ns(session.simulation_ns)
            try:
                if parse_utc_ns(anchor_value, field="anchor") > session.simulation_ns:
                    raise SessionCoreError(422, "anchor cannot exceed simulation clock", code="FUTURE_ANCHOR")
                return session.buffer.snapshot(vessel_id, anchor_value,
                                               simulation_clock=utc_iso_ns(session.simulation_ns))
            except TrackBufferError as exc:
                raise SessionCoreError(422, str(exc), code="INVALID_SNAPSHOT") from exc
            except ReplayTimeError as exc:
                raise SessionCoreError(422, str(exc), code="INVALID_ANCHOR") from exc

    def control(self, session_id: str, action: str, *, expected_version: int,
                target_time: str | None = None, idempotency_key: str | None = None) -> SessionView:
        action = action if isinstance(action, str) else ""
        if action not in {"PLAY", "PAUSE", "RESUME", "RESET", "SEEK"}:
            raise SessionCoreError(422, "unknown control action", code="INVALID_ACTION")
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
            raise SessionCoreError(422, "expected_version must be a nonnegative integer", code="INVALID_VERSION")
        if action == "SEEK":
            if target_time is None:
                raise SessionCoreError(422, "SEEK requires target_time", code="MISSING_TARGET")
        elif target_time is not None:
            raise SessionCoreError(422, "target_time is only valid for SEEK", code="UNEXPECTED_TARGET")
        if action in ("RESET", "SEEK") and idempotency_key is None:
            raise SessionCoreError(422, "RESET/SEEK require Idempotency-Key", code="MISSING_IDEMPOTENCY_KEY")
        if idempotency_key is not None and (not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128):
            raise SessionCoreError(422, "Idempotency-Key length must be 1..128", code="INVALID_IDEMPOTENCY_KEY")
        try:
            target_ns = parse_utc_ns(target_time, field="target_time") if target_time is not None else None
            canonical_target = utc_iso_ns(target_ns) if target_ns is not None else None
        except ReplayTimeError as exc:
            raise SessionCoreError(422, str(exc), code="INVALID_TARGET") from exc
        payload_obj: dict[str, Any] = {"action": action}
        if action == "SEEK":
            payload_obj["target_time"] = canonical_target
        payload_obj["expected_version"] = expected_version
        canonical_payload = json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":"))

        with self._lock:
            session = self._require_session(session_id)
            self._purge_idempotency()
            record_key = (session_id, idempotency_key) if idempotency_key is not None else None
            if record_key is not None and record_key in self._idempotency:
                previous = self._idempotency[record_key]
                if previous.payload != canonical_payload:
                    raise SessionCoreError(409, "Idempotency-Key was used with a different payload",
                                           code="IDEMPOTENCY_CONFLICT")
                return previous.result
            if session.status == "EXPIRED":
                raise SessionCoreError(410, "session has expired", code="SESSION_EXPIRED")
            if session.status == "ENDED":
                raise SessionCoreError(409, "ended session cannot be controlled", code="SESSION_ENDED")
            if expected_version != session.version:
                raise SessionCoreError(409, "expected_version does not match current version",
                                       code="VERSION_CONFLICT")

            if action in ("PLAY", "PAUSE", "RESUME"):
                next_status = TRANSITIONS[session.status][action]
                if isinstance(next_status, int):
                    raise SessionCoreError(next_status, f"{action} is invalid from {session.status}",
                                           code="INVALID_TRANSITION")
                session.status = next_status
                session.version += 1
                result = session.view()
            else:
                if action == "SEEK" and not session.source_start_ns <= int(target_ns) < session.source_end_ns:
                    raise SessionCoreError(422, "SEEK target is outside source range", code="TARGET_OUT_OF_RANGE")
                session.status = "ENDED"
                session.version += 1
                new_clock = session.source_start_ns if action == "RESET" else int(target_ns)
                new_status = "READY" if action == "RESET" else "PAUSED"
                successor = self._new_session(session.source_id, session.source_start_ns,
                                              session.source_end_ns, new_clock, new_status)
                self._sessions[successor.session_id] = successor
                result = successor.view()
            if record_key is not None:
                self._idempotency[record_key] = _IdempotencyRecord(canonical_payload, result, self.wall_clock())
            return result

    def advance_clock(self, session_id: str, target_time: str) -> SessionView:
        """Advance the authoritative simulation clock; source end is exclusive."""
        try:
            target_ns = parse_utc_ns(target_time, field="simulation_time")
        except ReplayTimeError as exc:
            raise SessionCoreError(422, str(exc), code="INVALID_SIMULATION_TIME") from exc
        with self._lock:
            session = self._require_session(session_id)
            if session.status == "EXPIRED":
                raise SessionCoreError(410, "session has expired", code="SESSION_EXPIRED")
            if session.status != "PLAYING":
                raise SessionCoreError(409, "simulation clock advances only while PLAYING", code="CLOCK_NOT_PLAYING")
            if target_ns < session.simulation_ns or target_ns > session.source_end_ns:
                raise SessionCoreError(422, "simulation clock must advance within source range", code="CLOCK_OUT_OF_RANGE")
            clock_changed = target_ns != session.simulation_ns
            if clock_changed:
                session.simulation_ns = target_ns
            status_changed = target_ns == session.source_end_ns and session.status != "ENDED"
            if target_ns == session.source_end_ns:
                session.status = "ENDED"
            # Version is the optimistic-control version. Ordinary clock ticks
            # must not invalidate a control request between polling and POST;
            # the PLAYING -> ENDED state transition still advances it once.
            if status_changed:
                session.version += 1
            return session.view()

    def expire(self, session_id: str) -> SessionView:
        with self._lock:
            session = self._require_session(session_id)
            if session.status != "EXPIRED":
                session.status = "EXPIRED"
                session.version += 1
            return session.view()

    def _new_session(self, source_id: str, start_ns: int, end_ns: int,
                     simulation_ns: int, status: str) -> _Session:
        session_id = str(uuid.uuid4())
        buffer = TrackBuffer(session_id, identity_verifier=self.identity_verifier, **self.buffer_options)
        return _Session(session_id, source_id, start_ns, end_ns, simulation_ns, status, 0, buffer)

    def _require_session(self, session_id: str) -> _Session:
        try:
            parsed = uuid.UUID(session_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise SessionCoreError(404, "session was not found", code="SESSION_NOT_FOUND") from exc
        if str(parsed) != session_id:
            raise SessionCoreError(404, "session_id must be lowercase canonical UUID", code="SESSION_NOT_FOUND")
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionCoreError(404, "session was not found", code="SESSION_NOT_FOUND")
        return session

    def _purge_idempotency(self) -> None:
        cutoff = self.wall_clock() - IDEMPOTENCY_RETENTION_SECONDS
        expired = [key for key, record in self._idempotency.items() if record.recorded_at < cutoff]
        for key in expired:
            del self._idempotency[key]
