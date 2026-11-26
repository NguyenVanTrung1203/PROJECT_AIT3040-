"""Bounded-memory reader and Contract V1 QC for cleaned daily AIS Parquet.

The reader never writes to the source tree. It sorts selected events through
temporary external merge runs so source row order cannot leak into replay order.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from itertools import groupby
import heapq
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

UTC = timezone.utc
MMSI_RE = re.compile(r"^[0-9]{9}$", re.ASCII)
REQUIRED_COLUMNS = (
    "mmsi", "timestamp_utc", "latitude", "longitude", "sog", "cog",
    "flag_invalid_mmsi", "flag_invalid_timestamp", "flag_off_date",
    "flag_invalid_position", "flag_invalid_sog", "flag_invalid_cog",
    "flag_core_valid", "source_file", "source_row",
)
EQUALITY_FIELDS = ("latitude", "longitude", "sog", "cog")
QUALITY_FLAGS = (
    "flag_invalid_mmsi", "flag_invalid_timestamp", "flag_off_date",
    "flag_invalid_position", "flag_invalid_sog", "flag_invalid_cog",
    "flag_core_valid",
)
_UNIT_NS = {"s": 1_000_000_000, "ms": 1_000_000, "us": 1_000, "ns": 1}
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class ReplayInputError(ValueError):
    """Source/configuration cannot safely be interpreted as Contract V1 input."""


def parse_utc(value: str | datetime, *, field: str = "timestamp") -> datetime:
    """Parse only an explicit zero-offset timestamp; never assume UTC for naive input."""
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith("-00:00"):
            raise ReplayInputError(f"{field} must carry a known UTC offset")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            value = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ReplayInputError(f"{field} must be an ISO-8601 UTC timestamp") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ReplayInputError(f"{field} must carry an explicit UTC offset")
    return value.astimezone(UTC)


def datetime_to_ns(value: datetime) -> int:
    value = parse_utc(value)
    delta = value - _EPOCH
    return ((delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds) * 1000


def ns_to_utc_iso(value: int) -> str:
    seconds, nanos = divmod(int(value), 1_000_000_000)
    stamp = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    fraction = f".{nanos:09d}".rstrip("0") if nanos else ""
    return f"{stamp}{fraction}Z"


def _ns_to_datetime(value: int) -> datetime:
    seconds, nanos = divmod(int(value), 1_000_000_000)
    return datetime.fromtimestamp(seconds, UTC).replace(microsecond=nanos // 1000)


def _arrow_timestamp_ns(values: pa.Array, unit: str) -> list[int | None]:
    raw = pc.cast(values, pa.int64()).to_pylist()
    scale = _UNIT_NS[unit]
    return [None if item is None else int(item) * scale for item in raw]


def _sort_key(row: Mapping[str, Any]) -> tuple[int, bytes, bytes, int]:
    return (int(row["_timestamp_ns"]), row["mmsi"].encode("ascii"),
            row["source_file"].encode("utf-8"), int(row["source_row"]))


def _duplicate_key(row: Mapping[str, Any]) -> tuple[int, str]:
    return int(row["_timestamp_ns"]), str(row["mmsi"])


def _same_event_payload(first: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    # D-03 equality is scoped to the fields consumed by TrackSnapshot. Source
    # metadata confirms key/order, but not a wider equality set; see T08 report.
    return all(first[field] == row[field] for field in EQUALITY_FIELDS)


def _load_json_lines(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line:
                yield json.loads(line)


def _write_json_line(stream, row: Mapping[str, Any]) -> None:
    stream.write(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False))
    stream.write("\n")


def _merge_run_group(paths: list[Path], target: Path) -> None:
    streams = [path.open("r", encoding="utf-8") for path in paths]
    try:
        heap: list[tuple[tuple[int, bytes, bytes, int], int, dict[str, Any]]] = []
        for index, stream in enumerate(streams):
            line = stream.readline()
            if line:
                row = json.loads(line)
                heapq.heappush(heap, (_sort_key(row), index, row))
        with target.open("w", encoding="utf-8", newline="\n") as output:
            while heap:
                _, index, row = heapq.heappop(heap)
                _write_json_line(output, row)
                line = streams[index].readline()
                if line:
                    next_row = json.loads(line)
                    heapq.heappush(heap, (_sort_key(next_row), index, next_row))
    finally:
        for stream in streams:
            stream.close()


def _external_sorted_rows(rows: Iterable[dict[str, Any]], workspace: Path,
                          chunk_rows: int, merge_fan_in: int = 48) -> Iterator[dict[str, Any]]:
    runs: list[Path] = []
    chunk: list[dict[str, Any]] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= chunk_rows:
            runs.append(_flush_run(chunk, workspace, len(runs)))
            chunk = []
    if chunk:
        runs.append(_flush_run(chunk, workspace, len(runs)))
    if not runs:
        return

    round_index = 0
    while len(runs) > merge_fan_in:
        merged: list[Path] = []
        for offset in range(0, len(runs), merge_fan_in):
            group = runs[offset:offset + merge_fan_in]
            target = workspace / f"merge-{round_index:03d}-{len(merged):06d}.jsonl"
            _merge_run_group(group, target)
            for path in group:
                path.unlink()
            merged.append(target)
        runs = merged
        round_index += 1

    final = workspace / f"merge-{round_index:03d}-final.jsonl"
    _merge_run_group(runs, final)
    for path in runs:
        path.unlink()
    yield from _load_json_lines(final)


def _flush_run(chunk: list[dict[str, Any]], workspace: Path, run_number: int) -> Path:
    chunk.sort(key=_sort_key)
    path = workspace / f"run-{run_number:06d}.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for row in chunk:
            _write_json_line(output, row)
    return path


def _day_paths(root: Path, start: datetime, end: datetime) -> Iterator[Path]:
    day = start.date()
    last = (end - timedelta(microseconds=1)).date()
    while day <= last:
        yield root / f"year={day.year:04d}" / f"month={day.month:02d}" / f"day={day.day:02d}" / "part-00000.parquet"
        day += timedelta(days=1)


def _row_group_overlaps(parquet: pq.ParquetFile, row_group: int,
                        timestamp_index: int, unit: str, start_ns: int,
                        end_ns: int) -> bool:
    stats = parquet.metadata.row_group(row_group).column(timestamp_index).statistics
    if stats is None or not stats.has_min_max or stats.min is None or stats.max is None:
        return True
    try:
        lower = datetime_to_ns(stats.min)
        upper = datetime_to_ns(stats.max)
    except (ReplayInputError, TypeError, ValueError, OverflowError):
        return True
    # Parquet statistics are inclusive; requested replay window is [start,end).
    return upper >= start_ns and lower < end_ns


def _iter_source_rows(source_root: Path, start_ns: int, end_ns: int,
                      mmsi_filter: frozenset[str] | None, batch_size: int,
                      stats: dict[str, Any]) -> Iterator[dict[str, Any]]:
    start = _ns_to_datetime(start_ns)
    end = _ns_to_datetime(end_ns)
    for path in _day_paths(source_root, start, end):
        if not path.is_file():
            stats["missing_partitions"].append(path.relative_to(source_root).as_posix())
            continue
        try:
            parquet = pq.ParquetFile(path)
        except Exception as exc:
            raise ReplayInputError(f"cannot read Parquet partition {path.name}: {exc}") from exc
        schema = parquet.schema_arrow
        missing = sorted(set(REQUIRED_COLUMNS) - set(schema.names))
        if missing:
            raise ReplayInputError(f"{path.name} is missing required columns: {', '.join(missing)}")
        timestamp_type = schema.field("timestamp_utc").type
        if not pa.types.is_timestamp(timestamp_type) or timestamp_type.tz != "UTC":
            raise ReplayInputError(f"{path.name}: timestamp_utc must be timezone-aware Arrow UTC")
        if timestamp_type.unit not in _UNIT_NS:
            raise ReplayInputError(f"{path.name}: unsupported timestamp unit {timestamp_type.unit}")
        for name in QUALITY_FLAGS:
            if not pa.types.is_boolean(schema.field(name).type):
                raise ReplayInputError(f"{path.name}: {name} must be boolean")
        if schema.field("mmsi").type not in (pa.string(), pa.large_string()):
            raise ReplayInputError(f"{path.name}: mmsi must be stored as text")
        if not pa.types.is_string(schema.field("source_file").type) and not pa.types.is_large_string(schema.field("source_file").type):
            raise ReplayInputError(f"{path.name}: source_file must be text")
        if not pa.types.is_integer(schema.field("source_row").type):
            raise ReplayInputError(f"{path.name}: source_row must be integer")

        column_indexes = {name: schema.get_field_index(name) for name in REQUIRED_COLUMNS}
        timestamp_index = schema.get_field_index("timestamp_utc")
        for row_group in range(parquet.metadata.num_row_groups):
            stats["row_groups_total"] += 1
            if not _row_group_overlaps(parquet, row_group, timestamp_index,
                                       timestamp_type.unit, start_ns, end_ns):
                stats["row_groups_pruned"] += 1
                continue
            stats["row_groups_read"] += 1
            iterator = parquet.iter_batches(batch_size=batch_size, row_groups=[row_group],
                                             columns=list(REQUIRED_COLUMNS), use_threads=False)
            for batch in iterator:
                stats["rows_read"] += batch.num_rows
                values = {name: batch.column(batch.schema.get_field_index(name)).to_pylist()
                          for name in REQUIRED_COLUMNS if name != "timestamp_utc"}
                timestamp_ns = _arrow_timestamp_ns(batch.column(batch.schema.get_field_index("timestamp_utc")), timestamp_type.unit)
                for i in range(batch.num_rows):
                    ns = timestamp_ns[i]
                    if ns is None:
                        stats["unfilterable_timestamp_rows"] += 1
                        _reject(stats, ["invalid_timestamp"])
                        continue
                    if ns < start_ns or ns >= end_ns:
                        stats["outside_window_rows"] += 1
                        continue
                    mmsi = values["mmsi"][i]
                    if mmsi_filter is not None and mmsi not in mmsi_filter:
                        stats["source_filter_rows"] += 1
                        continue
                    if not isinstance(mmsi, str) or MMSI_RE.fullmatch(mmsi) is None:
                        _reject(stats, ["invalid_mmsi"])
                        continue
                    source_file, source_row = values["source_file"][i], values["source_row"][i]
                    if not isinstance(source_file, str) or not source_file.strip() or not isinstance(source_row, int) or source_row < 1:
                        _reject(stats, ["missing_or_invalid_provenance"])
                        continue
                    row: dict[str, Any] = {
                        "_timestamp_ns": ns,
                        "mmsi": mmsi,
                        "latitude": values["latitude"][i],
                        "longitude": values["longitude"][i],
                        "sog": values["sog"][i],
                        "cog": values["cog"][i],
                        "source_file": source_file,
                        "source_row": source_row,
                    }
                    for flag in QUALITY_FLAGS:
                        row[flag] = values[flag][i]
                    stats["window_rows_with_identity_and_provenance"] += 1
                    yield row


def _reject(stats: dict[str, Any], reasons: Iterable[str]) -> None:
    unique = set(reasons)
    if unique:
        stats["rejected_rows"] += 1
        for reason in unique:
            stats["rejection_reasons"][reason] += 1


def _validate_event(row: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for flag in QUALITY_FLAGS:
        value = row.get(flag)
        if not isinstance(value, bool):
            reasons.append(f"missing_quality_flag:{flag}")
        elif flag.startswith("flag_invalid_") and value:
            reasons.append(f"quality_flag:{flag}")
        elif flag == "flag_off_date" and value:
            reasons.append("quality_flag:flag_off_date")
        elif flag == "flag_core_valid" and not value:
            reasons.append("quality_flag:flag_core_valid")

    for field, low, high, upper_inclusive in (
        ("latitude", -90.0, 90.0, True), ("longitude", -180.0, 180.0, True),
        ("sog", 0.0, 50.0, True), ("cog", 0.0, 360.0, False),
    ):
        value = row.get(field)
        if value is None or isinstance(value, bool):
            reasons.append(f"invalid_{field}")
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            reasons.append(f"invalid_{field}")
            continue
        if not math.isfinite(numeric) or numeric < low or numeric > high or (not upper_inclusive and numeric >= high):
            reasons.append(f"invalid_{field}")
    return reasons


def _event_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "vessel_id": f"physical_mmsi:{row['mmsi']}",
        "mmsi": row["mmsi"],
        "source_type": "REAL_AIS",
        "is_simulated": False,
        "timestamp_utc": ns_to_utc_iso(row["_timestamp_ns"]),
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "sog_kn": float(row["sog"]),
        "cog_deg": float(row["cog"]),
        "provenance": {"source_file": row["source_file"], "source_row": int(row["source_row"])},
    }


def run_replay(*, source_root: str | Path, start: str | datetime, end: str | datetime,
               emit: Callable[[dict[str, Any]], None], mmsi_filter: Iterable[str] | None = None,
               max_events: int = 10_000, batch_size: int = 8_192,
               temp_root: str | Path | None = None) -> dict[str, Any]:
    """Read, QC, stable-deduplicate and emit ordered events with bounded memory.

    The time window is half-open [start,end). `max_events` caps emitted output;
    the entire selected window is still scanned so ordering and QC summary are
    complete. Temporary sort runs are removed on success or failure.
    """
    start_utc, end_utc = parse_utc(start, field="start"), parse_utc(end, field="end")
    if end_utc <= start_utc:
        raise ReplayInputError("end must be later than start")
    if max_events < 1 or batch_size < 1:
        raise ReplayInputError("max_events and batch_size must be positive")
    normalized_filter = None
    if mmsi_filter is not None:
        normalized_filter = frozenset(mmsi_filter)
        invalid = [value for value in normalized_filter if not isinstance(value, str) or MMSI_RE.fullmatch(value) is None]
        if invalid:
            raise ReplayInputError("MMSI filters must contain exactly nine ASCII digits")

    root = Path(source_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ReplayInputError("source_root must be a directory")
    start_ns, end_ns = datetime_to_ns(start_utc), datetime_to_ns(end_utc)
    stats: dict[str, Any] = {
        "source_root": str(root),
        "window_start_utc": ns_to_utc_iso(start_ns),
        "window_end_utc_exclusive": ns_to_utc_iso(end_ns),
        "mmsi_filter": sorted(normalized_filter) if normalized_filter is not None else None,
        "max_events": max_events,
        "batch_size": batch_size,
        "row_groups_total": 0, "row_groups_read": 0, "row_groups_pruned": 0,
        "rows_read": 0, "outside_window_rows": 0, "source_filter_rows": 0,
        "unfilterable_timestamp_rows": 0, "window_rows_with_identity_and_provenance": 0,
        "rejected_rows": 0, "rejection_reasons": Counter(),
        "duplicate_groups_identical": 0, "duplicate_rows_identical_dropped": 0,
        "duplicate_groups_conflicting": 0, "duplicate_rows_conflicting_dropped": 0,
        "accepted_events": 0, "events_written": 0, "missing_partitions": [],
        "duplicate_equality_fields": ["latitude", "longitude", "sog", "cog"],
        "stable_duplicate_order": ["source_file ASC", "source_row ASC"],
    }
    temp_parent = Path(temp_root).expanduser().resolve() if temp_root is not None else None
    if temp_parent is not None:
        temp_parent.mkdir(parents=True, exist_ok=True)
        if temp_parent == root or root in temp_parent.parents:
            raise ReplayInputError("temporary sort directory must be outside source_root")

    with tempfile.TemporaryDirectory(prefix="ait3040-ais-replay-", dir=temp_parent) as tmp:
        workspace = Path(tmp)
        source_rows = _iter_source_rows(root, start_ns, end_ns, normalized_filter, batch_size, stats)
        sorted_rows = _external_sorted_rows(source_rows, workspace, batch_size)
        row_groups = groupby(sorted_rows, key=_duplicate_key)
        for _, records in row_groups:
            first: dict[str, Any] | None = None
            count = 0
            conflict = False
            for record in records:
                if first is None:
                    first = record
                elif not _same_event_payload(first, record):
                    conflict = True
                count += 1
            if first is None:
                continue
            if count > 1 and conflict:
                stats["duplicate_groups_conflicting"] += 1
                stats["duplicate_rows_conflicting_dropped"] += count
                _reject(stats, ["duplicate_conflict"])
                # The counter records conflicting rows, including rows beyond
                # the one group-level rejection record above.
                stats["rejected_rows"] += count - 1
                stats["rejection_reasons"]["duplicate_conflict"] += count - 1
                continue
            if count > 1:
                stats["duplicate_groups_identical"] += 1
                stats["duplicate_rows_identical_dropped"] += count - 1
            reasons = _validate_event(first)
            if reasons:
                _reject(stats, reasons)
                continue
            event = _event_from_row(first)
            stats["accepted_events"] += 1
            if stats["events_written"] < max_events:
                emit(event)
                stats["events_written"] += 1

    stats["rejection_reasons"] = dict(sorted(stats["rejection_reasons"].items()))
    stats["missing_partitions"] = sorted(stats["missing_partitions"])
    stats["complete_window"] = not stats["missing_partitions"]
    return stats


def build_production_track_snapshot(events: Iterable[Mapping[str, Any]], *, anchor: str | datetime) -> dict[str, Any]:
    """Build one complete 10-point REAL_AIS snapshot and enforce G11 at boundary.

    This narrow adapter does not buffer events, interpolate, or emit partial
    TrackSnapshots. T09 owns long-lived buffer/session lifecycle.
    """
    from src.data.track_semantics import validate_production_track_g11

    anchor_utc = parse_utc(anchor, field="anchor")
    rows = list(events)
    if not rows:
        raise ReplayInputError("cannot create TrackSnapshot from empty history")
    mmsis = {row.get("mmsi") for row in rows}
    vessel_ids = {row.get("vessel_id") for row in rows}
    if len(mmsis) != 1 or len(vessel_ids) != 1:
        raise ReplayInputError("TrackSnapshot input must contain exactly one physical MMSI identity")
    mmsi = next(iter(mmsis))
    if not isinstance(mmsi, str) or MMSI_RE.fullmatch(mmsi) is None or next(iter(vessel_ids)) != f"physical_mmsi:{mmsi}":
        raise ReplayInputError("event physical identity must exactly match its nine-digit MMSI")

    indexed: list[tuple[int, Mapping[str, Any]]] = []
    for row in rows:
        source = parse_utc(row.get("timestamp_utc"), field="event timestamp")
        if row.get("source_type") != "REAL_AIS" or row.get("is_simulated") is not False:
            raise ReplayInputError("cleaned physical AIS events require REAL_AIS and is_simulated=false")
        indexed.append((datetime_to_ns(source), row))
    indexed.sort(key=lambda pair: (pair[0], pair[1]["provenance"]["source_file"].encode("utf-8"),
                                   int(pair[1]["provenance"]["source_row"])))
    anchor_ns = datetime_to_ns(anchor_utc)
    history: list[dict[str, Any]] = []
    for offset in range(-9, 1):
        nominal_ns = anchor_ns + offset * 60 * 1_000_000_000
        eligible = [(source_ns, row) for source_ns, row in indexed
                    if source_ns <= nominal_ns and nominal_ns - source_ns <= 60 * 1_000_000_000]
        if not eligible:
            raise ReplayInputError(f"no as-of AIS event within 60 seconds for minute offset {offset}")
        source_ns, selected = eligible[-1]
        history.append({
            "nominal_timestamp": ns_to_utc_iso(nominal_ns),
            "source_timestamp": ns_to_utc_iso(source_ns),
            "original_source_timestamp": ns_to_utc_iso(source_ns),
            "latitude": selected["latitude"], "longitude": selected["longitude"],
            "sog_kn": selected["sog_kn"], "cog_deg": selected["cog_deg"],
            "source_age_seconds": (nominal_ns - source_ns) / 1_000_000_000,
        })
    snapshot: dict[str, Any] = {
        "schema_version": "1.0.0", "vessel_id": f"physical_mmsi:{mmsi}", "mmsi": mmsi,
        "source_type": "REAL_AIS", "is_simulated": False,
        "anchor_timestamp": ns_to_utc_iso(anchor_ns), "current_state": history[-1],
        "history": history, "data_status": "VALID",
    }
    validate_track_snapshot_temporal(snapshot)
    validate_production_track_g11(snapshot)
    return snapshot


def validate_track_snapshot_temporal(snapshot: Mapping[str, Any]) -> None:
    """Runtime temporal checks complementary to production schema + G11."""
    anchor = datetime_to_ns(parse_utc(snapshot.get("anchor_timestamp"), field="anchor_timestamp"))
    history = snapshot.get("history")
    if not isinstance(history, list) or len(history) != 10 or snapshot.get("data_status") != "VALID":
        raise ReplayInputError("production VALID TrackSnapshot requires ten history points")
    expected = [anchor + offset * 60 * 1_000_000_000 for offset in range(-9, 1)]
    actual: list[int] = []
    for point in history:
        nominal = datetime_to_ns(parse_utc(point.get("nominal_timestamp"), field="nominal_timestamp"))
        source = datetime_to_ns(parse_utc(point.get("source_timestamp"), field="source_timestamp"))
        age = point.get("source_age_seconds")
        if nominal > anchor or source > nominal:
            raise ReplayInputError("TrackSnapshot history cannot contain future source/nominal timestamps")
        if age is None or not math.isfinite(float(age)) or abs((nominal - source) / 1e9 - float(age)) > 1e-6 or not 0 <= float(age) <= 60:
            raise ReplayInputError("TrackSnapshot source age must match as-of age in [0,60] seconds")
        actual.append(nominal)
    if actual != expected:
        raise ReplayInputError("TrackSnapshot nominal history must be the ordered anchor -9 through anchor grid")
    if snapshot.get("current_state") != history[-1]:
        raise ReplayInputError("current_state must equal the final history point")
