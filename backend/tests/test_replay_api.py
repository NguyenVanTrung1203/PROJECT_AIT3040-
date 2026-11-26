from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.replay_api import DEMO_SOURCE_ID, ReplayAPI, ReplaySource, demo_source


START = "2024-11-01T00:00:00Z"
ANCHOR = "2024-11-01T00:09:00Z"
END = "2024-11-01T00:10:00Z"


@pytest.fixture
def api_runtime(monkeypatch):
    ticks = [0.0]
    runtime = ReplayAPI([demo_source()], monotonic=lambda: ticks[0])
    monkeypatch.setattr(app.state, "replay_api", runtime, raising=False)
    return runtime, ticks, TestClient(app)


def create(client, start_time=ANCHOR):
    response = client.post("/api/v1/replay/sessions", json={
        "source_id": DEMO_SOURCE_ID, "start_time": start_time,
    })
    assert response.status_code == 201
    return response.json()


def long_replay_source():
    template = demo_source().event_loader()[0]
    events = []
    for minute in range(30):
        event = dict(template)
        event["timestamp_utc"] = f"2024-11-01T00:{minute:02d}:00Z"
        event.pop("original_source_timestamp", None)
        event["vessel_id"] = "simulated:long-replay:ship-001"
        event["latitude"] = template["latitude"] + minute * 0.001
        event["longitude"] = template["longitude"] + minute * 0.001
        event["provenance"] = {"source_file": "long-replay-fixture", "source_row": minute + 1}
        events.append(event)
    return ReplaySource(
        "fixture-long-30m-v1",
        "2024-11-01T00:00:00Z",
        "2024-11-01T00:30:00Z",
        lambda: events,
    )


def test_create_without_optional_start_time_uses_fixture_source_start(api_runtime):
    _runtime, _ticks, client = api_runtime
    response = client.post("/api/v1/replay/sessions", json={"source_id": DEMO_SOURCE_ID})
    assert response.status_code == 201
    session = response.json()
    assert session["source_id"] == DEMO_SOURCE_ID
    assert session["simulation_time"] == START
    assert session["status"] == "READY" and session["version"] == 0

    page_response = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks")
    assert page_response.status_code == 200
    track = page_response.json()["items"][0]
    assert track["anchor_timestamp"] == START
    assert len(track["history"]) == 1
    assert track["data_status"] == "INSUFFICIENT_DATA"
    assert track["current_state"] is None
    assert track["history"][0]["source_timestamp"] == START


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


def test_backend_playback_clock_advances_from_monotonic_time_and_pauses(api_runtime):
    _runtime, ticks, client = api_runtime
    session = create(client)
    session_id = session["session_id"]

    playing = client.post(f"/api/v1/replay/sessions/{session_id}/control",
                          json={"action": "PLAY", "expected_version": 0})
    assert playing.status_code == 200
    assert playing.json()["status"] == "PLAYING" and playing.json()["version"] == 1

    ticks[0] += 2.4
    advanced = client.get(f"/api/v1/replay/sessions/{session_id}").json()
    assert advanced["simulation_time"] == "2024-11-01T00:09:02Z"
    assert advanced["version"] == 1
    assert client.get(f"/api/v1/replay/sessions/{session_id}").json()["version"] == 1

    page_response = client.get(f"/api/v1/replay/sessions/{session_id}/tracks")
    assert page_response.status_code == 200
    page = page_response.json()
    assert page["simulation_time"] == advanced["simulation_time"]
    for track in page["items"]:
        assert all(point["source_timestamp"] <= point["nominal_timestamp"] <= page["simulation_time"]
                   for point in track["history"])

    paused = client.post(f"/api/v1/replay/sessions/{session_id}/control",
                         json={"action": "PAUSE", "expected_version": 1})
    assert paused.status_code == 200
    assert paused.json()["status"] == "PAUSED" and paused.json()["version"] == 2
    ticks[0] += 8
    frozen = client.get(f"/api/v1/replay/sessions/{session_id}").json()
    assert frozen["simulation_time"] == advanced["simulation_time"]
    assert frozen["version"] == 2

    resumed = client.post(f"/api/v1/replay/sessions/{session_id}/control",
                          json={"action": "RESUME", "expected_version": 2})
    assert resumed.status_code == 200
    ticks[0] += 1
    next_clock = client.get(f"/api/v1/replay/sessions/{session_id}").json()
    assert next_clock["simulation_time"] == "2024-11-01T00:09:03Z"
    assert next_clock["version"] == 3

    ticks[0] += 60
    ended = client.get(f"/api/v1/replay/sessions/{session_id}").json()
    assert ended["simulation_time"] == END
    assert ended["status"] == "ENDED"
    assert ended["version"] == 4
    assert client.post(f"/api/v1/replay/sessions/{session_id}/control",
                       json={"action": "PLAY", "expected_version": 4}).status_code == 409


def test_seek_creates_a_paused_session_at_target_with_session_isolation(api_runtime):
    runtime, _ticks, client = api_runtime
    original = create(client)
    original_id = original["session_id"]
    seek = client.post(
        f"/api/v1/replay/sessions/{original_id}/control",
        headers={"Idempotency-Key": "seek-api-1"},
        json={"action": "SEEK", "expected_version": 0, "target_time": "2024-11-01T00:04:00Z"},
    )
    assert seek.status_code == 200
    target = seek.json()
    assert target["session_id"] != original_id
    assert target["status"] == "PAUSED" and target["version"] == 0
    assert target["simulation_time"] == "2024-11-01T00:04:00Z"
    assert runtime.get_session(original_id).status == "ENDED"
    page = client.get(f"/api/v1/replay/sessions/{target['session_id']}/tracks").json()
    assert page["simulation_time"] == target["simulation_time"]
    assert all(point["source_timestamp"] <= point["nominal_timestamp"] <= target["simulation_time"]
               for track in page["items"] for point in track["history"])
    retry = client.post(
        f"/api/v1/replay/sessions/{original_id}/control",
        headers={"Idempotency-Key": "seek-api-1"},
        json={"action": "SEEK", "expected_version": 0, "target_time": "2024-11-01T00:04:00Z"},
    )
    assert retry.status_code == 200 and retry.json() == target


