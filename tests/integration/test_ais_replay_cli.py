from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc


def _write_partition(root: Path) -> Path:
    path = root / "year=2024" / "month=11" / "day=01" / "part-00000.parquet"
    path.parent.mkdir(parents=True)
    schema = pa.schema([
        ("mmsi", pa.string()), ("timestamp_utc", pa.timestamp("ns", tz="UTC")),
        ("latitude", pa.float64()), ("longitude", pa.float64()),
        ("sog", pa.float64()), ("cog", pa.float64()),
        ("flag_invalid_mmsi", pa.bool_()), ("flag_invalid_timestamp", pa.bool_()),
        ("flag_off_date", pa.bool_()), ("flag_invalid_position", pa.bool_()),
        ("flag_invalid_sog", pa.bool_()), ("flag_invalid_cog", pa.bool_()),
        ("flag_core_valid", pa.bool_()), ("source_file", pa.string()), ("source_row", pa.int64()),
    ])
    rows = [{
        "mmsi": "123456789", "timestamp_utc": datetime(2024, 11, 1, 0, 0, 1, tzinfo=UTC),
        "latitude": 10.0, "longitude": 20.0, "sog": 10.0, "cog": 180.0,
        "flag_invalid_mmsi": False, "flag_invalid_timestamp": False, "flag_off_date": False,
        "flag_invalid_position": False, "flag_invalid_sog": False, "flag_invalid_cog": False,
        "flag_core_valid": True, "source_file": "ais-day.csv", "source_row": 1,
    }]
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
    return path


def test_cli_smoke_jsonl_qc_and_source_read_only(tmp_path):
    source_root = tmp_path / "source"
    source = _write_partition(source_root)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([
        sys.executable, "-m", "src.data.replay_cli",
        "--source-root", str(source_root),
        "--start", "2024-11-01T00:00:00Z", "--end", "2024-11-01T00:00:10Z",
        "--mmsi", "123456789", "--max-events", "5", "--batch-size", "1",
    ], cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    events = [json.loads(line) for line in proc.stdout.splitlines()]
    summary = json.loads(proc.stderr)
    assert len(events) == 1
    assert events[0]["vessel_id"] == "physical_mmsi:123456789"
    assert events[0]["sog_kn"] == 10.0 and events[0]["cog_deg"] == 180.0
    assert events[0]["provenance"] == {"source_file": "ais-day.csv", "source_row": 1}
    assert summary["accepted_events"] == 1
    assert summary["complete_window"] is True
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_cli_refuses_output_inside_source_tree(tmp_path):
    source_root = tmp_path / "source"
    _write_partition(source_root)
    target = source_root / "output.jsonl"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([
        sys.executable, "-m", "src.data.replay_cli",
        "--source-root", str(source_root),
        "--start", "2024-11-01T00:00:00Z", "--end", "2024-11-01T00:00:10Z",
        "--output", str(target),
    ], cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    assert proc.returncode == 2
    assert "must not be inside protected" in proc.stderr
    assert not target.exists()
