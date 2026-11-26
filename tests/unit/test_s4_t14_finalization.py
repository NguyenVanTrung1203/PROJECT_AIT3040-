from fractions import Fraction
import hashlib
import math
import random
import pytest
from src.protocol.calibration_protocol import ProtocolError
from src.protocol.calibration_primitives import CountMetrics, subgroup_recall, select_candidate, classify_prediction, confidence_support, check_dependency_rows
from src.protocol.group_assignment import assign_groups


def candidate(k, tp=90, fp=10, fn=10, tn=90, real_fp=10, real_tn=90):
    return {'k':k,'overall':CountMetrics(tp,fp,fn,tn),'real':CountMetrics(0,real_fp,0,real_tn),'synthetic_tp_fn':(90,10),'close_tp_fn':(19,1),'severe_qc':0}


def test_exact_ties_lower_index_and_order_independence():
    cs=[candidate(50),candidate(60),candidate(20)]
    assert select_candidate(cs)==20
    assert select_candidate(list(reversed(cs)))==20


def test_fpr_tie_break():
    a=candidate(30,real_fp=10,real_tn=90);b=candidate(70,real_fp=9,real_tn=91)
    assert select_candidate([a,b])==70


def test_exact_near_tie_and_boundary():
    assert CountMetrics(900000000,0,100000000,30).ratio('recall')==Fraction(9,10)
    assert CountMetrics(899999999,0,100000001,30).ratio('recall')<Fraction(9,10)
    assert CountMetrics(0,3,0,22).ratio('fpr')==Fraction(3,25)
    assert Fraction(89,100)-Fraction(90,100)==Fraction(-1,100)


def test_undefined_and_support_boundaries():
    assert CountMetrics(0,0,0,30).support('recall')==('NA',None)
    assert CountMetrics(29,0,0,30).support('recall')[0]=='LOW_SUPPORT'
    assert CountMetrics(30,0,0,30).support('recall')[0]=='VALID_SUPPORT'
    assert subgroup_recall(9,0,10)[0]=='LOW_SUPPORT'
    assert subgroup_recall(10,0,10)[0]=='VALID_SUPPORT'
    assert CountMetrics(0,0,0,0).ratio('f1') is None


def test_score_boundary_no_rounding():
    t=50/200
    assert classify_prediction(t,50)
    assert not classify_prediction(math.nextafter(t,-math.inf),50)
    assert classify_prediction(math.nextafter(t,math.inf),50)
    with pytest.raises(ValueError):classify_prediction(float('nan'),50)


def test_no_feasible_if_support_missing():
    c=candidate(20);c['close_tp_fn']=(9,0)
    assert select_candidate([c]) is None


def test_ci_4749_4750():
    assert confidence_support(4749)=='CI_INSUFFICIENT_VALID_REPETITIONS'
    assert confidence_support(4750)=='VALID_SUPPORT'
    with pytest.raises(ValueError):confidence_support(4751,4999)


def test_manifest_integrity_no_repair():
    raw=b'version:1';h=hashlib.sha256(raw).hexdigest()
    assert check_dependency_rows([('e1','g1'),('e2','g1')],['e1','e2'],manifest_bytes=raw,expected_sha256=h,version='1')=={'e1':'g1','e2':'g1'}
    for rows,sha in [([('e1','g1'),('e1','g2')],h),([('e1',''),('e2','g1')],h),([('e1','g1')],h),([('e1','g1'),('e2','g1')],'0'*64)]:
        with pytest.raises(ValueError,match='DEPENDENCY_METADATA_INVALID'):
            check_dependency_rows(rows,['e1','e2'],manifest_bytes=raw,expected_sha256=sha,version='1')


def groups():
    return [{'id':f'g{i:02}','encounters':100,'positive':50,'negative':50,'real_negative':30,'synthetic_positive':30,'close_positive':10,'yang_lei':30} for i in range(20)]


def test_group_search_reproducible_and_input_order_independent():
    g=groups();a=assign_groups(g);b=assign_groups(list(reversed(g)))
    assert a['status']=='GROUPED_CV_READY' and a['k']==5 and a['assignment']==b['assignment']
    assert len(a['assignment'])==20


def test_group_search_no_fabricated_singletons():
    g=groups();g[0]['id']=g[1]['id']
    with pytest.raises(ProtocolError):assign_groups(g)


def test_structural_or_bounded_search_are_distinguished():
    g=groups()[:1]
    a=assign_groups(g)
    assert a['status']=='GROUPED_CV_INFEASIBLE' and a['structurally_impossible_k']==[5,4,3,2]
    assert a['assignment'] is None

def test_recall_breaks_exact_f1_and_fpr_tie():
    a=candidate(20,tp=90,fp=10,fn=10,tn=90)
    b=candidate(70,tp=99,fp=21,fn=1,tn=79)
    assert a['overall'].ratio('f1') == b['overall'].ratio('f1')
    assert select_candidate([a,b]) == 70

