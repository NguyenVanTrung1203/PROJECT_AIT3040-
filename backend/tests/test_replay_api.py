from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.replay_api import DEMO_SOURCE_ID, ReplayAPI, demo_source


START = "2024-11-01T00:00:00Z"
ANCHOR = "2024-11-01T00:09:00Z"
END = "2024-11-01T00:10:00Z"


@pytest.fixture
def api_runtime(monkeypatch):
    ticks = [0.0]
    runtime = ReplayAPI([demo_source()], monotonic=lambda: ticks[0])
    monkeypatch.setattr(app.state, "replay_api", runtime, raising=False)
    return runtime, ticks, TestClient(app)


def create(client):
    response = client.post("/api/v1/replay/sessions", json={
        "source_id": DEMO_SOURCE_ID, "start_time": ANCHOR,
    })
    assert response.status_code == 201
    return response.json()


def test_replay_v1_five_routes_return_contract_data_and_leaflet_coordinates(api_runtime):
    _runtime, _ticks, client = api_runtime
    session = create(client)
    assert client.get(f"/api/v1/replay/sessions/{session['session_id']}").json() == session

    listing = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks",
                         params={"limit": 50, "offset": 0})
    assert listing.status_code == 200
    page = listing.json()
    assert page["total"] == 1 and page["limit"] == 50 and page["offset"] == 0
    assert len(page["snapshot_id"]) == 36 and page["simulation_time"] == ANCHOR
    track = page["items"][0]
    assert track["data_status"] == "VALID" and len(track["history"]) == 10
    assert track["current_state"] == track["history"][-1]
    assert track["source_type"] == "SYNTHETIC_AIS" and track["is_simulated"] is True
    assert all(point["source_timestamp"] <= point["nominal_timestamp"] for point in track["history"])
    detail = client.get(
        f"/api/v1/replay/sessions/{session['session_id']}/tracks/{track['vessel_id']}",
        params={"snapshot_id": page["snapshot_id"]},
    )
    assert detail.status_code == 200 and detail.json() == track
    next_page = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks",
                           params={"limit": 1, "offset": 1, "snapshot_id": page["snapshot_id"]})
    assert next_page.status_code == 200 and next_page.json()["items"] == []


def test_snapshot_pagination_is_pinned_and_requires_id_for_next_page(api_runtime):
    runtime, _ticks, client = api_runtime
    session = create(client)
    first = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks").json()
    missing_pin = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks",
                             params={"offset": 1})
    assert missing_pin.status_code == 422

    # RESET creates a separate session; the pinned page remains attached to the old session.
    response = client.post(f"/api/v1/replay/sessions/{session['session_id']}/control",
                           headers={"Idempotency-Key": "reset-api-1"},
                           json={"action": "RESET", "expected_version": 0})
    assert response.status_code == 200
    reset_session = response.json()
    assert reset_session["session_id"] != session["session_id"]
    assert reset_session["status"] == "READY" and reset_session["version"] == 0
    old_page = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks",
                          params={"snapshot_id": first["snapshot_id"]}).json()
    assert old_page["items"] == first["items"]
    assert runtime.get_session(session["session_id"]).status == "ENDED"

    same_retry = client.post(f"/api/v1/replay/sessions/{session['session_id']}/control",
                             headers={"Idempotency-Key": "reset-api-1"},
                             json={"action": "RESET", "expected_version": 0})
    assert same_retry.json() == reset_session
    reset_tracks = client.get(f"/api/v1/replay/sessions/{reset_session['session_id']}/tracks").json()["items"]
    assert len(reset_tracks) == 1
    assert reset_tracks[0]["data_status"] == "INSUFFICIENT_DATA"
    assert reset_tracks[0]["current_state"] is None


def test_errors_stale_session_and_snapshot_ttl(api_runtime):
    runtime, ticks, client = api_runtime
    unknown_source = client.post("/api/v1/replay/sessions", json={"source_id": "missing"})
    assert unknown_source.status_code == 503
    assert unknown_source.json()["error_code"] == "SOURCE_UNAVAILABLE"
    bad_start = client.post("/api/v1/replay/sessions", json={
        "source_id": DEMO_SOURCE_ID, "start_time": "2024-11-01T07:09:00+07:00",
    })
    assert bad_start.status_code == 422

    session = create(client)
    no_key = client.post(f"/api/v1/replay/sessions/{session['session_id']}/control",
                         json={"action": "RESET", "expected_version": 0})
    assert no_key.status_code == 422
    bad_pagination = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks",
                                params={"limit": 101})
    assert bad_pagination.status_code == 422
    missing_vessel = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks/absent")
    assert missing_vessel.status_code == 404
    unknown_session = client.get("/api/v1/replay/sessions/123e4567-e89b-12d3-a456-426614174099")
    assert unknown_session.status_code == 404

    page = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks").json()
    ticks[0] += 301
    expired = client.get(
        f"/api/v1/replay/sessions/{session['session_id']}/tracks/{page['items'][0]['vessel_id']}",
        params={"snapshot_id": page["snapshot_id"]},
    )
    assert expired.status_code == 410 and expired.json()["error_code"] == "SNAPSHOT_EXPIRED"

    core = runtime._core_for_session(session["session_id"])
    core.expire(session["session_id"])
    assert client.get(f"/api/v1/replay/sessions/{session['session_id']}").status_code == 410


def test_mock_api_remains_separate_from_replay_endpoints(api_runtime):
    _runtime, _ticks, client = api_runtime
    mock = client.get("/api/v1/mock/tracks")
    assert mock.status_code == 200 and mock.json()["total"] == 4
    assert client.get("/api/v1/replay/sessions").status_code == 405
