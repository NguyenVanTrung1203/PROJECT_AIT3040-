from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import copy
import json
import os
import threading

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
import numpy as np
import pytest
import torch

from src.runtime.config import load_config, resolve_threshold
from src.runtime.m5a_service import M5aRuntime, RuntimeUnavailable
from src.runtime.risk_service import FixtureRiskHarness, AlertManager, _risk_components, _decision
from src.runtime.trusted_fixture import FixtureProvider
from src.risk.adapter import ref, verify_reference
from scripts.contract_identity_reference import encounter_id


@pytest.fixture(scope='module')
def config():
    torch.set_num_threads(1)
    return load_config(os.environ)


@pytest.fixture
def integration(config):
    provider = FixtureProvider(5)
    provider.create('2024-11-01T00:09:00Z')
    snapshot = provider.snapshot()
    coverage = provider.candidates(snapshot)
    model = M5aRuntime(config, provider)
    yield provider, snapshot, coverage, model, FixtureRiskHarness(provider, model)
    model.close()


def validator(name):
    root = Path(__file__).resolve().parents[2] / 'contracts'
    registry = Registry()
    base = 'https://schemas.ait3040.invalid/contracts/'
    for path in root.glob('*.schema.json'):
        doc = json.loads(path.read_text(encoding='utf-8'))
        doc['$id'] = base + path.name
        registry = registry.with_resource(doc['$id'], Resource.from_contents(doc))
    return Draft202012Validator({'$ref': base + name}, registry=registry, format_checker=FormatChecker())


def test_fixture_actual_full_coverage_and_schema(integration):
    p, snapshot, coverage, model, harness = integration
    risk_schema, alert_schema = validator('risk_response_v1.schema.json'), validator('alert_v1.schema.json')
    seen = []
    feature_calls = [0]
    original_features = p.features
    def count_features(current_snapshot, encounter):
        feature_calls[0] += 1
        return original_features(current_snapshot, encounter)
    p.features = count_features
    for anchor in ('0009', '0015'):
        if anchor == '0015':
            p.control('SEEK', '2024-11-01T00:15:00Z')
            snapshot = p.snapshot()
            coverage = p.candidates(snapshot)
        assert (coverage.expected, coverage.evaluated) == (10, 10)
        assert (coverage.eligible, coverage.unavailable) == ((6, 4) if anchor == '0009' else (10, 0))
        for index, candidate in enumerate(coverage.candidates):
            risk = harness.evaluate(snapshot, candidate, anchor + '-' + str(index))
            risk_schema.validate(risk)
            assert risk['pair_id'] == candidate.pair_id
            if candidate.unavailable_reason:
                assert risk['risk_score'] is None and risk['alert_triggered'] is None
            else:
                assert risk['model_status']['active_model'] == 'M5A'
                assert abs(risk['risk_score'] - (0.68*risk['predicted_cpa_score'] + 0.12*risk['current_cpa_score'] + 0.20*risk['rule_score'])) < 1e-14
                assert risk['alert_triggered'] == (risk['risk_score'] >= .420)
            seen.append(risk['alert_triggered'])
            keys = ('pair_id', 'anchor_timestamp', 'forecast_status', 'current_dcpa_nm', 'current_tcpa_minutes', 'predicted_min_distance_nm', 'predicted_closest_time_minutes', 'current_cpa_score', 'predicted_cpa_score', 'rule_score', 'risk_score', 'threshold', 'alert_triggered', 'decision_reason')
            print('FIXTURE_ROW', json.dumps({k: risk[k] for k in keys}, separators=(',', ':')))
        for alert in harness.alerts(snapshot):
            alert_schema.validate(alert)
    assert True in seen and False in seen and None in seen
    p.control('RESET')
    with pytest.raises(ValueError):
        harness.alerts(snapshot)
    snapshot = p.snapshot()
    assert harness.alerts(snapshot) == []
    assert feature_calls[0] == 16


