from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import shutil
import os
import threading
import time

import numpy as np
import pytest
import torch

import src.runtime.m5a_service as module
from src.models.pipeline import forecast
from src.models.kinematics import cv_displacement, project_forecast
from src.runtime.config import load_config
from src.runtime.m5a_service import M5aRuntime, RuntimeUnavailable
from src.runtime.trusted_fixture import FixtureProvider


@pytest.fixture(scope='module')
def config():
    import os
    torch.set_num_threads(1)
    return load_config(os.environ)


@pytest.fixture
def fixture():
    p = FixtureProvider(5)
    p.create('2024-11-01T00:09:00Z')
    s = p.snapshot()
    return p, s, p.candidates(s)


@pytest.fixture
def runtime(config, fixture):
    service = M5aRuntime(config, fixture[0])
    yield service
    service.close()


def test_real_model_lifecycle_and_cpu_reference(config, fixture, runtime):
    p, s, c = fixture
    candidate = c.candidates[0]
    enc, _ = p.encounter(s, candidate)
    features = p.features(s, enc)
    result = runtime.predict(s, candidate, features)
    assert runtime.load_count == 1 and not runtime._backend.model.training
    assert result.status == 'AVAILABLE' and not result.risk_eligible
    assert all(v.active_model == 'M5a' and v.qc_status == 'PASS' for v in result.vessels)
    assert all(v.en.shape == (15, 2) and v.lat_lon.shape == (15, 2) for v in result.vessels)
    assert len(result.timestamps) == 15 and result.timestamps[0] == '2024-11-01T00:10:00Z'
    x = torch.from_numpy(features.history.copy())
    a = torch.from_numpy(features.anchors_en.copy())
    with torch.inference_mode():
        scaled = runtime._backend.x_scaler.transform(x)
        cv = cv_displacement(x[:, -1, 2:].to(a.dtype))
        residual = runtime._backend.residual_scaler.inverse_transform(runtime._backend.model(scaled)).to(a.dtype)
        manual = project_forecast(a[:, None] + cv + residual, a, x[:, -1, 2:].to(a.dtype))
        reference = forecast(runtime._backend.model, runtime._backend.x_scaler, runtime._backend.residual_scaler, x, a)
    np.testing.assert_allclose(manual.numpy(), reference.numpy(), atol=1e-12, rtol=0)
    np.testing.assert_allclose(np.stack([v.en for v in result.vessels]), reference.numpy(), atol=1e-6, rtol=0)
    lat0, lon0 = features.origin_lat_lon
    en = np.stack([v.en for v in result.vessels])
    geo = np.stack([v.lat_lon for v in result.vessels])
    np.testing.assert_allclose((geo[..., 1] - lon0) * 60 * np.cos(np.deg2rad(lat0)), en[..., 0], atol=1e-10)
    np.testing.assert_allclose((geo[..., 0] - lat0) * 60, en[..., 1], atol=1e-10)
    assert runtime.predict(s, candidate).status == 'AVAILABLE' and runtime.load_count == 1


def test_full_fixture_coverage(config, fixture, runtime):
    p, s, coverage = fixture
    assert (coverage.eligible, coverage.unavailable) == (6, 4)
    for candidate in coverage.candidates:
        if candidate.unavailable_reason:
            with pytest.raises(RuntimeUnavailable, match='INSUFFICIENT'):
                runtime.predict(s, candidate)
        else:
            assert runtime.predict(s, candidate).status == 'AVAILABLE'
    p.control('SEEK', '2024-11-01T00:15:00Z')
    s = p.snapshot()
    coverage = p.candidates(s)
    assert (coverage.eligible, coverage.unavailable) == (10, 0)
    for candidate in coverage.candidates:
        out = runtime.predict(s, candidate)
        assert out.status == 'AVAILABLE' and tuple(v.vessel_id for v in out.vessels) == candidate.vessels
    p.control('RESET')
    early = p.snapshot()
    assert p.candidates(early).eligible == 0
    with pytest.raises(RuntimeUnavailable):
        runtime.predict(s, candidate)


