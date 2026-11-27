from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import os
import shutil
import threading
import time

import pytest
import torch

import src.runtime.verified_context as verified_context
from src.runtime.batch_scheduler import AutomaticEvaluationScheduler
from src.runtime.config import load_config
from src.runtime.m5a_service import M5aRuntime, RuntimeUnavailable
from src.runtime.risk_service import FixtureRiskHarness
from src.runtime.trusted_fixture import FixtureProvider, SOURCE


@pytest.fixture(scope='module')
def config():
    torch.set_num_threads(1)
    return load_config(os.environ)


def _run_batch(provider, model, harness, anchor):
    view = provider._api.get_session(provider._session.session_id)
    snapshot, coverage = provider.evaluation_snapshot(view.session_id, anchor, view.version)
    deadline = provider._api.evaluation_deadline(view.session_id, anchor, 1.0)
    cancellation = threading.Event()
    threshold_checks_before = model._context.threshold_semantic_check_count
    total_started = time.perf_counter()
    harness.invalidate_stale_anchor_cache(snapshot)
    started = time.perf_counter()
    token = model.begin_batch(snapshot, coverage.candidates, deadline, cancellation)
    start_boundary_seconds = time.perf_counter() - started
    stage = harness.begin_batch_stage()
    try:
        started = time.perf_counter()
        for candidate in coverage.candidates:
            request_id = f'07b:{anchor}:{candidate.pair_id}'
            stage.evaluate(snapshot, candidate, request_id, token)
        boundary_started = time.perf_counter()
        model.verify_batch_end(token)
        end_boundary_seconds = time.perf_counter() - boundary_started
        results = harness.publish_batch_stage(stage, snapshot, token)
        return snapshot, coverage, results, {'batch_seconds': time.perf_counter() - total_started,
            'start_boundary_seconds': start_boundary_seconds, 'end_boundary_seconds': end_boundary_seconds,
            'threshold_checks': model._context.threshold_semantic_check_count - threshold_checks_before}
    finally:
        if not stage.closed:
            harness.discard_batch_stage(stage)
        model.discard_batch(token)
        provider.release_evaluation_snapshot(snapshot)


def test_generation_lease_survives_clock_progress_and_expires_on_pause():
    clock = [100.0]
    provider = FixtureProvider(5, backend_replay=True)
    provider._api.monotonic = lambda: clock[0]
    ready = provider.create('2024-11-01T00:09:00Z')
    playing = provider.control('PLAY')
    snapshot, coverage = provider.evaluation_snapshot(ready.session_id, '2024-11-01T00:09:00Z', playing.version)
    assert (coverage.expected, coverage.eligible, coverage.unavailable) == (10, 6, 4)
    assert all(track['anchor_timestamp'] == snapshot.anchor_utc for track in snapshot.tracks)
    assert all(point['nominal_timestamp'] <= snapshot.anchor_utc
               for track in snapshot.tracks for point in track['history'])
    clock[0] += 37
    provider._check(snapshot)
    paused = provider.control('PAUSE')
    assert paused.status == 'PAUSED'
    with pytest.raises(ValueError):
        provider._check(snapshot)


def test_deadline_is_measured_from_the_anchor_crossing():
    clock = [100.0]
    provider = FixtureProvider(5, backend_replay=True)
    provider._api.monotonic = lambda: clock[0]
    ready = provider.create('2024-11-01T00:09:00Z')
    playing = provider.control('PLAY')
    clock[0] += 30
    deadline_09 = provider._api.evaluation_deadline(ready.session_id, '2024-11-01T00:09:00Z')
    deadline_10 = provider._api.evaluation_deadline(playing.session_id, '2024-11-01T00:10:00Z')
    assert deadline_09 == pytest.approx(160.0)
    assert deadline_10 == pytest.approx(220.0)


def test_scheduler_keeps_only_one_latest_pending_anchor():
    entered = threading.Event()
    release_first = threading.Event()

    class Provider:
        def __init__(self):
            self.released = []
            self._api = SimpleNamespace(evaluation_deadline=lambda *_args: time.monotonic() + 60)

        def evaluation_snapshot(self, session_id, anchor, generation):
            snapshot = SimpleNamespace(session_id=session_id, session_version=generation,
                snapshot_id=f'snapshot-{anchor}', anchor_utc=anchor)
            return snapshot, SimpleNamespace(candidates=(), expected=0, eligible=0, unavailable=0)

        def release_evaluation_snapshot(self, snapshot):
            self.released.append(snapshot.anchor_utc)

    provider = Provider()

    class State:
        def __init__(self):
            self.provider = provider
            self.calls = 0

        def model(self):
            self.calls += 1
            if self.calls == 1:
                entered.set()
                release_first.wait(3)
            raise RuntimeUnavailable('TEST_WORKER_FAILURE')

    state = State()
    scheduler = AutomaticEvaluationScheduler(state)
    view = SimpleNamespace(session_id='session', version=4, source_id=SOURCE,
                           status='PLAYING', simulation_time='2024-11-01T00:02:00Z')
    scheduler._binding = ('session', 4, SOURCE, 'PLAYING')
    scheduler._create_and_enqueue(view, '2024-11-01T00:00:00Z')
    assert entered.wait(2)
    scheduler._create_and_enqueue(view, '2024-11-01T00:01:00Z')
    scheduler._create_and_enqueue(view, '2024-11-01T00:02:00Z')
    status = scheduler.status()
    assert status['active_anchor'] == '2024-11-01T00:00:00Z'
    assert status['pending_anchor'] == '2024-11-01T00:02:00Z'
    assert len(status['skipped_anchors']) == 1
    assert status['skipped_anchors'][0]['reason'] == 'REPLACED_BY_LATEST_PENDING'
    release_first.set()
    deadline = time.monotonic() + 5
    while scheduler.status()['running'] or scheduler._worker_busy:
        if time.monotonic() >= deadline:
            scheduler.close()
            pytest.fail('scheduler did not drain the bounded queue')
        time.sleep(0.02)
    assert state.calls == 2
    assert set(provider.released) == {'2024-11-01T00:00:00Z', '2024-11-01T00:01:00Z', '2024-11-01T00:02:00Z'}
    scheduler.close()


