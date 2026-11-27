import asyncio
import time
import threading

import httpx
import pytest
import torch

from backend.app.main import app
from backend.app.runtime_http import RuntimeState
from src.runtime.trusted_fixture import SOURCE
from tests.unit.test_s5_03_runtime_risk import validator


@pytest.fixture
def state(monkeypatch):
    torch.set_num_threads(1)
    runtime = RuntimeState()
    monkeypatch.setattr(app.state, 's5_runtime', runtime, raising=False)
    monkeypatch.setattr(app.state, 'replay_api', runtime.replay, raising=False)
    yield runtime
    runtime.close()


async def client_call(work):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        return await work(client)


async def create(client, anchor='2024-11-01T00:09:00Z'):
    r = await client.post('/api/v1/replay/sessions', json={'source_id': SOURCE, 'start_time': anchor})
    assert r.status_code == 201, r.text
    return r.json()


async def coverage(client, session):
    r = await client.get(f"/api/v1/runtime/sessions/{session['session_id']}/candidates")
    assert r.status_code == 200, r.text
    return r.json()


async def evaluate(client, session, cov, pair, request_id):
    return await client.post(f"/api/v1/runtime/sessions/{session['session_id']}/evaluate", json={
        'snapshot_id': cov['snapshot_id'], 'pair_id': pair['pair_id'], 'request_id': request_id})


def test_health_mock_replay_and_missing_runtime(state, monkeypatch):
    monkeypatch.delenv('AIT3040_MODEL_PACKAGE', raising=False)
    async def work(client):
        assert (await client.get('/health')).status_code == 200
        assert (await client.get('/api/v1/mock/tracks')).json()['total'] == 4
        s4 = await client.post('/api/v1/replay/sessions', json={'source_id': 'fixture-denmark-10m-v1'})
        assert s4.status_code == 201
        assert (await client.get('/api/v1/replay/sessions/' + s4.json()['session_id'] + '/tracks')).status_code == 200
        session = await create(client)
        cov = await coverage(client, session)
        out = await evaluate(client, session, cov, cov['pairs'][0], 'missing')
        assert out.status_code == 503 and out.json()['error_code'] == 'RUNTIME_CONFIGURATION_OR_ARTIFACT_UNAVAILABLE'
        assert (await client.get('/health')).status_code == 200
    asyncio.run(client_call(work))


