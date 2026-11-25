from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.data.ais_replay import (
    ReplayInputError,
    build_production_track_snapshot,
    parse_utc,
    run_replay,
)

UTC = timezone.utc
START = "2024-11-01T00:00:00Z"
END = "2024-11-01T00:02:00Z"
SCHEMA = pa.schema([
    ("mmsi", pa.string()), ("timestamp_utc", pa.timestamp("ns", tz="UTC")),
    ("latitude", pa.float64()), ("longitude", pa.float64()),
    ("sog", pa.float64()), ("cog", pa.float64()),
    ("flag_invalid_mmsi", pa.bool_()), ("flag_invalid_timestamp", pa.bool_()),
    ("flag_off_date", pa.bool_()), ("flag_invalid_position", pa.bool_()),
    ("flag_invalid_sog", pa.bool_()), ("flag_invalid_cog", pa.bool_()),
    ("flag_core_valid", pa.bool_()), ("source_file", pa.string()), ("source_row", pa.int64()),
])


def row(mmsi="123456789", timestamp="2024-11-01T00:00:01Z", *, latitude=10.0,
        longitude=20.0, sog=12.0, cog=90.0, source_file="ais.csv", source_row=1,
        **flags):
    ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if timestamp else None
    result = {
        "mmsi": mmsi, "timestamp_utc": ts, "latitude": latitude, "longitude": longitude,
        "sog": sog, "cog": cog, "flag_invalid_mmsi": False,
        "flag_invalid_timestamp": False, "flag_off_date": False,
        "flag_invalid_position": False, "flag_invalid_sog": False,
        "flag_invalid_cog": False, "flag_core_valid": True,
        "source_file": source_file, "source_row": source_row,
    }
    result.update(flags)
    return result


def write_source(root, rows, *, rows_per_group=2):
    target = root / "year=2024" / "month=11" / "day=01" / "part-00000.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    pq.write_table(table, target, row_group_size=rows_per_group)
    return target


def replay(root, rows, *, batch_size=2, **kwargs):
    write_source(root, rows)
    result = []
    report = run_replay(source_root=root, start=START, end=END, emit=result.append,
                        batch_size=batch_size, **kwargs)
    return result, report


def test_utc_requires_explicit_zero_offset():
    assert parse_utc("2024-11-01T00:00:00Z").isoformat() == "2024-11-01T00:00:00+00:00"
    with pytest.raises(ReplayInputError, match="explicit UTC"):
        parse_utc("2024-11-01T00:00:00")
    with pytest.raises(ReplayInputError, match="explicit UTC"):
        parse_utc("2024-11-01T01:00:00+01:00")
    with pytest.raises(ReplayInputError, match="known UTC offset"):
        parse_utc("2024-11-01T00:00:00-00:00")


def test_out_of_order_events_are_sorted_and_future_end_is_exclusive(tmp_path):
    rows = [
        row(timestamp="2024-11-01T00:00:40Z", source_row=2),
        row(timestamp="2024-11-01T00:00:10Z", mmsi="987654321", source_row=1),
        row(timestamp="2024-11-01T00:02:00Z", source_row=3),
        row(timestamp="2024-10-31T23:59:59Z", source_row=4),
    ]
    events, report = replay(tmp_path, rows)
    assert [(e["timestamp_utc"], e["mmsi"]) for e in events] == [
        ("2024-11-01T00:00:10Z", "987654321"),
        ("2024-11-01T00:00:40Z", "123456789"),
    ]
    assert report["outside_window_rows"] == 2


def test_identical_duplicates_keep_stable_first_provenance(tmp_path):
    rows = [
        row(source_file="z-file.csv", source_row=1),
        row(source_file="a-file.csv", source_row=9),
    ]
    events, report = replay(tmp_path, rows, batch_size=1)
    assert len(events) == 1
    assert events[0]["provenance"] == {"source_file": "a-file.csv", "source_row": 9}
    assert report["duplicate_groups_identical"] == 1
    assert report["duplicate_rows_identical_dropped"] == 1


def test_conflicting_duplicate_drops_entire_mmsi_timestamp_group(tmp_path):
    rows = [row(source_row=1), row(latitude=10.1, source_row=2),
            row(timestamp="2024-11-01T00:00:02Z", source_row=3)]
    events, report = replay(tmp_path, rows, batch_size=1)
    assert [event["timestamp_utc"] for event in events] == ["2024-11-01T00:00:02Z"]
    assert report["duplicate_groups_conflicting"] == 1
    assert report["duplicate_rows_conflicting_dropped"] == 2
    assert report["rejection_reasons"]["duplicate_conflict"] == 2