@pytest.mark.parametrize(
    ("minute", "expected_points", "expected_status"),
    [(0, 1, "INSUFFICIENT_DATA"), (1, 2, "INSUFFICIENT_DATA"),
     (5, 6, "INSUFFICIENT_DATA"), (8, 9, "INSUFFICIENT_DATA"),
     (9, 10, "VALID"), (10, 10, "VALID")],
)
def test_replay_fixture_partial_history_at_requested_anchors(api_runtime, minute, expected_points, expected_status):
    _runtime, ticks, client = api_runtime
    target_time = f"2024-11-01T00:{minute:02d}:00Z"
    session = create(client, START)
    if minute > 0:
        started = client.post(f"/api/v1/replay/sessions/{session['session_id']}/control",
                              json={"action": "PLAY", "expected_version": 0})
        assert started.status_code == 200
        ticks[0] += minute * 60
        advanced = client.get(f"/api/v1/replay/sessions/{session['session_id']}").json()
        assert advanced["simulation_time"] == target_time
        assert advanced["status"] == ("ENDED" if minute == 10 else "PLAYING")

    response = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks")
    assert response.status_code == 200
    payload = response.json()
    assert payload["simulation_time"] == target_time
    track = payload["items"][0]
    assert track["anchor_timestamp"] == target_time
    assert len(track["history"]) == expected_points
    assert track["data_status"] == expected_status
    assert (track["current_state"] is None) is (expected_status != "VALID")
    if expected_status == "VALID":
        assert track["current_state"] == track["history"][-1]
    assert track["history"][-1]["nominal_timestamp"] == target_time
    assert all(point["source_timestamp"] <= point["nominal_timestamp"] <= target_time
               and 0 <= point["source_age_seconds"] <= 60 for point in track["history"])


def test_long_replay_keeps_clock_window_and_seek_reset_history_asof(monkeypatch):
    ticks = [0.0]
    runtime = ReplayAPI([long_replay_source()], monotonic=lambda: ticks[0])
    monkeypatch.setattr(app.state, "replay_api", runtime, raising=False)
    client = TestClient(app)

    created = client.post("/api/v1/replay/sessions", json={"source_id": "fixture-long-30m-v1"})
    assert created.status_code == 201
    session = created.json()
    start_page = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks").json()
    start_track = start_page["items"][0]
    assert len(start_track["history"]) == 1
    assert start_track["history"][0]["source_timestamp"] == "2024-11-01T00:00:00Z"
    assert start_track["history"][0]["original_source_timestamp"] is None
    assert start_track["data_status"] == "INSUFFICIENT_DATA" and start_track["current_state"] is None

    started = client.post(
        f"/api/v1/replay/sessions/{session['session_id']}/control",
        json={"action": "PLAY", "expected_version": 0},
    )
    assert started.status_code == 200
    ticks[0] += 15 * 60
    middle = client.get(f"/api/v1/replay/sessions/{session['session_id']}").json()
    assert middle["simulation_time"] == "2024-11-01T00:15:00Z"
    middle_page = client.get(f"/api/v1/replay/sessions/{session['session_id']}/tracks").json()
    middle_track = middle_page["items"][0]
    assert len(middle_track["history"]) == 10 and middle_track["data_status"] == "VALID"

    forward = client.post(
        f"/api/v1/replay/sessions/{session['session_id']}/control",
        headers={"Idempotency-Key": "long-replay-seek-forward"},
        json={"action": "SEEK", "expected_version": 1, "target_time": "2024-11-01T00:25:00Z"},
    ).json()
    forward_page = client.get(f"/api/v1/replay/sessions/{forward['session_id']}/tracks").json()
    forward_track = forward_page["items"][0]
    assert forward["simulation_time"] == "2024-11-01T00:25:00Z"
    assert len(forward_track["history"]) == 10 and forward_track["data_status"] == "VALID"

    backward = client.post(
        f"/api/v1/replay/sessions/{forward['session_id']}/control",
        headers={"Idempotency-Key": "long-replay-seek-backward"},
        json={"action": "SEEK", "expected_version": 0, "target_time": "2024-11-01T00:03:00Z"},
    ).json()
    backward_page = client.get(f"/api/v1/replay/sessions/{backward['session_id']}/tracks").json()
    backward_track = backward_page["items"][0]
    assert len(backward_track["history"]) == 4
    assert backward_track["data_status"] == "INSUFFICIENT_DATA"
    assert backward_track["current_state"] is None

    reset = client.post(
        f"/api/v1/replay/sessions/{backward['session_id']}/control",
        headers={"Idempotency-Key": "long-replay-reset"},
        json={"action": "RESET", "expected_version": 0},
    ).json()
    reset_page = client.get(f"/api/v1/replay/sessions/{reset['session_id']}/tracks").json()
    reset_track = reset_page["items"][0]
    assert reset["simulation_time"] == "2024-11-01T00:00:00Z"
    assert len(reset_track["history"]) == 1
    assert reset_track["history"][0]["source_timestamp"] == "2024-11-01T00:00:00Z"

    for page in (start_page, middle_page, forward_page, backward_page, reset_page):
        for track in page["items"]:
            assert all(point["source_timestamp"] <= point["nominal_timestamp"] <= page["simulation_time"]
                       for point in track["history"])