def test_near_zero_tie_and_v4_parity():
    verify_reference()
    x = np.zeros((2, 10, 4), dtype=np.float32)
    a = np.array([[0., 0.], [0.5, 0.]])
    f = SimpleNamespace(history=x, anchors_en=a, sog_cog=tuple(tuple((0., 0.) for _ in range(10)) for _ in range(2)))
    predictions = np.stack([np.tile(anchor, (15, 1)) for anchor in a])
    forecast = SimpleNamespace(vessels=[SimpleNamespace(en=q) for q in predictions])
    result = _risk_components(f, forecast)
    assert result['current_cpa_status'] == 'UNDEFINED_LOW_RELATIVE_VELOCITY'
    assert result['current_tcpa_minutes'] is None and result['current_tcpa_clipped_minutes'] is None
    assert result['current_dcpa_nm'] == 0.5 and result['predicted_closest_time_minutes'] == 1
    assert result['rule_score'] == 0.5
    expected = ref.score(np.array([.5]), np.array([0.]), .16)[0]
    assert result['current_cpa_score'] == expected
    assert result['predicted_cpa_score'] == ref.score(np.array([.5]), np.array([1]))[0]
    assert result['risk_score'] == .68*result['predicted_cpa_score'] + .12*expected + .20*.5


def risk_row(timestamp, decision, encounter='enc1'):
    return {'replay_session_id': 'session', 'pair_id': 'pair', 'anchor_timestamp': timestamp,
        'encounter_id': encounter, 'vessel_ids': ['a','b'], 'alert_triggered': decision,
        'risk_score': .6, 'threshold': .42, 'predicted_min_distance_nm': .2,
        'predicted_closest_time_minutes': 3, 'current_dcpa_nm': .3,
        'current_tcpa_minutes': 2., 'model_status': {'active_model': 'M5A'}}


def test_alert_lifecycle_unavailable_out_of_order_and_concurrency():
    alerts = AlertManager()
    initial = risk_row('2024-11-01T00:09:00Z', True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(alerts.apply, [copy.deepcopy(initial) for _ in range(8)]))
    assert len(alerts.list('session')) == 1
    alert = alerts.list('session')[0]
    alerts.apply(risk_row('2024-11-01T00:10:00Z', None, 'enc2'))
    unavailable = alerts.list('session')[0]
    assert unavailable['alert_status'] == 'DATA_UNAVAILABLE' and unavailable['values_are_last_valid']
    assert unavailable['values_as_of'] == initial['anchor_timestamp'] and unavailable['risk_score'] == alert['risk_score']
    alerts.apply(risk_row('2024-11-01T00:08:00Z', False))
    assert alerts.list('session')[0]['alert_status'] == 'DATA_UNAVAILABLE'
    alerts.apply(risk_row('2024-11-01T00:11:00Z', True, 'enc3'))
    assert alerts.list('session')[0]['alert_status'] == 'ACTIVE'
    alerts.apply(risk_row('2024-11-01T00:12:00Z', False, 'enc4'))
    assert alerts.list('session')[0]['alert_status'] == 'RESOLVED'
    alerts.apply(risk_row('2024-11-01T00:13:00Z', True, 'enc5'))
    assert len(alerts.list('session')) == 2


def test_threshold_authority(config):
    for model, threshold in [('M5a', .420), ('CV', .435)]:
        result = resolve_threshold(config, (model, model))
        assert result.available and float(result.threshold) == threshold
        assert _decision(threshold, float(result.threshold)) is True
        assert _decision(threshold + .001, float(result.threshold)) is True
        assert _decision(threshold - .001, float(result.threshold)) is False
    assert _decision(.5, None) is None
    assert not resolve_threshold(None, ('M5a','M5a')).available
    assert not resolve_threshold(config, ('CV','M5a')).available
    assert not resolve_threshold(config, ('M5a','M5a'), official_alert=True).available
    assert not resolve_threshold(replace(config, lock_id='bad'), ('M5a','M5a')).available


def test_alert_state_variants_are_schema_valid(integration):
    _, s, c, _, harness = integration
    original = harness.evaluate(s, c.candidates[0], 'schema-lifecycle')
    manager = AlertManager()
    schema = validator('alert_v1.schema.json')
    for minute, decision in [(9, True), (10, None), (11, True), (12, False)]:
        row = copy.deepcopy(original)
        row['anchor_timestamp'] = f'2024-11-01T00:{minute:02d}:00Z'
        row['encounter_id'] = encounter_id(s.session_id, row['pair_id'], row['anchor_timestamp'])
        row['alert_triggered'] = decision
        manager.apply(row)
        schema.validate(manager.list(s.session_id)[-1])


def test_reject_forged_candidate_and_snapshot(integration):
    _, s, c, _, harness = integration
    with pytest.raises(RuntimeUnavailable):
        harness.evaluate(s, replace(c.candidates[0]), 'r')
    with pytest.raises(RuntimeUnavailable):
        harness.evaluate(replace(s), c.candidates[0], 'r')