def test_mmsi_filter_source_quality_flags_and_null_motion_are_not_coerced(tmp_path):
    rows = [
        row(mmsi="123456789", source_row=1),
        row(mmsi="987654321", source_row=2),
        row(timestamp="2024-11-01T00:00:03Z", sog=None, cog=None, source_row=3),
        row(timestamp="2024-11-01T00:00:04Z", source_row=4, flag_invalid_position=True),
    ]
    events, report = replay(tmp_path, rows, mmsi_filter=["123456789"])
    assert [event["mmsi"] for event in events] == ["123456789"]
    assert events[0]["sog_kn"] == 12.0
    assert report["source_filter_rows"] == 1
    # Re-run without a filter to prove null SOG/COG is rejected, never made zero.
    events, report = replay(tmp_path, rows)
    assert all(event["sog_kn"] != 0 for event in events)
    assert report["rejection_reasons"]["invalid_sog"] == 1
    assert report["rejection_reasons"]["invalid_cog"] == 1
    assert report["rejection_reasons"]["quality_flag:flag_invalid_position"] == 1


def test_null_timestamp_is_counted_as_qc_rejection(tmp_path):
    _, report = replay(tmp_path, [row(timestamp=None)])
    assert report["unfilterable_timestamp_rows"] == 1
    assert report["rejected_rows"] == 1
    assert report["rejection_reasons"]["invalid_timestamp"] == 1


def test_empty_input_and_filter_outside_source_return_empty_summary(tmp_path):
    write_source(tmp_path, [])
    events = []
    report = run_replay(source_root=tmp_path, start=START, end=END,
                        mmsi_filter=["999999999"], emit=events.append)
    assert events == []
    assert report["accepted_events"] == 0
    assert report["complete_window"] is True


def test_max_events_caps_output_but_qc_scans_whole_window(tmp_path):
    rows = [row(timestamp=f"2024-11-01T00:00:{i:02d}Z", source_row=i + 1) for i in (1, 2, 3)]
    events, report = replay(tmp_path, rows, max_events=1, batch_size=1)
    assert len(events) == 1
    assert report["accepted_events"] == 3
    assert report["events_written"] == 1


def test_repeat_runs_are_deterministic_and_source_bytes_unchanged(tmp_path):
    source = write_source(tmp_path, [
        row(timestamp="2024-11-01T00:00:30Z", source_file="z.csv", source_row=2),
        row(timestamp="2024-11-01T00:00:10Z", source_file="a.csv", source_row=1),
    ])
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    def load(batch_size):
        result = []
        report = run_replay(source_root=tmp_path, start=START, end=END, emit=result.append,
                            batch_size=batch_size)
        return result, report

    first, report1 = load(1)
    second, report2 = load(2)
    assert first == second
    assert report1["accepted_events"] == report2["accepted_events"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_production_snapshot_boundary_runs_temporal_and_g11_validation():
    anchor = datetime(2024, 11, 1, 0, 9, tzinfo=UTC)
    events = []
    for index in range(10):
        stamp = anchor - timedelta(minutes=9 - index)
        events.append({
            "vessel_id": "physical_mmsi:123456789", "mmsi": "123456789",
            "source_type": "REAL_AIS", "is_simulated": False,
            "timestamp_utc": stamp.isoformat().replace("+00:00", "Z"),
            "latitude": 10.0 + index / 1000, "longitude": 20.0,
            "sog_kn": 12.0, "cog_deg": 90.0,
            "provenance": {"source_file": "ais.csv", "source_row": index + 1},
        })
    snapshot = build_production_track_snapshot(events, anchor=anchor)
    assert snapshot["data_status"] == "VALID"
    assert len(snapshot["history"]) == 10
    assert snapshot["current_state"] == snapshot["history"][-1]
    assert all(point["source_timestamp"] <= point["nominal_timestamp"] for point in snapshot["history"])


def test_production_snapshot_rejects_future_only_history():
    anchor = datetime(2024, 11, 1, 0, 9, tzinfo=UTC)
    events = [{
        "vessel_id": "physical_mmsi:123456789", "mmsi": "123456789",
        "source_type": "REAL_AIS", "is_simulated": False,
        "timestamp_utc": (anchor + timedelta(seconds=1)).isoformat(),
        "latitude": 10.0, "longitude": 20.0, "sog_kn": 1.0, "cog_deg": 0.0,
        "provenance": {"source_file": "ais.csv", "source_row": 1},
    }]
    with pytest.raises(ReplayInputError, match="no as-of AIS event"):
        build_production_track_snapshot(events, anchor=anchor)
