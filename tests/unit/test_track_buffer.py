from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data.replay_time import parse_utc_ns, utc_iso_ns
from src.data.track_buffer import TrackBuffer, TrackBufferError, validate_track_snapshot_runtime


SESSION = "123e4567-e89b-12d3-a456-426614174000"
ANCHOR = "2024-11-01T00:09:00Z"
FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "t09_ais_rows.json").read_text(encoding="utf-8"))


def verifier(event):
    return event.get("provenance", {}).get("source_file") == "t09-fixture.csv" and event.get("mmsi") == "338443451"


def event_at(timestamp, *, row_num=20, vessel_id="physical_mmsi:338443451", **fields):
    value = {
        "timestamp_utc": timestamp, "vessel_id": vessel_id, "mmsi": "338443451",
        "source_type": "REAL_AIS", "is_simulated": False,
        "latitude": 41.7, "longitude": -71.4, "sog_kn": 4.0, "cog_deg": 90.0,
        "provenance": {"source_file": "t09-fixture.csv", "source_row": row_num},
    }
    value.update(fields)
    return value


def new_buffer(**kwargs):
    return TrackBuffer(SESSION, identity_verifier=verifier, **kwargs)


def fixture_events():
    return [
        {"timestamp_utc": row["timestamp_utc"], "vessel_id": "physical_mmsi:338443451",
         "mmsi": row["mmsi"], "source_type": "REAL_AIS", "is_simulated": False,
         "latitude": row["latitude"], "longitude": row["longitude"],
         "sog_kn": row["sog"], "cog_deg": row["cog"],
         "provenance": {"source_file": row["source_file"], "source_row": row["source_row"]}}
        for row in FIXTURE
    ]


def test_session_bound_buffer_and_future_safe_valid_snapshot():
    buffer = new_buffer()
    for item in reversed(fixture_events()):
        buffer.ingest(item, session_id=SESSION)
    with pytest.raises(TrackBufferError, match="different replay session"):
        buffer.ingest(fixture_events()[0], session_id="another-session")
    future = event_at("2024-11-01T00:10:00Z", row_num=11)
    buffer.ingest(future, session_id=SESSION)
    snapshot = buffer.snapshot("physical_mmsi:338443451", ANCHOR, simulation_clock=ANCHOR)
    assert snapshot["data_status"] == "VALID"
    assert len(snapshot["history"]) == 10
    assert snapshot["current_state"] == snapshot["history"][-1]
    assert all(point["source_timestamp"] <= point["nominal_timestamp"] <= ANCHOR for point in snapshot["history"])
    assert snapshot["history"][-1]["source_timestamp"] == ANCHOR
    assert snapshot["history"][-1]["latitude"] == FIXTURE[-1]["latitude"]
    validate_track_snapshot_runtime(snapshot, simulation_clock=ANCHOR)


@pytest.mark.parametrize("delay,status", [(0, "VALID"), (60, "VALID"), (61, "STALE")])
def test_asof_age_boundaries(delay, status):
    buffer = new_buffer()
    for offset in range(-9, -1):
        from src.data.replay_time import parse_utc_ns
        ts = parse_utc_ns(ANCHOR) + offset * 60 * 1_000_000_000
        buffer.ingest(event_at(utc_iso_ns(ts), row_num=offset + 11), session_id=SESSION)
    last = parse_utc_ns(ANCHOR) - delay * 1_000_000_000
    buffer.ingest(event_at(utc_iso_ns(last), row_num=30), session_id=SESSION)
    snapshot = buffer.snapshot("physical_mmsi:338443451", ANCHOR, simulation_clock=ANCHOR)
    assert snapshot["data_status"] == status
    if status == "VALID":
        assert snapshot["history"][-1]["source_age_seconds"] == delay
    else:
        assert snapshot["current_state"] is None


def test_missing_history_is_insufficient_and_unknown_vessel_is_empty():
    buffer = new_buffer()
    buffer.ingest(event_at(ANCHOR), session_id=SESSION)
    snapshot = buffer.snapshot("physical_mmsi:338443451", ANCHOR, simulation_clock=ANCHOR)
    assert snapshot["data_status"] == "INSUFFICIENT_DATA"
    assert len(snapshot["history"]) == 1
    assert snapshot["current_state"] is None
    assert buffer.snapshot("physical_mmsi:111111111", ANCHOR, simulation_clock=ANCHOR) is None


def test_invalid_marker_reports_invalid_without_emitting_bad_values():
    buffer = new_buffer()
    for item in fixture_events():
        buffer.ingest(item, session_id=SESSION)
    buffer.record_invalid("physical_mmsi:338443451", "2024-11-01T00:09:00Z",
                          "invalid source quality flag", session_id=SESSION)
    result = buffer.snapshot("physical_mmsi:338443451", ANCHOR, simulation_clock=ANCHOR)
    assert result["data_status"] == "INVALID_DATA"
    assert result["current_state"] is None


@pytest.mark.parametrize("timestamp", ["2024-11-01T00:00:00", "2024-11-01T07:00:00+07:00", "2024-11-01T00:00:00-00:00"])
def test_buffer_rejects_naive_unknown_or_non_utc(timestamp):
    with pytest.raises(TrackBufferError):
        new_buffer().ingest(event_at(timestamp), session_id=SESSION)


def test_event_qc_and_source_identity_fail_closed():
    with pytest.raises(TrackBufferError, match="not verified"):
        TrackBuffer(SESSION).ingest(event_at(ANCHOR), session_id=SESSION)
    for bad in [
        event_at(ANCHOR, mmsi="123", vessel_id="physical_mmsi:123"),
        event_at(ANCHOR, sog_kn=None),
        event_at(ANCHOR, cog_deg=360),
        event_at(ANCHOR, latitude=float("nan")),
    ]:
        with pytest.raises(TrackBufferError):
            new_buffer().ingest(bad, session_id=SESSION)


