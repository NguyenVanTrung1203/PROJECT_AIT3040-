from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import pytest
from src.protocol.calibration_protocol import (ProtocolError, load_protocol, threshold_grid,
                                               validate_group_assignment, validate_protocol)

CONFIG = Path('configs/s4_calibration_protocol.yaml')

@pytest.fixture
def config():
    return load_protocol(CONFIG)


def test_all_decisions_approved(config):
    assert config['approval']['decisions'] == {f'D{i}':'APPROVED_BY_TRUNG' for i in range(1,8)}


def test_d1_gates_and_undefined(config):
    g=config['mandatory_gates']
    assert (g['overall_recall_min'],g['real_ais_fpr_max'],g['synthetic_ais_recall_min'],g['close_positive_recall_min'],g['severe_qc_count_max']) == (.90,.12,.90,.95,0)
    assert g['undefined_metric']=='NA_AND_GATE_CANNOT_PASS'


def test_grid_exact_inclusive(config):
    grid=threshold_grid(config)
    assert len(grid)==201 and grid[0]==Decimal('0') and grid[-1]==Decimal('1')
    assert all(b-a==Decimal('.005') for a,b in zip(grid,grid[1:]))


def test_d1_tiebreak_and_no_solution(config):
    c=config['calibration']
    assert c['objective']=='maximize_F1'
    assert c['tie_break']==['lower_real_ais_fpr','higher_overall_recall','lower_threshold']
    assert c['no_feasible_threshold']=='NO_FEASIBLE_THRESHOLD'
    assert set(c['infeasible_report']) == {'violated_gates','available_operating_points','pareto_tradeoff','valid_threshold_count'}


def test_d2_absolute_percentage_point_and_ade_ratios(config):
    g=config['comparative_gates']
    assert (g['recall_delta_min_absolute'],g['real_ais_fpr_delta_max_absolute'],g['f1_delta_min_absolute'])==(-.01,.01,-.01)
    assert (g['overall_ade_max_ratio'],g['real_ais_ade_max_ratio'])==(1.10,1.10)
    assert g['delta_convention']=='M5a_minus_CV'
    assert g['cv_infeasible_status']=='D2_CONDITIONAL'
    assert g['v1_unavailable_status']=='V1_BASELINE_UNAVAILABLE' and not g['v1_unavailable_blocks_cv_m5a_calibration']
    assert not g['statistical_noninferiority_claim']


def test_close_positive_is_per_encounter(config):
    c=config['mandatory_gates']['close_positive'];g=config['comparative_gates']
    assert (c['source'],c['label'],c['distance'],c['maximum_exclusive_nm'])==('synthetic_ais','positive','ground_truth_future_minimum_haversine_nm',.1)
    assert not c['scoring_uses_future'] and c['subgroup_may_be_used_for_calibration_gate']
    assert g['compare_close_positive_by_encounter_id'] and g['added_close_positive_false_negative_count_max']==0


def test_group_folds_are_never_split(config):
    assert config['grouped_cross_fitting']['folds'] is None
    assert validate_group_assignment(['a','a','b'],[0,0,1])
    with pytest.raises(ProtocolError): validate_group_assignment(['a','a','b'],[0,1,1])
    with pytest.raises(ProtocolError): validate_group_assignment(['a',None],[0,1])


def test_bootstrap_and_sensitivity(config):
    b=config['clustered_bootstrap']
    assert (b['unit'],b['paired'],b['preserve_multiplicity'],b['repetitions'],b['seed'],b['confidence_level'],b['interval'])==('dependency_group',True,True,5000,20261124,.95,'percentile')
    assert b['undefined_metric']=='NA_REPORT_COUNT_AND_RATE' and b['min_valid_repetitions'] == 4750
    s=config['sensitivity_analysis']
    assert s['scenarios']=={'S1':'all_835','S2':'exclude_largest_279','S3':'largest_only_556'}
    assert s['fixed_reference_thresholds'] and not s['select_alternative_threshold']
    assert config['threshold_stability']['reselect_each_model_per_replicate'] and not config['threshold_stability']['out_of_sample_evaluation']


def test_device_parity_and_policy(config):
    p=config['device_parity']
    assert (p['position_max_abs_coordinate_nm'],p['aggregate_ade_abs_nm'],p['aggregate_fde_abs_nm'],p['risk_score_max_abs'])==(5e-5,1e-6,1e-6,5e-5)
    assert p['vessels_exceeding_position_tolerance_max']==0 and p['decision_parity_fraction']==1
    assert p['decision_mismatch_status']=='RISK_DECISION_PARITY_REVIEW_REQUIRED'
    assert not p['rounding_or_epsilon_to_force_pass'] and not p['missing_cuda_causes_cv_fallback']


def test_lock_and_test_access_fail_closed(config):
    m=config['model_lock']; t=config['test_benchmark'];p=config['production_restrictions']
    assert m['current']=='CANDIDATE' and not m['locked'] and not m['automatic_transition']
    assert 'Trung_final_approval' in m['prerequisites']
    assert not t['authorized'] and not config['dataset']['test_tensor_access_before_approved_lock']
    assert set(t['open_after'])=={'T14_complete','Trung_approved_conditional_lock','package_version_and_manifest_verified','T15_protocol_fixed'}
    assert not t['threshold_reselection'] and not t['retrain_recalibrate_model_selection']
    assert not p['approved'] and not p['production_alert']


def test_diagnostic_thresholds_not_calibrated(config):
    c=config['calibration']
    assert c['calibrated_m5a_threshold'] is None and c['calibrated_cv_threshold'] is None
    assert c['diagnostic_thresholds']=={'CV':.435,'M5a':.420,'status':'HISTORICAL_NOT_CALIBRATED'}


@pytest.mark.parametrize('section,key,value',[
    ('mandatory_gates','overall_recall_min',.89),('mandatory_gates','real_ais_fpr_max',.13),
    ('mandatory_gates','close_positive_recall_min',.94),('comparative_gates','overall_ade_max_ratio',1.11),
    ('comparative_gates','added_close_positive_false_negative_count_max',1),('clustered_bootstrap','repetitions',4999),
    ('clustered_bootstrap','seed',123),('device_parity','decision_parity_fraction',.99),
    ('test_benchmark','authorized',True),('model_lock','locked',True),('production_restrictions','approved',True),
    ('calibration','calibrated_cv_threshold',.435),('grouped_cross_fitting','folds',5),
])
def test_changed_approved_values_are_rejected(config,section,key,value):
    other=deepcopy(config);other[section][key]=value
    with pytest.raises(ProtocolError):validate_protocol(other)


def test_duplicate_yaml_key_rejected(tmp_path):
    p=tmp_path/'bad.yaml';p.write_text('a: 1\na: 2\n',encoding='utf-8')
    with pytest.raises(ProtocolError):load_protocol(p)
