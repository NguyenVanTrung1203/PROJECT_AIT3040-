"""Contract examples and known implementation gaps; no production runtime implied."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / 'contracts'
BASE = 'https://schemas.ait3040.invalid/contracts/'


def read(path):
    return json.loads((CONTRACTS / path).read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def track_validator():
    common = read('common.schema.json')
    track = read('track_snapshot.schema.json')
    common['$id'] = BASE + 'common.schema.json'
    track['$id'] = BASE + 'track_snapshot.schema.json'
    registry = Registry().with_resource(common['$id'], Resource.from_contents(common))
    return Draft202012Validator(track, registry=registry, format_checker=FormatChecker())


@pytest.mark.parametrize('field', ['schema_version', 'mmsi'])
def test_schema_rejects_missing_required_track_fields(track_validator, field):
    track = read('mock/tracks/track_simulated.json')
    assert track_validator.is_valid(track)
    del track[field]
    assert not track_validator.is_valid(track)


@pytest.mark.parametrize('field', ['schema_version', 'mmsi'])
def test_t04_pydantic_rejects_missing_required_fields(field):
    from backend.app.mock_tracks import MOCK_TRACKS, TrackSnapshot
    from pydantic import ValidationError
    payload = MOCK_TRACKS[0].model_dump(mode='json')
    del payload[field]
    with pytest.raises(ValidationError):
        TrackSnapshot.model_validate(payload)


@pytest.mark.parametrize(('field', 'value', 'valid'), [
    ('mmsi', None, True), ('mmsi', '123456789', True),
    ('mmsi', '1234', False), ('schema_version', '1.0.1', False),
    ('schema_version', 1, False),
])
def test_t04_pydantic_schema_parity_for_fields(track_validator, field, value, valid):
    from backend.app.mock_tracks import MOCK_TRACKS, TrackSnapshot
    from pydantic import ValidationError
    payload = MOCK_TRACKS[0].model_dump(mode='json')
    payload[field] = value
    assert track_validator.is_valid(payload) is valid
    if valid:
        assert TrackSnapshot.model_validate(payload).model_dump(mode='json') == payload
    else:
        with pytest.raises(ValidationError):
            TrackSnapshot.model_validate(payload)


@pytest.mark.parametrize('mutation', ['current_state', 'grid', 'future_source'])
def test_t04_snapshot_semantic_invariants(mutation):
    from datetime import timedelta
    from backend.app.mock_tracks import MOCK_TRACKS, TrackSnapshot
    from pydantic import ValidationError
    payload = MOCK_TRACKS[0].model_dump(mode='python')
    if mutation == 'current_state':
        payload['current_state']['latitude'] += 1
    elif mutation == 'grid':
        payload['history'][0]['nominal_timestamp'] -= timedelta(seconds=1)
    else:
        payload['history'][0]['source_timestamp'] += timedelta(seconds=1)
    with pytest.raises(ValidationError):
        TrackSnapshot.model_validate(payload)


def test_selected_source_and_age_contract():
    contract = read('temporal_contract.json')
    asof = contract['asof']
    assert (asof['minimum_age_seconds'], asof['maximum_age_seconds'], asof['both_boundaries_inclusive']) == (0, 60, True)
    assert asof['conflicting_duplicate_key'] == 'exclude_all_records_for_MMSI_and_timestamp'
    assert asof['identical_duplicate_key'] == 'stable_first_record'
    assert 'simulated_source_timestamp_utc' in contract['source_timestamp']['synthetic_AIS']
    assert 'original_source_timestamp_utc' in contract['source_timestamp']['real_AIS']


@pytest.mark.parametrize(('age', 'valid'), [(0, True), (60, True), (-1, False), (60.01, False)])
def test_track_schema_ais_age_boundaries(track_validator, age, valid):
    track = read('mock/tracks/track_valid.json')
    track['history'][0]['source_age_seconds'] = age
    assert track_validator.is_valid(track) is valid


def test_feature_rule_shapes_and_offline_mapping():
    feature, rule = read('feature_contract.json'), read('rule_input_contract.json')
    assert feature['shapes']['encounter'] == [2, 10, 4]
    assert feature['model_input_dtype'] == 'float32'
    assert rule['history_shape'] == [2, 10, 2] and rule['source_dtype'] == 'float64'
    assert rule['channels'] == ['SOG', 'COG']
    assert 'without_resorting' in feature['offline_mapping']
    assert 'online_A_is_smaller_canonical_id_by_UTF8_bytes' in feature['replay_mapping_proposal']['A_B_order']


def test_pair_reference_vector_and_order_independence():
    from scripts.verify_feature_contract import proposed_pair_id
    a, b = 'physical_mmsi:000000001', 'physical_mmsi:000000002'
    expected = 'pair:v1:5edcd44d2d37a0ada2de37283483f76bbddc8bb9c5bb22b8992b7f7297cf5c18'
    assert proposed_pair_id(a, b) == proposed_pair_id(b, a) == expected
    for x, y in [(a, a), ('', b), (None, b)]:
        with pytest.raises(ValueError):
            proposed_pair_id(x, y)


def test_mock_reset_preserves_pair_but_isolates_alert_and_session():
    before = read('mock/alerts/alert_active.json')
    after = read('mock/alerts/alert_after_replay_reset.json')
    assert before['pair_id'] == after['pair_id']
    assert before['replay_session_id'] != after['replay_session_id']
    assert before['alert_id'] != after['alert_id']


def test_near_zero_mock_has_null_tcpa_and_available_components():
    response = read('mock/responses/risk_response_near_zero.json')
    assert response['current_cpa_status'] == 'UNDEFINED_LOW_RELATIVE_VELOCITY'
    assert response['current_tcpa_minutes'] is None and response['current_tcpa_clipped_minutes'] is None
    assert response['current_dcpa_nm'] is not None and response['current_cpa_score'] is not None
    assert response['risk_score'] == pytest.approx(.68 * response['predicted_cpa_score'] + .12 * response['current_cpa_score'] + .20 * response['rule_score'])