def test_out_of_order_tie_break_is_stable_and_bounded_retention():
    buffer = new_buffer(retention_seconds=600, max_events_per_vessel=3)
    first = event_at(ANCHOR, row_num=2, latitude=41.71)
    second = event_at(ANCHOR, row_num=1, latitude=41.72)
    buffer.ingest(first, session_id=SESSION)
    buffer.ingest(second, session_id=SESSION)
    buffer.ingest(event_at("2024-11-01T00:09:01Z", row_num=3), session_id=SESSION)
    with pytest.raises(TrackBufferError, match="capacity"):
        buffer.ingest(event_at("2024-11-01T00:09:02Z", row_num=4), session_id=SESSION)
    # Source row 1 wins deterministic same-timestamp ordering as the latest as-of record.
    snap = buffer.snapshot("physical_mmsi:338443451", ANCHOR, simulation_clock="2024-11-01T00:09:01Z")
    assert snap["history"][-1]["latitude"] == 41.72


def test_selected_source_time_controls_asof_original_timestamp_is_provenance_only():
    buffer = new_buffer()
    for index, item in enumerate(fixture_events()):
        item["vessel_id"] = "simulated:fixture:ship-1"
        item["mmsi"] = None
        item["source_type"] = "SYNTHETIC_AIS"
        item["is_simulated"] = True
        item["original_source_timestamp"] = "2024-11-01T00:15:00Z" if index == 9 else item["timestamp_utc"]
        buffer.ingest(item, session_id=SESSION)
    snap = buffer.snapshot("simulated:fixture:ship-1", ANCHOR, simulation_clock=ANCHOR)
    assert snap["data_status"] == "VALID"
    assert snap["history"][-1]["source_timestamp"] == ANCHOR
    assert snap["history"][-1]["original_source_timestamp"] == "2024-11-01T00:15:00Z"


def test_missing_synthetic_original_timestamp_stays_null():
    sample = event_at(
        ANCHOR,
        vessel_id="simulated:fixture:missing-parent-time",
        mmsi=None,
        source_type="SYNTHETIC_AIS",
        is_simulated=True,
    )
    sample.pop("original_source_timestamp", None)
    buffer = TrackBuffer(SESSION)
    buffer.ingest(sample, session_id=SESSION)

    snapshot = buffer.snapshot(sample["vessel_id"], ANCHOR, simulation_clock=ANCHOR)

    assert snapshot["data_status"] == "INSUFFICIENT_DATA"
    assert snapshot["history"][0]["source_timestamp"] == ANCHOR
    assert snapshot["history"][0]["original_source_timestamp"] is None
    assert snapshot["current_state"] is None


def test_invalid_original_source_timestamp_is_rejected():
    sample = event_at(
        ANCHOR,
        vessel_id="simulated:fixture:invalid-parent-time",
        mmsi=None,
        source_type="SYNTHETIC_AIS",
        is_simulated=True,
        original_source_timestamp="not-a-utc-timestamp",
    )
    with pytest.raises(TrackBufferError, match="original_source_timestamp"):
        TrackBuffer(SESSION).ingest(sample, session_id=SESSION)


def test_real_ais_original_source_timestamp_must_match_selected_timestamp():
    sample = event_at(ANCHOR, original_source_timestamp="2024-11-01T00:08:00Z")
    with pytest.raises(TrackBufferError, match="REAL_AIS original and selected"):
        new_buffer().ingest(sample, session_id=SESSION)


def test_nanosecond_timestamps_are_preserved_and_future_anchor_rejected():
    stamp = "2024-11-01T00:09:00.123456789Z"
    assert utc_iso_ns(parse_utc_ns(stamp)) == stamp
    buffer = new_buffer()
    buffer.ingest(event_at(ANCHOR), session_id=SESSION)
    with pytest.raises(TrackBufferError, match="simulation clock"):
        buffer.snapshot("physical_mmsi:338443451", "2024-11-01T00:09:01Z",
                        simulation_clock=ANCHOR)


def test_future_invalid_marker_does_not_leak_back_to_earlier_anchor():
    buffer = new_buffer()
    for item in fixture_events():
        buffer.ingest(item, session_id=SESSION)
    buffer.record_invalid("physical_mmsi:338443451", "2024-11-01T00:09:01Z",
                          "future invalid point", session_id=SESSION)
    snapshot = buffer.snapshot("physical_mmsi:338443451", ANCHOR, simulation_clock=ANCHOR)
    assert snapshot["data_status"] == "VALID"


def test_nfc_simulated_id_and_synthetic_physical_mmsi_semantics():
    decomposed = "simulated:fixture:cafe\u0301-1"
    sample = event_at(ANCHOR, vessel_id=decomposed, mmsi=None,
                      source_type="SYNTHETIC_AIS", is_simulated=True)
    sample["provenance"] = {"source_file": "t09-fixture.csv", "source_row": 1}
    buffer = new_buffer()
    canonical = buffer.ingest(sample, session_id=SESSION)
    assert canonical == "simulated:fixture:caf\u00e9-1"
    snap = buffer.snapshot(canonical, ANCHOR, simulation_clock=ANCHOR)
    assert snap["vessel_id"] == canonical and snap["is_simulated"] is True

    physical_synthetic = event_at(ANCHOR, vessel_id="physical_mmsi:338443451", row_num=2,
                                  source_type="SYNTHETIC_AIS", is_simulated=True)
    accepted = new_buffer().ingest(physical_synthetic, session_id=SESSION)
    assert accepted == "physical_mmsi:338443451"
