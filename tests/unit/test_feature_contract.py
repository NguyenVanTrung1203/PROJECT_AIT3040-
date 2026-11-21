import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import yaml

from scripts.verify_feature_contract import asof_valid, common_en, inverse_en, proposed_pair_id, velocity_en, verify

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def contracts():
    return {name:json.loads((ROOT/'contracts'/f'{name}_contract.json').read_text(encoding='utf-8')) for name in ('feature','temporal','rule_input','forecast')}


@pytest.fixture(scope='module')
def verified():
    return verify()


def test_feature_order_matches_data_and_model(contracts):
    data=yaml.safe_load((ROOT/'configs/data_config.yaml').read_text(encoding='utf-8'))
    model=yaml.safe_load((ROOT/'configs/model_config.yaml').read_text(encoding='utf-8'))
    assert contracts['feature']['feature_order']==data['feature_order']==model['features']['order']
    assert contracts['feature']['shapes']['vessel']==[data['history_length'],data['input_features']]


def test_feature_dtype_units_and_unscaled_velocity(contracts):
    f=contracts['feature']
    assert f['model_input_dtype']=='float32' and f['coordinate_intermediate_dtype']=='float64'
    assert f['units']==['nautical_mile','nautical_mile','knot','knot']
    assert f['constant_velocity_uses']=='unscaled_anchor_velocity_kn'


@pytest.mark.parametrize('angle,expected',[(0,(0,10)),(90,(10,0)),(180,(0,-10)),(270,(-10,0)),(360,(0,10))])
def test_nautical_velocity_directions(angle,expected):
    np.testing.assert_allclose(velocity_en(10,angle),expected,atol=1e-12)
    np.testing.assert_allclose(velocity_en(0,angle),[0,0],atol=1e-12)


def test_temporal_offsets_and_no_overlap(contracts):
    t=contracts['temporal']; h=t['history_offsets_minutes']; f=t['forecast_offsets_minutes']
    assert h==list(range(-9,1)) and f==list(range(1,16)) and not set(h)&set(f)
    assert t['time_zone']=='UTC' and t['timestep_minutes']==1


@pytest.mark.parametrize('seconds,expected',[(-1,False),(0,True),(59.999,True),(60,True),(60.001,False)])
def test_asof_boundaries(seconds,expected):
    grid=pd.Timestamp('2025-09-01T12:00:00Z'); source=grid-pd.Timedelta(seconds=seconds)
    assert asof_valid(grid,source) is expected


def test_asof_rejects_naive_timestamp():
    with pytest.raises(ValueError): asof_valid('2025-09-01 12:00:00','2025-09-01T12:00:00Z')


def test_geographic_roundtrip_and_known_direction():
    lat0,lon0=0.0,10.0
    np.testing.assert_allclose(common_en(1.0,11.0,lat0,lon0),[60,60],rtol=0,atol=1e-12)
    lat,lon=57.1,11.2; xy=common_en(lat,lon,57.0,11.0)
    np.testing.assert_allclose(inverse_en(*xy,57.0,11.0),[lat,lon],rtol=0,atol=1e-10)
    with pytest.raises(ValueError): inverse_en(1,1,90,0)


def test_anchor_own_relative_and_distance():
    anchors=np.array([[1.,2.],[9.,7.]])
    points=np.array([[2.,4.],[10.,10.]])
    relative=points-anchors
    np.testing.assert_array_equal(relative+anchors,points)
    np.testing.assert_array_equal((anchors-anchors),np.zeros((2,2)))
    assert np.linalg.norm((relative+anchors)[0]-(relative+anchors)[1])==pytest.approx(10.)
    assert not np.array_equal(relative+anchors[0],points)


def test_pair_identity_unordered_and_distinct(contracts):
    a,b='physical_mmsi:123456789','physical_mmsi:987654321'
    assert proposed_pair_id(a,b)==proposed_pair_id(b,a)
    assert proposed_pair_id(a,b).startswith('pair:v1:')
    assert proposed_pair_id(a,b) != 'encounter:2025-09-01T12:00:00Z'
    with pytest.raises(ValueError): proposed_pair_id(a,a)
    assert contracts['feature']['simulated_mmsi'].startswith('nullable')


@pytest.mark.parametrize('split,n,v',[('train',1440,2880),('validation',835,1670)])
def test_full_history_mapping_rule_and_coordinate_feasibility(verified,split,n,v):
    x=verified['splits'][split]
    assert (x['encounters_checked'],x['encounters_complete'],x['vessels_checked'],x['history_rows']) == (n,n,v,v*10)
    assert x['encounters_missing_or_bad_mapping']==0 and x['rule_shape_per_encounter']==[2,10,2]
    assert x['history_alignment']==x['future_exclusion']=='PASS'
    assert x['velocity_max_abs_error_kn'] < verified['velocity_tolerance_kn']
    assert x['geographic_roundtrip_max_abs_error_degrees'] < verified['roundtrip_tolerance_degrees']
    assert x['anchor_max_abs_error_nm'] < 1e-10 and x['distance_max_abs_error_nm'] < 1e-10
    assert x['target_reconstruction_max_abs_error_nm'] < 1e-6


def test_rule_history_order_and_sources(contracts,verified):
    r=contracts['rule_input']; assert r['channels']==['SOG','COG'] and r['history_shape']==[2,10,2]
    sources=verified['splits']['validation']['source_timestamp_observations']
    assert sources['real_ais_kattegat_v3']['source_timestamp_field']=='original_source_timestamp_utc'
    assert sources['augmented_real_ais_kattegat_v3']['source_timestamp_field']=='simulated_source_timestamp_utc'
    assert sources['augmented_real_ais_kattegat_v3']['invalid_age_count']==0


def test_forecast_and_invalid_data_specification(contracts):
    f=contracts['forecast']; a=f['forecast']; invalid=f['invalid_data']
    assert a['forecast_displacement_en_nm']==a['forecast_common_en_nm']==a['forecast_lat_lon']==[2,15,2]
    assert a['forecast_lat_lon_order']==['latitude','longitude'] and a['forecast_timestamps']==[15]
    assert invalid['missing_history_or_stale']=='INSUFFICIENT_DATA' and invalid['nan_or_inf']=='INSUFFICIENT_DATA'
    assert 'valid_data' in f['fallback'] and 'no_official_alert' in invalid['uncalibrated_threshold']
    risk=yaml.safe_load((ROOT/'configs/risk_config.yaml').read_text(encoding='utf-8'))
    assert risk['threshold']['calibration_status']=='not_calibrated' and not risk['threshold']['allow_reference_for_official_alerts']


def test_json_contracts_are_drafts_without_machine_paths(contracts):
    for contract in contracts.values():
        assert contract['version']=='1.0.0-draft' and contract['status']=='proposed_pending_team_review'
        raw=json.dumps(contract).lower()
        assert 'c:\\\\users' not in raw and '/users/' not in raw