def test_real_intermediate_parity(fixture, runtime, monkeypatch):
    import src.models.pipeline as pipeline
    p, s, c = fixture
    encounter, _ = p.encounter(s, c.candidates[0])
    f = p.features(s, encounter)
    x = torch.from_numpy(f.history.copy())
    a = torch.from_numpy(f.anchors_en.copy())
    model = runtime._backend.model
    with torch.inference_mode():
        expected_scaled = torch.cat([runtime._backend.x_scaler.transform(x[i:i+1]) for i in range(2)])
        expected_residual = torch.cat([model(expected_scaled[i:i+1]) for i in range(2)])
        expected_cv = torch.cat([cv_displacement(x[i:i+1, -1, 2:].to(a.dtype)) for i in range(2)])
    scaled, residual, cv = [], [], []
    before = model.register_forward_pre_hook(lambda _m, inputs: scaled.append(inputs[0].detach().cpu().clone()))
    after = model.register_forward_hook(lambda _m, _inputs, output: residual.append(output.detach().cpu().clone()))
    original_cv = pipeline.cv_displacement
    def capture_cv(*args, **kwargs):
        value = original_cv(*args, **kwargs)
        cv.append(value.detach().cpu().clone())
        return value
    monkeypatch.setattr(pipeline, 'cv_displacement', capture_cv)
    try:
        result = runtime.predict(s, c.candidates[0])
    finally:
        before.remove()
        after.remove()
    assert all(v.active_model == 'M5a' for v in result.vessels)
    differences = [torch.max(torch.abs(torch.cat(actual) - expected)).item() for actual, expected in
                   ((scaled, expected_scaled), (residual, expected_residual), (cv, expected_cv))]
    print('CPU_INTERMEDIATE_MAX_ABS scaled,residual,cv=', differences)
    assert max(differences) == 0


def test_reject_arbitrary_and_stale(fixture, runtime):
    p, s, c = fixture
    with pytest.raises(RuntimeUnavailable, match='INPUT'):
        runtime.predict(s, replace(c.candidates[0]))
    with pytest.raises(RuntimeUnavailable, match='INPUT'):
        runtime.predict(replace(s), c.candidates[0])
    with pytest.raises(RuntimeUnavailable, match='INPUT'):
        runtime.predict(s, torch.zeros(2, 10, 4))
    p.control('SEEK', '2024-11-01T00:08:00Z')
    with pytest.raises(RuntimeUnavailable, match='INPUT'):
        runtime.predict(s, c.candidates[0])


def test_provider_issued_features_are_bound_to_exact_snapshot_and_pair(fixture):
    p, s, c = fixture
    encounter, reason = p.encounter(s, c.candidates[0])
    assert reason is None
    features = p.features(s, encounter)
    assert p.is_issued_features(s, encounter, features)
    assert not p.is_issued_features(s, encounter, replace(features))
    recomputed = p.features(s, encounter)
    np.testing.assert_array_equal(recomputed.history, features.history)
    np.testing.assert_array_equal(recomputed.anchors_en, features.anchors_en)
    assert recomputed.origin_lat_lon == features.origin_lat_lon
    features = recomputed

    other, reason = p.encounter(s, c.candidates[1])
    assert reason is None
    assert not p.is_issued_features(s, other, features)

    p.control('SEEK', '2024-11-01T00:08:00Z')
    with pytest.raises(ValueError, match='STALE'):
        p.is_issued_features(s, encounter, features)


@pytest.mark.parametrize('bad', ['shape', 'dtype', 'nonfinite', 'frame'])
def test_feature_corruption_fails_closed(fixture, runtime, monkeypatch, bad):
    p, s, c = fixture
    get_features = p.features
    def corrupt(*args):
        f = get_features(*args)
        if bad == 'shape':
            return replace(f, history=f.history[:, :9])
        if bad == 'dtype':
            return replace(f, history=f.history.astype(np.float64))
        if bad == 'nonfinite':
            x = f.history.copy()
            x[0, 0, 0] = np.nan
            return replace(f, history=x)
        return replace(f, frame='OTHER')
    monkeypatch.setattr(p, 'features', corrupt)
    with pytest.raises(RuntimeUnavailable, match='INPUT'):
        runtime.predict(s, c.candidates[0])


def test_pin_change_after_load_fails_without_fallback(config, fixture, tmp_path, monkeypatch):
    pin = tmp_path / 'pin.json'
    shutil.copyfile(config.pin_path, pin)
    p, s, c = fixture
    service = M5aRuntime(replace(config, pin_path=pin), p)
    pin.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(service, '_run_vessel', lambda *args: pytest.fail('must not run model or fallback'))
    with pytest.raises(RuntimeUnavailable, match='ARTIFACT'):
        service.predict(s, c.candidates[0])
    service.close()


