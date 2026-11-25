from __future__ import annotations

import json
from datetime import datetime
import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from jsonschema import Draft202012Validator
import pytest

from src.data.ais_replay import run_replay
from src.data.replay_session_core import ReplaySessionCore
from src.data.track_semantics import validate_production_track_g11


FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "t09_ais_rows.json").read_text(encoding="utf-8"))
SCHEMA = pa.schema([
    ("mmsi", pa.string()), ("timestamp_utc", pa.timestamp("ns", tz="UTC")),
    ("latitude", pa.float64()), ("longitude", pa.float64()), ("sog", pa.float64()), ("cog", pa.float64()),
    ("flag_invalid_mmsi", pa.bool_()), ("flag_invalid_timestamp", pa.bool_()),
    ("flag_off_date", pa.bool_()), ("flag_invalid_position", pa.bool_()),
    ("flag_invalid_sog", pa.bool_()), ("flag_invalid_cog", pa.bool_()),
    ("flag_core_valid", pa.bool_()), ("source_file", pa.string()), ("source_row", pa.int64()),
])


def verified(event):
    return event["mmsi"] == "338443451" and event["provenance"]["source_file"] == "t09-fixture.csv"


def test_t08_ordered_parquet_events_build_g11_snapshot_and_reset_isolated(tmp_path):
    source = tmp_path / "ais_cleaned" / "year=2024" / "month=11" / "day=01" / "part-00000.parquet"
    source.parent.mkdir(parents=True)
    table_rows = []
    for row in FIXTURE:
        row = dict(row)
        row["timestamp_utc"] = datetime.fromisoformat(row["timestamp_utc"].replace("Z", "+00:00"))
        table_rows.append(row)
    table = pa.Table.from_pylist(table_rows, schema=SCHEMA)
    pq.write_table(table, source, row_group_size=3)

    ordered = []
    qc = run_replay(source_root=source.parents[3], start="2024-11-01T00:00:00Z",
                    end="2024-11-01T00:10:00Z", emit=ordered.append,
                    max_events=100, batch_size=4)
    assert qc["complete_window"] and qc["accepted_events"] == 10
    assert [event["timestamp_utc"] for event in ordered] == sorted(event["timestamp_utc"] for event in ordered)

    core = ReplaySessionCore(identity_verifier=verified)
    session = core.create("fixture-source", "2024-11-01T00:00:00Z", "2024-11-01T00:10:00Z",
                          start_time="2024-11-01T00:09:00Z")
    for event in ordered:
        core.ingest(session.session_id, event)
    snapshot = core.snapshot(session.session_id, "physical_mmsi:338443451")
    assert snapshot["data_status"] == "VALID" and len(snapshot["history"]) == 10
    assert snapshot["history"][-1]["source_timestamp"] == session.simulation_time
    validate_production_track_g11(snapshot)
    contracts = Path(__file__).parents[2] / "contracts"
    Draft202012Validator.check_schema(json.loads((contracts / "track_snapshot.schema.json").read_text(encoding="utf-8")))

    reset = core.control(session.session_id, "RESET", expected_version=0, idempotency_key="integration-reset")
    assert core.get(session.session_id).status == "ENDED"
    assert core.get(reset.session_id).status == "READY" and reset.version == 0
    assert core.snapshot(reset.session_id, "physical_mmsi:338443451") is None
    assert core.snapshot(session.session_id, "physical_mmsi:338443451")["data_status"] == "VALID"


def test_controlled_real_ais_slice_reaches_t09_without_future_leakage():
    default_root = Path(__file__).resolve().parents[3] / "maritime-ais-system" / "data" / "processed" / "ais_cleaned"
    source_root = Path(os.environ.get("AIS_REPLAY_ROOT", str(default_root)))
    if not source_root.is_dir():
        pytest.skip("cleaned AIS source is not present in this environment")
    ordered = []
    qc = run_replay(source_root=source_root, start="2024-11-01T00:00:00Z",
                    end="2024-11-01T00:00:15Z", mmsi_filter=["338443451"],
                    emit=ordered.append, max_events=5, batch_size=1024)
    assert qc["complete_window"] and qc["accepted_events"] == 1

    def test_only_source_gate(event):
        # Test hook validates the known slice mapping; it is not a production
        # vessel-ownership or source-authority attestation.
        return (event.get("mmsi") == "338443451"
                and event.get("provenance", {}).get("source_file") == "ais-2024-11-01.tgz")

    core = ReplaySessionCore(identity_verifier=test_only_source_gate)
    session = core.create("cleaned-ais-test-slice", "2024-11-01T00:00:00Z",
                          "2024-11-01T00:10:00Z", start_time="2024-11-01T00:00:15Z")
    for event in ordered:
        core.ingest(session.session_id, event)
    snapshot = core.snapshot(session.session_id, "physical_mmsi:338443451")
    assert snapshot["data_status"] == "INSUFFICIENT_DATA"
    assert len(snapshot["history"]) == 1
    assert snapshot["history"][0]["source_timestamp"] == "2024-11-01T00:00:01Z"
    assert snapshot["history"][0]["source_timestamp"] <= snapshot["history"][0]["nominal_timestamp"]
