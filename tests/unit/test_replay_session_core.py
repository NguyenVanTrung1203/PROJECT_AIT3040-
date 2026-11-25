from __future__ import annotations

import pytest

from src.data.replay_session_core import ReplaySessionCore, SessionCoreError


START = "2024-11-01T00:00:00Z"
END = "2024-11-01T00:10:00Z"
TARGET = "2024-11-01T00:05:00Z"


def make_core(**kwargs):
    return ReplaySessionCore(**kwargs)


def enter_state(core, state):
    session = core.create("fixture-source", START, END)
    if state in ("PLAYING", "PAUSED"):
        session = core.control(session.session_id, "PLAY", expected_version=0)
    if state == "PAUSED":
        session = core.control(session.session_id, "PAUSE", expected_version=1)
    if state == "ENDED":
        session = core.control(session.session_id, "PLAY", expected_version=0)
        session = core.advance_clock(session.session_id, END)
    if state == "EXPIRED":
        session = core.expire(session.session_id)
    return session


def test_canonical_session_uuid_initial_version_and_simulation_clock():
    core = make_core()
    ready = core.create("fixture-source", START, END)
    assert ready.status == "READY" and ready.version == 0
    assert len(ready.session_id) == 36 and ready.session_id == ready.session_id.lower()
    assert core.control(ready.session_id, "PLAY", expected_version=0).version == 1
    with_error = core.get(ready.session_id)
    assert with_error.status == "PLAYING"
    with pytest.raises(SessionCoreError) as err:
        core.advance_clock(ready.session_id, "2024-11-01T00:11:00Z")
    assert err.value.status_code == 422
    assert core.advance_clock(ready.session_id, "2024-11-01T00:00:01Z").simulation_time == "2024-11-01T00:00:01Z"


def test_all_25_state_action_matrix_cases():
    expected = {
        "READY": {"PLAY": 200, "PAUSE": 409, "RESUME": 409, "RESET": 200, "SEEK": 200},
        "PLAYING": {"PLAY": 409, "PAUSE": 200, "RESUME": 409, "RESET": 200, "SEEK": 200},
        "PAUSED": {"PLAY": 200, "PAUSE": 409, "RESUME": 200, "RESET": 200, "SEEK": 200},
        "ENDED": {"PLAY": 409, "PAUSE": 409, "RESUME": 409, "RESET": 409, "SEEK": 409},
        "EXPIRED": {"PLAY": 410, "PAUSE": 410, "RESUME": 410, "RESET": 410, "SEEK": 410},
    }
    checked = 0
    for state, actions in expected.items():
        for action, expected_code in actions.items():
            core = make_core()
            source = enter_state(core, state)
            key = f"key-{state}-{action}" if action in ("RESET", "SEEK") else None
            kwargs = {"expected_version": source.version}
            if key:
                kwargs["idempotency_key"] = key
            if action == "SEEK":
                kwargs["target_time"] = TARGET
            if expected_code == 200:
                result = core.control(source.session_id, action, **kwargs)
                if action in ("RESET", "SEEK"):
                    assert result.session_id != source.session_id and result.version == 0
                    assert result.status == ("READY" if action == "RESET" else "PAUSED")
                    old = core.get(source.session_id)
                    assert old.status == "ENDED" and old.version == source.version + 1
                else:
                    assert result.session_id == source.session_id and result.version == source.version + 1
            else:
                with pytest.raises(SessionCoreError) as err:
                    core.control(source.session_id, action, **kwargs)
                assert err.value.status_code == expected_code
            checked += 1
    assert checked == 25


def test_reset_is_idempotent_version_checked_and_buffer_isolated():
    def verified(event):
        return event.get("provenance", {}).get("source_file") == "fixture.csv"

    core = make_core(identity_verifier=verified)
    source = core.create("fixture-source", START, END)
    source_buffered = {
        "timestamp_utc": START, "vessel_id": "physical_mmsi:338443451", "mmsi": "338443451",
        "source_type": "REAL_AIS", "is_simulated": False,
        "latitude": 41.7, "longitude": -71.4, "sog_kn": 0.0, "cog_deg": 10.0,
        "provenance": {"source_file": "fixture.csv", "source_row": 1},
    }
    core.ingest(source.session_id, source_buffered)
    new = core.control(source.session_id, "RESET", expected_version=0, idempotency_key="reset-1")
    session_count = len(core.session_ids)
    retry = core.control(source.session_id, "RESET", expected_version=0, idempotency_key="reset-1")
    assert retry == new and len(core.session_ids) == session_count
    assert core.get(source.session_id).status == "ENDED"
    assert core.snapshot(source.session_id, "physical_mmsi:338443451") is not None
    assert core.snapshot(new.session_id, "physical_mmsi:338443451") is None
    with pytest.raises(SessionCoreError) as err:
        core.control(source.session_id, "RESET", expected_version=1, idempotency_key="reset-1")
    assert err.value.status_code == 409 and err.value.code == "IDEMPOTENCY_CONFLICT"


def test_seek_range_retry_and_version_conflicts():
    core = make_core()
    session = core.create("fixture-source", START, END)
    paused = core.control(session.session_id, "SEEK", target_time=TARGET,
                          expected_version=0, idempotency_key="seek-1")
    assert paused.status == "PAUSED" and paused.simulation_time == TARGET and paused.version == 0
    assert core.control(session.session_id, "SEEK", target_time=TARGET,
                        expected_version=0, idempotency_key="seek-1") == paused
    with pytest.raises(SessionCoreError) as err:
        core.control(paused.session_id, "PLAY", expected_version=4)
    assert err.value.status_code == 409 and err.value.code == "VERSION_CONFLICT"
    with pytest.raises(SessionCoreError) as err:
        core.control(paused.session_id, "SEEK", target_time=END,
                     expected_version=0, idempotency_key="seek-out")
    assert err.value.status_code == 422


def test_expired_key_retention_and_noncanonical_uuid():
    now = [100.0]
    core = make_core(wall_clock=lambda: now[0])
    source = core.create("fixture-source", START, END)
    result = core.control(source.session_id, "RESET", expected_version=0, idempotency_key="r")
    now[0] += 24 * 60 * 60 + 1
    with pytest.raises(SessionCoreError) as err:
        core.control(source.session_id, "RESET", expected_version=0, idempotency_key="r")
    assert err.value.status_code == 409
    with pytest.raises(SessionCoreError) as err:
        core.get(source.session_id.upper())
    assert err.value.status_code == 404
    assert core.durable is False and result.version == 0


def test_control_request_shape_and_expiry_status_codes():
    core = make_core()
    session = core.create("fixture-source", START, END)
    with pytest.raises(SessionCoreError) as err:
        core.control(session.session_id, "RESET", expected_version=0)
    assert err.value.status_code == 422
    with pytest.raises(SessionCoreError) as err:
        core.control(session.session_id, "play", expected_version=0)
    assert err.value.status_code == 422
    expired = core.expire(session.session_id)
    assert expired.version == 1 and expired.status == "EXPIRED"
    with pytest.raises(SessionCoreError) as err:
        core.control(session.session_id, "PLAY", expected_version=1)
    assert err.value.status_code == 410