def test_actual_model_http_all_pairs(state):
    async def work(client):
        session = await create(client)
        response = await client.post(f"/api/v1/replay/sessions/{session['session_id']}/control", headers={'Idempotency-Key': 'seek-09'}, json={
            'action': 'SEEK', 'expected_version': session['version'], 'target_time': '2024-11-01T00:09:00Z'})
        assert response.status_code == 200 and response.json()['status'] == 'PAUSED'
        current = response.json()
        results = []
        schema = validator('risk_response_v1.schema.json')
        for anchor in ('0009', '0015'):
            if anchor == '0015':
                control = await client.post(f"/api/v1/replay/sessions/{current['session_id']}/control", headers={'Idempotency-Key': 'seek-15'}, json={
                    'action': 'SEEK', 'expected_version': current['version'], 'target_time': '2024-11-01T00:15:00Z'})
                assert control.status_code == 200, control.text
                old = current
                current = control.json()
                assert current['session_id'] != old['session_id']
                assert (await client.get(f"/api/v1/runtime/sessions/{old['session_id']}/candidates")).status_code == 409
            cov = await coverage(client, current)
            assert (cov['expected'], cov['eligible'], cov['unavailable']) == ((10, 6, 4) if anchor == '0009' else (10, 10, 0))
            start = time.perf_counter()
            decisions = []
            for i, pair in enumerate(cov['pairs']):
                response = await evaluate(client, current, cov, pair, f'{anchor}-{i}')
                assert response.status_code == 200, response.text
                envelope = response.json()
                assert envelope['snapshot_id'] == cov['snapshot_id'] and envelope['anchor_utc'] == cov['anchor_utc']
                risk = envelope['risk']
                schema.validate(risk)
                decisions.append(risk['alert_triggered'])
                if i == 0:
                    expected = 0.8832455465682472 if anchor == '0009' else 0.9638132257055823
                    assert risk['risk_score'] == pytest.approx(expected, abs=1e-6)
                if risk['forecast']:
                    assert risk['forecast']['forecast_timestamps'][0] > risk['anchor_timestamp']
                    assert risk['model_status']['active_model'] == 'M5A'
            elapsed = time.perf_counter() - start
            assert (decisions.count(True), decisions.count(False), decisions.count(None)) == ((1, 5, 4) if anchor == '0009' else (1, 9, 0))
            print('HTTP_FIXTURE', anchor, 'seconds', elapsed, 'counts', (decisions.count(True), decisions.count(False), decisions.count(None)))
            alerts = await client.get(f"/api/v1/runtime/sessions/{current['session_id']}/alerts", params={'snapshot_id': cov['snapshot_id']})
            assert alerts.status_code == 200 and alerts.json()['total'] == 1
            validator('alert_v1.schema.json').validate(alerts.json()['items'][0])
            repeated = await evaluate(client, current, cov, cov['pairs'][0], f'{anchor}-0')
            assert repeated.status_code == 200 and repeated.json()['risk']['alert_triggered'] is True
            assert (await client.get(f"/api/v1/runtime/sessions/{current['session_id']}/alerts", params={'snapshot_id': cov['snapshot_id']})).json()['total'] == 1
            results.append((current, cov))
        status = (await client.get('/api/v1/runtime/status')).json()
        assert status['runtime_status'] == 'READY' and status['model_load_count'] == 1
        retries = await asyncio.gather(evaluate(client, current, cov, cov['pairs'][0], 'parallel'),
                                       evaluate(client, current, cov, cov['pairs'][0], 'parallel'))
        assert all(r.status_code == 200 for r in retries)
        assert retries[0].json() == retries[1].json()
        alerts = await client.get(f"/api/v1/runtime/sessions/{current['session_id']}/alerts", params={'snapshot_id': cov['snapshot_id']})
        assert alerts.json()['total'] == 1
        assert (await evaluate(client, current, cov, {'pair_id': 'bad'}, 'bad')).status_code == 404
        assert (await evaluate(client, current, results[0][1], cov['pairs'][0], 'old')).status_code == 409
    asyncio.run(client_call(work))


def test_controls_snapshot_invalidation_and_session_isolation(state):
    async def work(client):
        session = await create(client)
        old = await coverage(client, session)
        response = await client.post(f"/api/v1/replay/sessions/{session['session_id']}/control", json={'action':'PLAY','expected_version':0})
        assert response.status_code == 200
        playing = response.json()
        response = await client.post(f"/api/v1/replay/sessions/{playing['session_id']}/control", json={'action':'PAUSE','expected_version':playing['version']})
        assert response.status_code == 200
        paused = response.json()
        assert (await evaluate(client, paused, old, old['pairs'][0], 'stale')).status_code == 409
        response = await client.post(f"/api/v1/replay/sessions/{paused['session_id']}/control", headers={'Idempotency-Key':'reset-key'}, json={'action':'RESET','expected_version':paused['version']})
        assert response.status_code == 200
        new = response.json()
        assert new['session_id'] != paused['session_id']
        assert (await client.get(f"/api/v1/runtime/sessions/{paused['session_id']}/candidates")).status_code == 409
        new_cov = await coverage(client, new)
        assert new_cov['anchor_utc'] == '2024-11-01T00:00:00Z'
        assert (await client.post('/api/v1/replay/sessions', json={'source_id': SOURCE})).status_code == 409
    asyncio.run(client_call(work))


