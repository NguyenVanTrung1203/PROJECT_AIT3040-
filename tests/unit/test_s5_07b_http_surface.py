from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.app.replay_api import ControlRequest, CreateSessionRequest
from backend.app.runtime_http import EvaluationRequest, RuntimeState, candidates, evaluate, runtime_status, scheduler_status
from src.runtime.trusted_fixture import SOURCE


def _request(runtime):
    app = SimpleNamespace(state=SimpleNamespace(s5_runtime=runtime))
    return Request({'type': 'http', 'app': app, 'method': 'GET', 'path': '/api/v1/runtime/scheduler',
        'headers': [], 'query_string': b'', 'server': ('test', 80), 'client': ('test', 1),
        'scheme': 'http', 'http_version': '1.1', 'root_path': ''})


def test_scheduler_read_surface_and_manual_evaluation_pause_gate():
    runtime = RuntimeState()
    request = _request(runtime)
    try:
        ready = runtime.provider.create('2024-11-01T00:09:00Z')
        scheduler = scheduler_status(request, session_id=ready.session_id)
        assert scheduler['monitoring_status'] == 'DISABLED'
        assert scheduler['latest_batch'] is None
        assert runtime_status(request)['model_load_count'] == 0

        playing = runtime.provider.control('PLAY')
        request_body = EvaluationRequest(snapshot_id='unconsulted', pair_id='unconsulted', request_id='manual-live')
        with pytest.raises(HTTPException) as captured:
            evaluate(playing.session_id, request_body, request)
        assert captured.value.status_code == 409
        assert captured.value.detail['error_code'] == 'MANUAL_EVALUATION_REQUIRES_PAUSED'
        assert runtime._model is None

        runtime.provider.control('PAUSE')
        assert runtime_status(request)['model_load_count'] == 0
    finally:
        runtime.close()


def test_manual_mode_never_starts_scheduler_and_requires_pause_for_candidates():
    runtime = RuntimeState()
    request = _request(runtime)
    try:
        ready = runtime.provider.create('2024-11-01T00:09:00Z')
        runtime.start()
        runtime.provider.control('PLAY')
        assert runtime.scheduler._thread is None
        with pytest.raises(HTTPException) as exc:
            candidates(ready.session_id, request)
        assert exc.value.status_code == 409
        runtime.provider.control('PAUSE')
        assert candidates(ready.session_id, request)['expected'] == 10
        assert scheduler_status(request, ready.session_id)['monitoring_status'] == 'DISABLED'
    finally:
        runtime.close()


def test_shared_authority_keeps_s4_replay_controls_compatible():
    runtime = RuntimeState()
    try:
        created = runtime.replay.create_session(CreateSessionRequest(source_id='fixture-denmark-10m-v1'))
        assert created.source_id == 'fixture-denmark-10m-v1'
        assert runtime.provider._session is None
        playing = runtime.replay.control(created.session_id,
            ControlRequest(action='PLAY', expected_version=created.version), None)
        assert playing.status == 'PLAYING'
        paused = runtime.replay.control(playing.session_id,
            ControlRequest(action='PAUSE', expected_version=playing.version), None)
        assert paused.status == 'PAUSED'
        tracks = runtime.replay.list_tracks(paused.session_id, limit=20, offset=0, snapshot_id=None)
        assert tracks['items'] and tracks['total'] >= 1
        assert runtime.provider._session is None
    finally:
        runtime.close()