def test_scheduler_percentiles_use_nearest_rank_for_small_samples():
    scheduler = AutomaticEvaluationScheduler(SimpleNamespace(provider=None))
    try:
        scheduler._latencies = [3.009, 2.361]
        status = scheduler.status()
        assert status['latency_sample_count'] == 2
        assert status['latency_p50_seconds'] == pytest.approx(2.361)
        assert status['latency_p95_seconds'] == pytest.approx(3.009)
    finally:
        scheduler.close()


def test_failed_batch_stage_never_publishes_cache_or_alert_state():
    provider = FixtureProvider(5)
    model = object.__new__(M5aRuntime)
    model._provider = provider
    model._closed = False
    model._active_batch_token = object()
    model._state_lock = threading.RLock()
    harness = FixtureRiskHarness(provider, model)
    harness._cache['before'] = ('identity', {'value': 'existing'})
    harness._requests[('session', 'before')] = ('identity',)
    original_alerts = harness._alerts.clone()
    stage = harness.begin_batch_stage()
    stage.harness._cache['unpublished'] = ('new', {'value': 'staged'})
    stage.harness._requests[('session', 'new')] = ('new',)
    stage.harness._alerts._history.append({'alert_id': 'staged-only'})
    stage.results.append({'risk': {'alert_triggered': True}})
    with pytest.raises(RuntimeUnavailable, match='BATCH_PUBLICATION_INVALID'):
        harness.publish_batch_stage(stage, object(), object())
    assert harness._cache == {'before': ('identity', {'value': 'existing'})}
    assert harness._requests == {('session', 'before'): ('identity',)}
    assert harness._alerts.list('session') == original_alerts.list('session')
    assert stage.closed


def test_model_and_scalers_load_from_verified_bytes_even_if_disk_changes_after_hash(config, tmp_path):
    if os.name == 'nt' and not str(tmp_path).startswith('\\\\?\\'):
        tmp_path = Path('\\\\?\\' + str(tmp_path))
    package_copy = tmp_path / 'package-copy'
    shutil.copytree(config.package_path, package_copy)
    pin_copy = tmp_path / 'pin-copy.json'
    shutil.copyfile(config.pin_path, pin_copy)
    copied_config = replace(config, package_path=package_copy, pin_path=pin_copy)

    metadata, contents, identity, identity_obj = verified_context._load_package(copied_config)
    checkpoint_path = package_copy / metadata['run_dir'] / 'best_model.pt'
    checkpoint_path.write_bytes(b'tampered after verified read')
    backend = verified_context._load_inference(copied_config, metadata, contents)
    expected = torch.load(BytesIO(contents[f"{metadata['run_dir']}/best_model.pt"]),
                          map_location='cpu', weights_only=True)
    for name, value in expected['model_state'].items():
        assert torch.equal(backend.model.state_dict()[name].cpu(), value.cpu())

    context = verified_context.VerifiedRuntimeContext(copied_config, identity, identity_obj, 'test-generation', backend)
    context.bind_verified_manifest(metadata)
    with pytest.raises(verified_context.VerifiedContextError):
        context.verify_boundary()
    assert context.invalidated
    with pytest.raises(verified_context.VerifiedContextError, match='invalidated'):
        context.verify_boundary()