def test_harness_reuses_exact_issued_features_once(integration):
    p, snapshot, coverage, _, harness = integration
    calls = [0]
    original = p.features
    def counted(current_snapshot, encounter):
        calls[0] += 1
        return original(current_snapshot, encounter)
    p.features = counted
    risk = harness.evaluate(snapshot, coverage.candidates[0], 'single-feature-build')
    assert calls[0] == 1
    assert risk['forecast_status'] == 'AVAILABLE'


def test_idempotency_session_and_snapshot_conflict(integration):
    p, s, c, _, harness = integration
    a = harness.evaluate(s, c.candidates[0], 'retry')
    assert harness.evaluate(s, c.candidates[0], 'retry') == a
    assert harness.evaluate(s, c.candidates[0], 'other') == a
    with pytest.raises(RuntimeUnavailable, match='REQUEST_ID_CONFLICT'):
        harness.evaluate(s, c.candidates[1], 'retry')
    s2 = p.snapshot()
    c2 = p.candidates(s2)
    with pytest.raises(RuntimeUnavailable, match='SNAPSHOT_CONFLICT'):
        harness.evaluate(s2, c2.candidates[0], 'new')
    p.control('SEEK', '2024-11-01T00:08:00Z')
    with pytest.raises(RuntimeUnavailable):
        harness.evaluate(s, c.candidates[0], 'old')


def test_evaluation_cache_and_alerts_are_session_isolated(integration):
    p, first_snapshot, first_coverage, _, harness = integration
    first = harness.evaluate(first_snapshot, first_coverage.candidates[0], 'same-request-id')
    first_session = first_snapshot.session_id

    p.create('2024-11-01T00:09:00Z')
    second_snapshot = p.snapshot()
    second_coverage = p.candidates(second_snapshot)
    second = harness.evaluate(second_snapshot, second_coverage.candidates[0], 'same-request-id')

    assert second_snapshot.session_id != first_session
    assert first['replay_session_id'] == first_session
    assert second['replay_session_id'] == second_snapshot.session_id
    assert first['encounter_id'] != second['encounter_id']
    assert first['risk_score'] == second['risk_score']
    assert len(harness._alerts.list(first_session)) == 1
    assert len(harness._alerts.list(second_snapshot.session_id)) == 1


@pytest.mark.parametrize('mode', ['mixed', 'unavailable'])
def test_mixed_or_unavailable_forecast_is_not_a_decision(integration, monkeypatch, mode):
    _, snapshot, coverage, model, harness = integration
    actual = model.predict(snapshot, coverage.candidates[0])
    if mode == 'mixed':
        second = replace(actual.vessels[1], active_model='CV', fallback_reason='MOCK_FAILURE')
        changed = replace(actual, vessels=(actual.vessels[0], second))
    else:
        first = replace(actual.vessels[0], active_model=None, en=None, qc_status='UNAVAILABLE')
        changed = replace(actual, vessels=(first, actual.vessels[1]), status='UNAVAILABLE')
    monkeypatch.setattr(model, 'predict', lambda *args: changed)
    risk = harness.evaluate(snapshot, coverage.candidates[0], mode)
    validator('risk_response_v1.schema.json').validate(risk)
    assert risk['risk_score'] is None and risk['alert_triggered'] is None
    assert risk['decision_status'] == 'UNAVAILABLE' and risk['forecast_status'] == 'UNAVAILABLE'
    assert risk['model_status']['data_status'] == 'VALID'
    assert harness.alerts(snapshot) == []


def test_concurrent_retry_is_idempotent(integration):
    _, snapshot, coverage, _, harness = integration
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(harness.evaluate, snapshot, coverage.candidates[0], 'same') for _ in range(2)]
        first, second = (f.result(timeout=60) for f in futures)
    assert first == second and len(harness.alerts(snapshot)) == 1


def test_race_seek_cannot_commit(integration, monkeypatch):
    p, s, c, model, harness = integration
    started, proceed = threading.Event(), threading.Event()
    actual = model.predict
    def delayed(*args):
        output = actual(*args)
        started.set()
        assert proceed.wait(30)
        return output
    monkeypatch.setattr(model, 'predict', delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(harness.evaluate, s, c.candidates[0], 'race')
        assert started.wait(30)
        p.control('SEEK', '2024-11-01T00:08:00Z')
        proceed.set()
        with pytest.raises(RuntimeUnavailable):
            pending.result(timeout=40)
    new = p.snapshot()
    assert harness.alerts(new) == []
