from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError
from referencing import Registry, Resource
import pytest

from backend.app.main import app
from backend.app.mock_tracks import MOCK_TRACKS, TrackSnapshot


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
BASE = "https://schemas.ait3040.invalid/contracts/"
client = TestClient(app)


def track_validator() -> Draft202012Validator:
    common = json.loads((CONTRACTS / "common.schema.json").read_text(encoding="utf-8"))
    track = json.loads((CONTRACTS / "track_snapshot.schema.json").read_text(encoding="utf-8"))
    common["$id"] = BASE + "common.schema.json"
    track["$id"] = BASE + "track_snapshot.schema.json"
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    return Draft202012Validator(track, registry=registry, format_checker=FormatChecker())


def test_list_tracks_matches_snapshot_schema_and_has_valid_positions():
    response = client.get("/api/v1/mock/tracks")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == len(body["items"]) == 4
    validator = track_validator()
    for track in body["items"]:
        validator.validate(track)
        assert track["is_simulated"] is True
        assert track["source_type"] == "SYNTHETIC_AIS"
        assert track["mmsi"] is None
        assert len(track["history"]) == 10
        times = [datetime.fromisoformat(p["nominal_timestamp"].replace("Z", "+00:00")) for p in track["history"]]
        assert times == sorted(times)
        assert all(t.tzinfo is not None and t.utcoffset().total_seconds() == 0 for t in times)
        assert all(-90 <= p["latitude"] <= 90 and -180 <= p["longitude"] <= 180 for p in track["history"])
        assert track["current_state"] == track["history"][-1]
        for point in track["history"]:
            nominal = datetime.fromisoformat(point["nominal_timestamp"].replace("Z", "+00:00"))
            assert nominal <= datetime.fromisoformat(track["anchor_timestamp"].replace("Z", "+00:00"))
            if point["source_timestamp"] is not None:
                source = datetime.fromisoformat(point["source_timestamp"].replace("Z", "+00:00"))
                assert source <= nominal


def test_saved_track_example_matches_shared_snapshot_schema():
    example = json.loads((ROOT / "evaluation/s1_t04/mock_track_snapshot.json").read_text(encoding="utf-8"))
    track_validator().validate(example)


def test_detail_returns_track_history():
    response = client.get("/api/v1/mock/tracks/mock-vessel-001")
    assert response.status_code == 200
    assert response.json()["vessel_id"] == "mock-vessel-001"
    assert len(response.json()["history"]) == 10


def test_unknown_vessel_returns_contract_error():
    response = client.get("/api/v1/mock/tracks/absent-vessel")
    assert response.status_code == 404
    assert response.json()["error_code"] == "VESSEL_NOT_FOUND"
    assert response.json()["schema_version"] == "1.0.0"
    assert response.json()["details"]["path"].endswith("/absent-vessel")


def test_source_filter_can_return_empty_collection():
    response = client.get("/api/v1/mock/tracks", params={"source_type": "REAL_AIS"})
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_invalid_filter_uses_error_contract():
    response = client.get("/api/v1/mock/tracks", params={"data_status": "UNKNOWN"})
    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_REQUEST"
    assert response.json()["schema_version"] == "1.0.0"


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_snapshot_rejects_source_message_after_nominal_history_time():
    payload = MOCK_TRACKS[0].model_dump(mode="python")
    payload["history"][0]["source_timestamp"] = payload["anchor_timestamp"].replace(minute=payload["anchor_timestamp"].minute + 1)
    with pytest.raises(ValidationError, match="source timestamp cannot be later"):
        TrackSnapshot.model_validate(payload)
