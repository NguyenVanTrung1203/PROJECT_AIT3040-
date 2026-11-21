from pathlib import Path
import re

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def configs():
    def read(name):
        with (ROOT / 'configs' / name).open(encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {name:read(name + '_config.yaml') for name in ('data','model','projection','risk')}


@pytest.mark.parametrize('name', ['model','projection','risk'])
def test_configs_are_mappings(configs, name):
    assert isinstance(configs[name], dict) and configs[name]


def test_shape_and_features_match_data_contract(configs):
    model, data = configs['model'], configs['data']
    m = model['model']
    assert (m['history_length'],m['input_size'],m['forecast_horizon'],m['output_dimensions'],m['output_size']) == (10,4,15,2,30)
    assert (m['history_length'],m['input_size'],m['forecast_horizon'],m['output_dimensions']) == tuple(data[k] for k in ('history_length','input_features','forecast_horizon','output_dimensions'))
    assert model['features']['order'] == data['feature_order']
    assert (model['features']['position_unit'], model['features']['velocity_unit']) == (data['position_unit'], data['velocity_unit'])


def test_parameter_count_without_creating_model(configs):
    m=configs['model']['model']; h=m['hidden_size']; inp=m['input_size']; fc=m['fc_hidden_size']; out=m['output_size']
    assert (m['num_layers'],m['bias'],m['bidirectional'],m['batch_first']) == (1,True,False,True)
    count = 3*h*(inp+h+2) + h*fc+fc + fc*out+out
    assert count == m['expected_parameter_count'] == 15390


def test_training_and_seeds(configs):
    t=configs['model']['training']
    assert (t['optimizer'],t['learning_rate'],t['weight_decay'],t['batch_size']) == ('AdamW',0.0025,0.0001,256)
    assert (t['min_epochs'],t['max_epochs'],t['early_stopping_patience']) == (25,45,8)
    assert t['seeds'] == [20261110,20261111,20261112]
    assert t['shuffle_train'] and not t['drop_last'] and t['num_workers']==0
    assert t['gradient_clipping']=='none' and t['learning_rate_scheduler']=='none'
    assert t['device'] in t['allowed_devices'] == ['auto','cpu','cuda']


def test_loss_and_scalers(configs):
    m=configs['model']; loss=m['training']['loss']; s=m['scaling']
    assert [loss[k] for k in ('encoded_residual_mse','physical_position_mse','velocity_mse_weight','acceleration_mse_weight','kinematic_penalty_weight')] == [1.0,0.15,0.02,0.002,0.001]
    assert loss['reduction']=='mean' and loss['decoded_physical_space']
    assert s['fit_split']=='train' and s['input_scaler']==s['residual_scaler']=='StandardScaler'
    assert s['input_fit_shape']==[-1,4] and s['residual_fit_shape']==[-1,2] and s['scale_epsilon_after_fit']==1e-6


def test_checkpoint_and_seed_selection(configs):
    m=configs['model']; c=m['checkpoint_selection']
    assert c['split']=='validation' and c['criteria']=='lowest_real_ais_ADE_nm' and c['require_projected_qc_pass']
    assert c['best_epoch'] is c['selected_seed'] is c['selected_checkpoint'] is None
    assert m['seed_selection']['split']=='validation' and not m['seed_selection']['historical_values_are_official']
    assert m['seed_selection']['criteria_order'][0:2] == ['close_recall_desc','F1_desc']


def test_projection_and_qc(configs):
    p=configs['projection']['projection']; q=configs['projection']['kinematic_qc']; data=configs['data']
    assert (p['max_speed_kn'],p['max_vector_velocity_change_kn_per_min'],p['max_turn_degrees_per_min']) == (49.999,2.999,29.9)
    assert (q['max_speed_kn'],q['max_scalar_speed_change_kn_per_min'],q['max_turn_degrees_per_min']) == (50,3,30)
    assert p['turn_applies_when_both_speeds_at_least_kn']==q['turn_applies_when_both_speeds_at_least_kn']==3
    assert p['position_unit']==data['position_unit'] and p['velocity_unit']==data['velocity_unit']
    assert p['order'][1:4] == ['cap_desired_speed','cap_vector_velocity_change','limit_turn_if_moving']


def test_cpa_and_weights(configs):
    r=configs['risk']; weights=r['cc_dri']['weights']
    assert weights == {'predicted_cpa':0.68,'current_cpa':0.12,'rule':0.20}
    assert sum(weights.values())==pytest.approx(1.0)
    assert r['current_cpa']['score_distance_scale_nm']==0.16 and r['predicted_cpa']['score_distance_scale_nm']==0.14
    assert not r['predicted_cpa']['include_anchor'] and not r['score_is_collision_probability']


def test_calibration_and_official_threshold(configs):
    r=configs['risk']; t=r['threshold']; c=r['calibration']
    assert c['split']=='validation' and not c['use_test_for_selection_or_calibration']
    assert (c['grid_start'],c['grid_stop'],c['grid_step'],c['recall_minimum']) == (0,1,0.005,0.9)
    assert c['tie_break']==['lower_real_ais_FPR','higher_recall','lower_threshold']
    assert t['calibration_status']=='not_calibrated' and t['calibrated_m5a'] is t['calibrated_cv'] is None
    assert not t['allow_reference_for_official_alerts'] and not r['fallback']['fallback_uses_reference_threshold_for_official_alerts']


@pytest.mark.parametrize('filename',['model_config.yaml','projection_config.yaml','risk_config.yaml'])
def test_no_machine_specific_paths(filename):
    data=(ROOT/'configs'/filename).read_text(encoding='utf-8')
    assert not re.search(r'(?i)[a-z]:[\\/]|/Users/|/home/',data)