def test_active_s5_session_discovery_and_replacement(state):
    async def work(client):
        empty = await client.get('/api/v1/runtime/active-session')
        assert empty.status_code == 200 and empty.json() == {'session': None}

        s4 = await client.post('/api/v1/replay/sessions', json={'source_id': 'fixture-denmark-10m-v1'})
        assert s4.status_code == 201
        assert (await client.get('/api/v1/runtime/active-session')).json() == {'session': None}
        assert (await client.get(f"/api/v1/replay/sessions/{s4.json()['session_id']}/tracks")).status_code == 200

        current = await create(client)
        found = await client.get('/api/v1/runtime/active-session')
        assert found.status_code == 200
        assert found.json()['session'] == current

        for action, target in (('SEEK', '2024-11-01T00:15:00Z'), ('RESET', None)):
            body = {'action': action, 'expected_version': current['version']}
            if target is not None:
                body['target_time'] = target
            replacement = await client.post(
                f"/api/v1/replay/sessions/{current['session_id']}/control",
                headers={'Idempotency-Key': f'recovery-{action.lower()}'}, json=body)
            assert replacement.status_code == 200, replacement.text
            next_session = replacement.json()
            assert next_session['session_id'] != current['session_id']
            discovered = await client.get('/api/v1/runtime/active-session')
            assert discovered.status_code == 200
            assert discovered.json()['session'] == next_session
            assert (await client.get(
                f"/api/v1/runtime/sessions/{current['session_id']}/candidates")).status_code == 409
            current = next_session

        assert (await client.post('/api/v1/replay/sessions', json={'source_id': SOURCE})).status_code == 409
    asyncio.run(client_call(work))


def test_active_s5_recovery_repins_expired_snapshot(state):
    async def work(client):
        session = await create(client)
        old = await coverage(client, session)

        # Expire only the API's pinned snapshot while the replay session stays
        # active, matching a browser reload after the snapshot retention TTL.
        state.provider._api.snapshot_ttl_seconds = 0
        recovered_response = await client.get(
            f"/api/v1/runtime/sessions/{session['session_id']}/candidates")
        assert recovered_response.status_code == 200, recovered_response.text
        recovered = recovered_response.json()
        state.provider._api.snapshot_ttl_seconds = 60

        assert recovered['session_id'] == session['session_id']
        assert recovered['session_version'] == session['version']
        assert recovered['anchor_utc'] == session['simulation_time']
        assert recovered['snapshot_id'] != old['snapshot_id']
        tracks = await client.get(
            f"/api/v1/replay/sessions/{session['session_id']}/tracks",
            params={'limit': 50, 'offset': 0, 'snapshot_id': recovered['snapshot_id']})
        assert tracks.status_code == 200, tracks.text
        assert tracks.json()['snapshot_id'] == recovered['snapshot_id']
        assert len(tracks.json()['items']) == 5

        stale = await client.post(
            f"/api/v1/runtime/sessions/{session['session_id']}/evaluate",
            json={'snapshot_id': old['snapshot_id'], 'pair_id': old['pairs'][0]['pair_id'],
                  'request_id': 'expired-snapshot'})
        assert stale.status_code == 409, stale.text

    asyncio.run(client_call(work))


def test_active_s5_discovery_serializes_concurrent_create_and_recovery(state):
    async def work(client):
        created, observed = await asyncio.gather(
            client.post('/api/v1/replay/sessions', json={'source_id': SOURCE,
                                                         'start_time': '2024-11-01T00:09:00Z'}),
            client.get('/api/v1/runtime/active-session'))
        assert created.status_code == 201, created.text
        assert observed.status_code == 200
        active = await client.get('/api/v1/runtime/active-session')
        assert active.status_code == 200
        assert active.json()['session']['session_id'] == created.json()['session_id']

        duplicate_a, duplicate_b = await asyncio.gather(
            client.post('/api/v1/replay/sessions', json={'source_id': SOURCE}),
            client.post('/api/v1/replay/sessions', json={'source_id': SOURCE}))
        assert [duplicate_a.status_code, duplicate_b.status_code] == [409, 409]
        s5_ids = [sid for sid, source_id in state.replay.api._session_sources.items() if source_id == SOURCE]
        assert s5_ids == [created.json()['session_id']]
    asyncio.run(client_call(work))