def test_paired_multiplicity_and_execution_error():
    from src.protocol.calibration_primitives import paired_cluster_indices,ci_coverage
    sample=paired_cluster_indices(['a','a','b'],['b','a','a'])
    assert sample==(2,0,1,0,1)
    assert ci_coverage(['VALID_SUPPORT']*4750+['LOW_SUPPORT']*100+['UNDEFINED']*150)['status']=='VALID_SUPPORT'
    assert ci_coverage(['VALID_SUPPORT']*4749+['UNDEFINED']*251)['status']=='CI_INSUFFICIENT_VALID_REPETITIONS'
    assert ci_coverage(['VALID_SUPPORT']*4999+['EXECUTION_ERROR'])['status']=='EXECUTION_ERROR'

def test_d2_exact_count_boundaries():
    from src.protocol.calibration_primitives import comparison_gates
    cv=CountMetrics(90,10,10,90)
    assert comparison_gates(CountMetrics(89,10,11,90),cv,m5a_real=cv,cv_real=cv)=='COUNT_GATES_PASS'
    assert comparison_gates(CountMetrics(88,10,12,90),cv,m5a_real=cv,cv_real=cv)=='COUNT_GATES_FAIL'
    assert comparison_gates(CountMetrics(1,0,0,0),cv)=='D2_BLOCKED'

def test_ci_two_intervals_and_support_boundary():
    from src.protocol.calibration_primitives import summarize_bootstrap_metric
    a=summarize_bootstrap_metric([('VALID_SUPPORT',1.0)]*4750+[('LOW_SUPPORT',0.0)]*250)
    assert a['all_defined_ci']==[0.0,1.0] and a['support_qualified_ci']==[1.0,1.0]
    b=summarize_bootstrap_metric([('VALID_SUPPORT',1.0)]*4749+[('UNDEFINED',None)]*251)
    assert b['all_defined_ci']==[1.0,1.0] and b['support_qualified_ci'] is None
    with pytest.raises(RuntimeError):summarize_bootstrap_metric([('VALID_SUPPORT',1.0)]*4999+[('EXECUTION_ERROR',None)])

@pytest.mark.parametrize('metric,args,expected',[
    ('precision',{'predicted_positive':19},'LOW_SUPPORT'),('precision',{'predicted_positive':20},'VALID_SUPPORT'),
    ('real_fpr',{'negative':0},'NA'),('real_fpr',{'negative':29},'LOW_SUPPORT'),('real_fpr',{'negative':30},'VALID_SUPPORT'),
    ('average_precision',{'positive':30,'negative':0},'LOW_SUPPORT'),('roc_auc',{'positive':30,'negative':0},'NA'),
    ('f1',{'positive':30,'negative':29},'LOW_SUPPORT'),('source_ade',{'subset':30},'VALID_SUPPORT'),
    ('close_recall',{'subset':10},'VALID_SUPPORT')])
def test_p3_metric_support_boundaries(metric,args,expected):
    from src.protocol.calibration_primitives import metric_support
    assert metric_support(metric,**args)==expected

def test_dependency_lineage_reconstruction_and_mmsi():
    from src.protocol.calibration_primitives import validate_dependency_lineage
    assignments={'a':'DEP_a','b':'DEP_a','c':'DEP_c'}
    assert validate_dependency_lineage(assignments,[('a','123456789'),('b','123456789')],[])
    with pytest.raises(ValueError): validate_dependency_lineage(assignments,[('a','123'),('b','123')],[])
    with pytest.raises(ValueError): validate_dependency_lineage(assignments,[],[])
    with pytest.raises(ValueError): validate_dependency_lineage(assignments,[],[('b','unknown')])

def test_baseline_requires_integrity_and_no_implicit_lineage():
    from src.protocol.calibration_primitives import validate_offline_dependency_baseline
    with pytest.raises(ValueError,match='DEPENDENCY_METADATA_INVALID'):
        validate_offline_dependency_baseline([],[],manifest_bytes=b'x',expected_sha256=hashlib.sha256(b'x').hexdigest(),version='1',mmsi_links=None,parent_links=None)


def test_v1_classification_requires_actual_evidence():
    from src.protocol.calibration_primitives import classify_v1_evidence
    assert classify_v1_evidence({})=='V1_BASELINE_UNAVAILABLE'
    assert classify_v1_evidence({'historical_metrics_available':True})=='V1_HISTORICAL_REFERENCE_ONLY'
    assert classify_v1_evidence({'checkpoint':True,'source_identity':True})=='V1_BASELINE_REVIEW_REQUIRED'
    prediction={'predictions_available':True,'prediction_hash_verified':True,'prediction_split_verified':True,'prediction_mapping_verified':True,'prediction_semantics_verified':True}
    assert classify_v1_evidence(prediction)=='V1_PREDICTIONS_ONLY'
    prediction['prediction_mapping_verified']=False
    assert classify_v1_evidence(prediction)=='V1_BASELINE_REVIEW_REQUIRED'