@pytest.mark.parametrize('failure', ['pin', 'checkpoint', 'scaler'])
def test_artifact_failure_closed(config, fixture, tmp_path, failure):
    if os.name == 'nt' and not str(tmp_path).startswith('\\\\?\\'):
        tmp_path = Path('\\\\?\\' + str(tmp_path))
    target = tmp_path / 'package'
    shutil.copytree(config.package_path, target)
    pin = tmp_path / 'pin.json'
    shutil.copyfile(config.pin_path, pin)
    if failure == 'pin':
        pin.write_text('{}', encoding='utf-8')
    elif failure == 'checkpoint':
        (target / 'snapshot/artifacts/checkpoints/s3_t10_20261124_seed20261110_run01/best_model.pt').write_bytes(b'bad')
    else:
        (target / 'snapshot/artifacts/checkpoints/s3_t10_20261124_seed20261110_run01/x_scaler.json').unlink()
    with pytest.raises(RuntimeUnavailable, match='ARTIFACT'):
        M5aRuntime(replace(config, package_path=target, pin_path=pin), fixture[0])


def test_fallback_and_mixed_metadata(fixture, runtime, monkeypatch):
    _, s, c = fixture
    actual = module.forecast
    calls = [0]
    def fail_once(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError('injected technical failure')
        return actual(*args, **kwargs)
    monkeypatch.setattr(module, 'forecast', fail_once)
    result = runtime.predict(s, c.candidates[0])
    assert [v.active_model for v in result.vessels] == ['CV', 'M5a']
    assert result.vessels[0].fallback_reason and not result.risk_eligible


def test_severe_qc_then_fallback_and_cv_failure(fixture, runtime, monkeypatch):
    _, s, c = fixture
    original = module.severe_qc
    calls = [0]
    def severe_first(pred, anchor):
        calls[0] += 1
        return torch.ones(1, dtype=torch.bool) if calls[0] == 1 else original(pred, anchor)
    monkeypatch.setattr(module, 'severe_qc', severe_first)
    result = runtime.predict(s, c.candidates[0])
    assert result.vessels[0].active_model == 'CV'
    monkeypatch.setattr(module, 'forecast', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('failure')))
    monkeypatch.setattr(module, 'project_forecast', lambda *a, **k: (_ for _ in ()).throw(ValueError('failure')))
    result = runtime.predict(s, c.candidates[0])
    assert result.status == 'UNAVAILABLE' and all(v.en is None for v in result.vessels)


@pytest.mark.parametrize('action', ['SEEK', 'RESET'])
def test_seek_during_inference_discards_and_bounds_concurrency(fixture, runtime, monkeypatch, action):
    p, s, c = fixture
    entered, resume = threading.Event(), threading.Event()
    old = runtime._run_vessel
    def slow(*args):
        entered.set()
        assert resume.wait(20)
        return old(*args)
    monkeypatch.setattr(runtime, '_run_vessel', slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runtime.predict, s, c.candidates[0])
        assert entered.wait(20)
        with pytest.raises(RuntimeUnavailable, match='CONCURRENCY'):
            runtime.predict(s, c.candidates[0])
        if action == 'SEEK':
            p.control('SEEK', '2024-11-01T00:08:00Z')
        else:
            p.control('RESET')
        resume.set()
        with pytest.raises(RuntimeUnavailable, match='STALE'):
            future.result(timeout=20)


def test_cuda_smoke_measurement(config, fixture, runtime):
    if not torch.cuda.is_available():
        pytest.skip('CUDA unavailable')
    p, s, c = fixture
    start = time.perf_counter()
    cpu = runtime.predict(s, c.candidates[0])
    cpu_seconds = time.perf_counter() - start
    gpu = M5aRuntime(replace(config, device='cuda'), p)
    start = time.perf_counter()
    result = gpu.predict(s, c.candidates[0])
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    diffs = [np.max(np.abs(a.en - b.en)) for a, b in zip(cpu.vessels, result.vessels)]
    print('CUDA_SMOKE_MAX_ABS_NM=', max(diffs), 'CPU_SECONDS=', cpu_seconds, 'CUDA_SECONDS=', elapsed)
    assert result.status == 'AVAILABLE' and all(np.isfinite(v.en).all() for v in result.vessels)
    gpu.close()