def test_s4_controls_through_shared_authority_and_unauthorized(state, monkeypatch):
    monkeypatch.setenv('AIT3040_RUNTIME_AUTHORITY', 'invalid')
    async def work(client):
        start = await client.post('/api/v1/replay/sessions', json={'source_id': 'fixture-denmark-10m-v1'})
        s = start.json()
        for action in ('PLAY', 'PAUSE'):
            response = await client.post(f"/api/v1/replay/sessions/{s['session_id']}/control", json={'action': action, 'expected_version': s['version']})
            assert response.status_code == 200, response.text
            s = response.json()
        response = await client.post(f"/api/v1/replay/sessions/{s['session_id']}/control", headers={'Idempotency-Key':'s4-seek'}, json={'action':'SEEK','expected_version':s['version'],'target_time':'2024-11-01T00:09:00Z'})
        assert response.status_code == 200
        s = response.json()
        response = await client.post(f"/api/v1/replay/sessions/{s['session_id']}/control", headers={'Idempotency-Key':'s4-reset'}, json={'action':'RESET','expected_version':s['version']})
        assert response.status_code == 200
        session = await create(client)
        cov = await coverage(client, session)
        response = await evaluate(client, session, cov, cov['pairs'][0], 'unauthorized')
        assert response.status_code == 503
        state.close()
        status = (await client.get('/api/v1/runtime/status')).json()
        assert status['runtime_status'] == 'UNAVAILABLE' and status['reason'] == 'SERVICE_CLOSED'
    asyncio.run(client_call(work))


def test_continuous_playback_does_not_publish_stale(state):
    async def work(client):
        session = await create(client)
        response = await client.post(f"/api/v1/replay/sessions/{session['session_id']}/control", json={'action':'PLAY', 'expected_version':session['version']})
        assert response.status_code == 200
        playing = response.json()
        state.model()
        cov = await coverage(client, playing)
        start = time.perf_counter()
        result = await evaluate(client, playing, cov, cov['pairs'][0], 'live')
        elapsed = time.perf_counter() - start
        now = await client.get(f"/api/v1/replay/sessions/{playing['session_id']}")
        assert now.status_code == 200
        print('CONTINUOUS_PLAYBACK', 'seconds', elapsed, 'http', result.status_code, 'anchor', cov['anchor_utc'], 'clock', now.json()['simulation_time'])
        if result.status_code == 200:
            assert result.json()['anchor_utc'] == now.json()['simulation_time']
        else:
            assert result.status_code == 409
    asyncio.run(client_call(work))


@pytest.mark.parametrize('action', ['SEEK', 'RESET'])
def test_http_seek_reset_during_inference_discards(state, monkeypatch, action):
    async def work(client):
        session = await create(client)
        cov = await coverage(client, session)
        harness = state.model()
        original = harness._model.predict
        entered, proceed = threading.Event(), threading.Event()
        def delayed(*args):
            result = original(*args)
            entered.set()
            if not proceed.wait(60):
                raise RuntimeError('test timeout')
            return result
        monkeypatch.setattr(harness._model, 'predict', delayed)
        pending = asyncio.create_task(evaluate(client, session, cov, cov['pairs'][0], 'race'))
        assert await asyncio.to_thread(entered.wait, 60)
        body = {'action': action, 'expected_version': session['version']}
        if action == 'SEEK':
            body['target_time'] = '2024-11-01T00:08:00Z'
        transition = await client.post(f"/api/v1/replay/sessions/{session['session_id']}/control", headers={'Idempotency-Key':'race-key'}, json=body)
        assert transition.status_code == 200
        proceed.set()
        response = await asyncio.wait_for(pending, 90)
        assert response.status_code == 409, response.text
        replacement = transition.json()
        new_cov = await coverage(client, replacement)
        alerts = await client.get(f"/api/v1/runtime/sessions/{replacement['session_id']}/alerts", params={'snapshot_id':new_cov['snapshot_id']})
        assert alerts.status_code == 200 and alerts.json()['total'] == 0
    asyncio.run(client_call(work))
