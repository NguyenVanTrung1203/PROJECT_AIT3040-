"""Session-scoped bounded track buffering and Contract V1 as-of snapshots."""
from __future__ import annotations

from bisect import insort
from dataclasses import dataclass
import json
import math
import unicodedata
from typing import Any, Callable, Mapping

from src.data.replay_time import ReplayTimeError, parse_utc_ns, utc_iso_ns
from src.data.track_semantics import validate_production_track_g11, validate_track_semantics


NSEC = 1_000_000_000
MINUTE = 60 * NSEC
HISTORY_OFFSETS = tuple(range(-9, 1))
SourceIdentityVerifier = Callable[[Mapping[str, Any]], bool]


class TrackBufferError(ValueError):
    """A replay event or buffering request violates T09 safety invariants."""


@dataclass(frozen=True)
class _BufferedEvent:
    order: tuple[int, bytes, int, bytes]
    event: dict[str, Any]


@dataclass(frozen=True)
class _InvalidMarker:
    timestamp_ns: int
    detail: str


class TrackBuffer:
    """A bounded in-memory buffer owned by exactly one replay session.

    REAL_AIS and physical MMSI bindings are rejected unless an explicit source
    identity verifier is provided and accepts the full event/provenance record.
    No verifier ships as an implicit allow-all default.
    """

    def __init__(self, session_id: str, *, identity_verifier: SourceIdentityVerifier | None = None,
                 retention_seconds: int = 900, max_vessels: int = 10_000,
                 max_events_per_vessel: int = 4_096, max_total_events: int = 1_000_000):
        if not session_id:
            raise TrackBufferError("session_id is required")
        if min(retention_seconds, max_vessels, max_events_per_vessel, max_total_events) <= 0:
            raise TrackBufferError("buffer limits must be positive")
        self.session_id = session_id
        self.identity_verifier = identity_verifier
        self.retention_ns = retention_seconds * NSEC
        self.max_vessels = max_vessels
        self.max_events_per_vessel = max_events_per_vessel
        self.max_total_events = max_total_events
        self._events: dict[str, list[_BufferedEvent]] = {}
        self._identity: dict[str, dict[str, Any]] = {}
        self._latest_seen: dict[str, int] = {}
        self._invalid: dict[str, _InvalidMarker] = {}
        self._event_count = 0

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def vessel_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._events, key=lambda value: value.encode("utf-8")))

    def ingest(self, event: Mapping[str, Any], *, session_id: str) -> str:
        if session_id != self.session_id:
            raise TrackBufferError("event belongs to a different replay session")
        normalized = self._validate_and_normalize(event)
        vessel_id = normalized["vessel_id"]
        timestamp_ns = parse_utc_ns(normalized["timestamp_utc"], field="timestamp_utc")
        items = self._events.get(vessel_id)
        if items is None:
            if len(self._events) >= self.max_vessels:
                raise TrackBufferError("maximum buffered vessel count reached")
            items = []
        prior_identity = self._identity.get(vessel_id)
        identity = {name: normalized.get(name) for name in ("mmsi", "source_type", "is_simulated")}
        if prior_identity is not None and prior_identity != identity:
            raise TrackBufferError("vessel identity/source cannot change within a session")
        newest = max(self._latest_seen.get(vessel_id, timestamp_ns), timestamp_ns)
        if timestamp_ns < newest - self.retention_ns:
            raise TrackBufferError("out-of-order event is outside the retention window")

        cutoff = max(newest, timestamp_ns) - self.retention_ns
        if items:
            kept = [item for item in items if item.order[0] >= cutoff]
            self._event_count -= len(items) - len(kept)
            items[:] = kept
        if len(items) >= self.max_events_per_vessel or self._event_count >= self.max_total_events:
            raise TrackBufferError("bounded track buffer capacity reached")

        provenance = normalized["provenance"]
        stable_source = provenance["source_file"].encode("utf-8")
        source_row = provenance["source_row"]
        canonical = json.dumps(normalized, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False).encode("utf-8")
        stored = _BufferedEvent((timestamp_ns, stable_source, source_row, canonical), normalized)
        insort(items, stored, key=lambda row: row.order)
        self._events[vessel_id] = items
        if prior_identity is None:
            self._identity[vessel_id] = identity
        self._latest_seen[vessel_id] = max(self._latest_seen.get(vessel_id, timestamp_ns), timestamp_ns)
        self._event_count += 1
        invalid = self._invalid.get(vessel_id)
        if invalid is not None and timestamp_ns >= invalid.timestamp_ns:
            self._invalid.pop(vessel_id, None)
        return vessel_id

    def record_invalid(self, vessel_id: str, timestamp: str, detail: str, *, session_id: str) -> None:
        """Record only a timestamp/reason marker; rejected payloads never enter the buffer."""
        if session_id != self.session_id:
            raise TrackBufferError("invalid marker belongs to a different replay session")
        identity = self._identity.get(vessel_id)
        if identity is None:
            raise TrackBufferError("invalid marker requires an already known canonical vessel identity")
        timestamp_ns = parse_utc_ns(timestamp, field="invalid event timestamp")
        marker = _InvalidMarker(timestamp_ns, str(detail)[:160])
        previous = self._invalid.get(vessel_id)
        if previous is None or (marker.timestamp_ns, marker.detail) > (previous.timestamp_ns, previous.detail):
            self._invalid[vessel_id] = marker

    def snapshot(self, vessel_id: str, anchor: str, *, simulation_clock: str,
                 data_status_override: str | None = None) -> dict[str, Any] | None:
        """Return a schema/G11-validated as-of TrackSnapshot, or None for unknown ID."""
        identity = self._identity.get(vessel_id)
        if identity is None:
            return None
        anchor_ns = parse_utc_ns(anchor, field="anchor_timestamp")
        clock_ns = parse_utc_ns(simulation_clock, field="simulation_clock")
        if anchor_ns > clock_ns:
            raise TrackBufferError("snapshot anchor cannot exceed authoritative simulation clock")
        items = self._events[vessel_id]
        ordered = [item for item in items if item.order[0] <= anchor_ns]
        history: list[dict[str, Any]] = []
        latest_asof: _BufferedEvent | None = ordered[-1] if ordered else None
        for offset in HISTORY_OFFSETS:
            nominal_ns = anchor_ns + offset * MINUTE
            selected: _BufferedEvent | None = None
            for item in ordered:
                if item.order[0] <= nominal_ns:
                    if selected is None or item.order[0] > selected.order[0]:
                        # Stable-first for equal source times: `ordered` sorts
                        # provenance ascending, so retain the first tie.
                        selected = item
                else:
                    break
            if selected is None:
                continue
            age_ns = nominal_ns - selected.order[0]
            if age_ns < 0 or age_ns > MINUTE:
                continue
            event = selected.event
            original = event.get("original_source_timestamp")
            history.append({
                "nominal_timestamp": utc_iso_ns(nominal_ns),
                "source_timestamp": event["timestamp_utc"],
                "original_source_timestamp": original,
                "latitude": event["latitude"], "longitude": event["longitude"],
                "sog_kn": event["sog_kn"], "cog_deg": event["cog_deg"],
                "source_age_seconds": age_ns / NSEC,
            })

        marker = self._invalid.get(vessel_id)
        if data_status_override is not None:
            status = data_status_override
        elif marker is not None and marker.timestamp_ns <= anchor_ns and (latest_asof is None or marker.timestamp_ns >= latest_asof.order[0]):
            status = "INVALID_DATA"
        elif self._latest_seen.get(vessel_id) is not None and self._latest_seen[vessel_id] <= anchor_ns and anchor_ns - self._latest_seen[vessel_id] > MINUTE:
            status = "STALE"
        elif len(history) == 10:
            status = "VALID"
        else:
            status = "INSUFFICIENT_DATA"

        current_state = history[-1] if status == "VALID" and history else None
        snapshot = {
            "schema_version": "1.0.0", "vessel_id": vessel_id,
            "mmsi": identity["mmsi"], "source_type": identity["source_type"],
            "is_simulated": identity["is_simulated"],
            "anchor_timestamp": utc_iso_ns(anchor_ns),
            "current_state": current_state, "history": history,
            "data_status": status,
        }
        validate_track_snapshot_runtime(snapshot, simulation_clock=utc_iso_ns(clock_ns))
        return snapshot

    def _validate_and_normalize(self, event: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(event, Mapping):
            raise TrackBufferError("event must be a mapping")
        row = {name: event.get(name) for name in (
            "timestamp_utc", "original_source_timestamp", "vessel_id", "mmsi",
            "source_type", "is_simulated", "latitude", "longitude", "sog_kn",
            "cog_deg", "provenance",
        )}
        try:
            timestamp_ns = parse_utc_ns(row.get("timestamp_utc"), field="timestamp_utc")
            row["timestamp_utc"] = utc_iso_ns(timestamp_ns)
            original = row.get("original_source_timestamp")
            row["original_source_timestamp"] = (
                utc_iso_ns(parse_utc_ns(original, field="original_source_timestamp"))
                if original is not None else None
            )
            if (row.get("source_type") == "REAL_AIS"
                    and row["original_source_timestamp"] is not None
                    and row["original_source_timestamp"] != row["timestamp_utc"]):
                raise TrackBufferError("REAL_AIS original and selected source timestamps must match")
            vessel_id = row.get("vessel_id")
            if not isinstance(vessel_id, str) or not vessel_id:
                raise TrackBufferError("canonical vessel_id is required")
            row["vessel_id"] = unicodedata.normalize("NFC", vessel_id)
            if len(row["vessel_id"].encode("utf-8")) > 512:
                raise TrackBufferError("canonical vessel_id exceeds the buffer identity limit")
            provenance = row.get("provenance")
            if not isinstance(provenance, Mapping):
                raise TrackBufferError("event provenance is required")
            source_file, source_row = provenance.get("source_file"), provenance.get("source_row")
            if (not isinstance(source_file, str) or not source_file.strip()
                    or len(source_file.encode("utf-8")) > 1024
                    or isinstance(source_row, bool) or not isinstance(source_row, int)
                    or source_row < 1 or source_row > 2**63 - 1):
                raise TrackBufferError("source_file/source_row provenance is invalid")
            row["provenance"] = {"source_file": source_file, "source_row": source_row}
            for name, minimum, maximum, include_max in (
                ("latitude", -90.0, 90.0, True), ("longitude", -180.0, 180.0, True),
                ("sog_kn", 0.0, 50.0, True), ("cog_deg", 0.0, 360.0, False),
            ):
                value = row.get(name)
                if isinstance(value, bool) or value is None or not math.isfinite(float(value)):
                    raise TrackBufferError(f"{name} must be a finite non-null number")
                value = float(value)
                if value < minimum or (value > maximum if include_max else value >= maximum):
                    raise TrackBufferError(f"{name} is outside the accepted range")
                row[name] = value
            try:
                validate_track_semantics(row, profile="PRODUCTION_V1")
            except (ValueError, TypeError) as exc:
                raise TrackBufferError(f"invalid production identity/provenance: {exc}") from exc
            if row["source_type"] == "REAL_AIS" or row["vessel_id"].startswith("physical_mmsi:"):
                if self.identity_verifier is None or not self.identity_verifier(row):
                    raise TrackBufferError("physical identity is not verified by the configured source policy")
            return row
        except ReplayTimeError as exc:
            raise TrackBufferError(str(exc)) from exc
        except (TypeError, ValueError, OverflowError) as exc:
            if isinstance(exc, TrackBufferError):
                raise
            raise TrackBufferError(f"invalid replay event: {exc}") from exc


def validate_track_snapshot_runtime(snapshot: Mapping[str, Any], *, simulation_clock: str) -> None:
    """Structural + G11 + temporal/history checks; G11 alone is not sufficient."""
    try:
        validate_production_track_g11(snapshot)
        anchor_ns = parse_utc_ns(snapshot["anchor_timestamp"], field="anchor_timestamp")
        clock_ns = parse_utc_ns(simulation_clock, field="simulation_clock")
    except (KeyError, ReplayTimeError, ValueError, TypeError) as exc:
        raise TrackBufferError(f"TrackSnapshot validation failed: {exc}") from exc
    if anchor_ns > clock_ns:
        raise TrackBufferError("TrackSnapshot anchor exceeds simulation clock")
    status = snapshot.get("data_status")
    history = snapshot.get("history")
    if status not in ("VALID", "INSUFFICIENT_DATA", "STALE", "INVALID_DATA") or not isinstance(history, list):
        raise TrackBufferError("TrackSnapshot status/history is invalid")
    expected_grid = [anchor_ns + offset * MINUTE for offset in HISTORY_OFFSETS]
    actual_grid: list[int] = []
    for point in history:
        try:
            nominal_ns = parse_utc_ns(point["nominal_timestamp"], field="nominal_timestamp")
            selected_ns = parse_utc_ns(point["source_timestamp"], field="source_timestamp")
            age = float(point["source_age_seconds"])
        except (KeyError, TypeError, ValueError, ReplayTimeError) as exc:
            raise TrackBufferError(f"invalid as-of history point: {exc}") from exc
        if nominal_ns > anchor_ns or nominal_ns > clock_ns or selected_ns > nominal_ns:
            raise TrackBufferError("history contains a future nominal/source timestamp")
        if not math.isfinite(age) or not 0 <= age <= 60 or abs((nominal_ns - selected_ns) / NSEC - age) > 1e-9:
            raise TrackBufferError("history age must equal as-of age in [0,60] seconds")
        if nominal_ns not in expected_grid:
            raise TrackBufferError("history nominal timestamp is outside the anchor grid")
        actual_grid.append(nominal_ns)
    if actual_grid != sorted(set(actual_grid)):
        raise TrackBufferError("history points must be unique and ordered")
    if status == "VALID":
        if actual_grid != expected_grid or len(history) != 10:
            raise TrackBufferError("VALID TrackSnapshot requires exactly ten anchor-grid points")
        if snapshot.get("current_state") != history[-1]:
            raise TrackBufferError("current_state must equal the last history point")
    elif snapshot.get("current_state") is not None:
        raise TrackBufferError("non-VALID TrackSnapshot must not expose a current_state")