def test_batch_parity_at_minute_09_and_15_with_two_boundaries_each(config, monkeypatch):
    original_load = verified_context._load_package
    package_walks = []
    boundary_times = []

    def counted_load(runtime_config):
        package_walks.append(time.perf_counter())
        return original_load(runtime_config)

    monkeypatch.setattr(verified_context, '_load_package', counted_load)
    original_boundary = verified_context.VerifiedRuntimeContext.verify_boundary

    def timed_boundary(context):
        started = time.perf_counter()
        value = original_boundary(context)
        boundary_times.append(time.perf_counter() - started)
        return value

    monkeypatch.setattr(verified_context.VerifiedRuntimeContext, 'verify_boundary', timed_boundary)
    provider = FixtureProvider(5, backend_replay=True)
    ready = provider.create('2024-11-01T00:09:00Z')
    provider.control('PLAY')
    model = M5aRuntime(config, provider)
    harness = FixtureRiskHarness(provider, model)
    observed = {}
    batch_latencies = {}
    try:
        for anchor in ('2024-11-01T00:09:00Z', '2024-11-01T00:15:00Z'):
            if anchor.endswith('00:15:00Z'):
                provider.control('PAUSE')
                provider.control('SEEK', anchor)
                provider.control('PLAY')
            snapshot, coverage, rows, metrics = _run_batch(provider, model, harness, anchor)
            observed[anchor] = rows
            batch_latencies[anchor] = metrics
            assert coverage.expected == 10 and len(rows) == 10
            assert snapshot.anchor_utc == anchor
        assert package_walks and len(package_walks) == 5  # one load + two full boundaries per batch
        assert model.load_count == 1
        assert model._context.boundary_verification_count == 4
        assert model._context.threshold_semantic_check_count == 26
        assert len(boundary_times) == 4
        for anchor, alert_count, no_alert_count, unavailable_count, expected_score in (
                ('2024-11-01T00:09:00Z', 1, 5, 4, 0.8832455466),
                ('2024-11-01T00:15:00Z', 1, 9, 0, 0.9638132257)):
            by_pair = {row['pair_id']: row for row in observed[anchor]}
            decisions = [row['alert_triggered'] for row in by_pair.values()]
            assert decisions.count(True) == alert_count
            assert decisions.count(False) == no_alert_count
            assert decisions.count(None) == unavailable_count
            ab = next(row for row in by_pair.values() if row['vessel_ids'][0].endswith(':a') and row['vessel_ids'][1].endswith(':b'))
            assert ab['risk_score'] == pytest.approx(expected_score, abs=1e-9)
            assert ab['threshold'] == 0.420 and ab['decision_status'] == 'DECIDED'
            assert ab['forecast_status'] == 'AVAILABLE' and len(ab['forecast']['forecast_timestamps']) == 15
        assert batch_latencies['2024-11-01T00:09:00Z']['batch_seconds'] < 60
        assert batch_latencies['2024-11-01T00:15:00Z']['batch_seconds'] < 60
        print('S5_07B_BATCH_METRICS', {'package_walks': len(package_walks),
              'boundary_seconds': boundary_times, 'batch_metrics': batch_latencies,
              'threshold_semantic_checks': model._context.threshold_semantic_check_count,
              'load_count': model.load_count})
    finally:
        model.close()


def test_warm_single_pair_paused_evaluation_latency(config):
    provider = FixtureProvider(5)
    provider.create('2024-11-01T00:09:00Z')
    snapshot = provider.snapshot()
    coverage = provider.candidates(snapshot)
    cold_started = time.perf_counter()
    model = M5aRuntime(config, provider)
    cold_start_seconds = time.perf_counter() - cold_started
    harness = FixtureRiskHarness(provider, model)
    try:
        started = time.perf_counter()
        risk = harness.evaluate(snapshot, coverage.candidates[0], '07b-warm-paused-single-pair')
        warm_single_pair_seconds = time.perf_counter() - started
        assert risk['decision_status'] == 'DECIDED'
        assert risk['alert_triggered'] is True
        assert model.load_count == 1
        print('S5_07B_SINGLE_PAIR_METRICS', {'cold_start_seconds': cold_start_seconds,
              'warm_single_pair_seconds': warm_single_pair_seconds, 'model_load_count': model.load_count})
    finally:
        model.close()


def test_automatic_batch_recomputes_manual_same_anchor_under_new_generation(config):
    provider = FixtureProvider(5, backend_replay=True)
    ready = provider.create('2024-11-01T00:15:00Z')
    manual_snapshot = provider.snapshot()
    manual_coverage = provider.candidates(manual_snapshot)
    model = M5aRuntime(config, provider)
    harness = FixtureRiskHarness(provider, model)
    try:
        ab = next(candidate for candidate in manual_coverage.candidates
                  if candidate.vessels == ('simulated:s5-01:a', 'simulated:s5-01:b'))
        manual = harness.evaluate(manual_snapshot, ab, '07b-manual-before-play')
        assert manual['alert_triggered'] is True

        playing = provider.control('PLAY')
        snapshot, _coverage, rows, _metrics = _run_batch(
            provider, model, harness, '2024-11-01T00:15:00Z')
        auto_ab = next(row for row in rows
                       if row['vessel_ids'] == ['simulated:s5-01:a', 'simulated:s5-01:b'])
        assert snapshot.session_version == playing.version
        assert auto_ab['alert_triggered'] is True
        assert auto_ab['risk_score'] == pytest.approx(manual['risk_score'], abs=1e-9)
        assert auto_ab['anchor_timestamp'] == manual['anchor_timestamp']
        assert model.load_count == 1
    finally:
        model.close()
