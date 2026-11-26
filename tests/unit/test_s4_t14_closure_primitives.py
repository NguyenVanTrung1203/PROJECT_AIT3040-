from fractions import Fraction
import math
import numpy as np
import pytest
from src.protocol.calibration_primitives import (CountMetrics,select_candidate,comparison_gates,
    ade_gate,close_positive_comparison,paired_metric_delta,threshold_stability_summary,metric_support)


def candidate(k, overall=None, real=None, syn=(90,10), close=(19,1)):
    return {'k':k,'overall':overall or CountMetrics(90,10,10,90),
            'real':real or CountMetrics(0,10,0,90),'synthetic_tp_fn':syn,'close_tp_fn':close,'severe_qc':0}


def test_p3_support_integration_rejects_high_metric_low_support():
    assert select_candidate([candidate(12,close=(9,0))]) is None
    assert select_candidate([candidate(12,close=(10,0))])==12
    assert select_candidate([candidate(12,overall=CountMetrics(29,0,0,30))]) is None


def test_p4_near_equal_f1_fraction_selects_higher_not_rounded_tie():
    a=CountMetrics(999999999,1,1,100)
    b=CountMetrics(1000000000,1,1,100)
    assert round(float(a.ratio('f1')),8)==round(float(b.ratio('f1')),8)
    assert a.ratio('f1')<b.ratio('f1')
    assert select_candidate([candidate(1,a),candidate(2,b)])==2


def test_p4_d2_real_fpr_not_overall_and_exact_boundary():
    cv=CountMetrics(90,10,10,90);m=CountMetrics(90,5,10,95)
    real_cv=CountMetrics(0,10,0,90);real_m=CountMetrics(0,11,0,89)
    assert comparison_gates(m,cv,m5a_real=real_m,cv_real=real_cv)=='COUNT_GATES_PASS'
    assert comparison_gates(m,cv,m5a_real=CountMetrics(0,12,0,88),cv_real=real_cv)=='COUNT_GATES_FAIL'
    assert comparison_gates(m,cv)=='D2_BLOCKED'
    assert ade_gate(1.1,1.)=='D2_PASS'
    assert ade_gate(np.nextafter(1.1,np.inf),1.)=='D2_FAIL'
    assert ade_gate(0.,0.)=='D2_BLOCKED'


def test_p4_close_false_negatives_are_paired_by_identity():
    ids=['a','b','c'];result=close_positive_comparison(ids,['a','b'],['a','c'])
    assert result['cv_fn']=={'c'} and result['m5a_fn']=={'b'}
    assert result['added_m5a_fn']=={'b'} and result['m5a_only_detected']=={'c'} and result['status']=='D2_FAIL'
    with pytest.raises(ValueError):close_positive_comparison(['a','a'],[],[])


def test_p5_pairing_and_undefined_model_do_not_compute_delta():
    assert paired_metric_delta(.1,.2,[0,0,1],[0,0,1])==pytest.approx(.1)
    assert paired_metric_delta(None,.2,[1,2],[1,2]) is None
    with pytest.raises(ValueError,match='paired'):paired_metric_delta(.1,.2,[1,2],[2,1])


def test_p5_feasible_rate_denominator_not_success_count():
    s=threshold_stability_summary([1]*100+[None]*4900)
    assert s['attempts']==5000 and s['feasible_count']==100 and s['feasible_rate']==.02
    assert len(s['indices'])==100


@pytest.mark.parametrize('metric,key,minimum',[
    ('recall','positive',30),('overall_fpr','negative',30),('real_fpr','negative',30),
    ('synthetic_recall','positive',30),('close_recall','subset',10),('precision','predicted_positive',20),
    ('overall_ade','subset',30),('overall_fde','subset',30),('source_ade','subset',30),('source_fde','subset',30)])
def test_p3_below_at_above_support(metric,key,minimum):
    for value,expected in ((minimum-1,'LOW_SUPPORT'),(minimum,'VALID_SUPPORT'),(minimum+1,'VALID_SUPPORT')):
        assert metric_support(metric,**{key:value})==expected


@pytest.mark.parametrize('metric',['f1','roc_auc','average_precision'])
def test_p3_both_classes_support_boundary(metric):
    assert metric_support(metric,positive=29,negative=30,predicted_positive=20)=='LOW_SUPPORT'
    assert metric_support(metric,positive=30,negative=29,predicted_positive=20)=='LOW_SUPPORT'
    assert metric_support(metric,positive=30,negative=30,predicted_positive=20)=='VALID_SUPPORT'
    assert metric_support(metric,positive=31,negative=31,predicted_positive=20)=='VALID_SUPPORT'


def test_p3_undefined_f1_and_na_never_zero():
    assert metric_support('f1',positive=0,negative=30,predicted_positive=0)=='NA'
    assert metric_support('f1',positive=30,negative=30,predicted_positive=1,mathematical_defined=False)=='NA'


def test_p4_all_d1_rational_boundaries_and_d2_recall():
    exact=candidate(100,real=CountMetrics(0,12,0,88),syn=(90,10),close=(19,1))
    assert select_candidate([exact])==100
    over_fpr=candidate(100,real=CountMetrics(0,13,0,87))
    assert select_candidate([over_fpr]) is None
    assert select_candidate([candidate(100,syn=(89,11))]) is None
    assert select_candidate([candidate(100,close=(18,2))]) is None
    cv=CountMetrics(90,10,10,90);m=CountMetrics(89,9,11,91)
    real_cv=CountMetrics(0,10,0,90);real_m=CountMetrics(0,11,0,89)
    assert comparison_gates(m,cv,m5a_real=real_m,cv_real=real_cv)=='COUNT_GATES_PASS'


def test_d2_pass_requires_all_gates_and_close_identity():
    from src.protocol.calibration_primitives import evaluate_d2
    cv=CountMetrics(90,10,10,90); r=CountMetrics(0,10,0,90);ids=[str(i) for i in range(10)]
    args=dict(m5a_d1='D1_PASS',cv_d1='D1_PASS',m5a_counts=cv,cv_counts=cv,m5a_real=r,cv_real=r,
              overall_ade_m5a=1.1,overall_ade_cv=1.,real_ade_m5a=1.1,real_ade_cv=1.,
              overall_encounters=30,real_encounters=30,close_ids=ids,cv_detected=ids,m5a_detected=ids,severe=0)
    assert evaluate_d2(**args)=='D2_PASS'
    assert evaluate_d2(**{**args,'m5a_detected':ids[:-1]})=='D2_FAIL'
    assert evaluate_d2(**{**args,'real_encounters':29})=='D2_BLOCKED'
    assert evaluate_d2(**{**args,'cv_d1':'NO_FEASIBLE_THRESHOLD'})=='D2_CONDITIONAL'


def test_p5_synthetic_cluster_sampling_reproducible_and_paired():
    from src.protocol.calibration_primitives import sample_cluster_ids,paired_cluster_indices
    ids=['a','b','c','d'];sample=sample_cluster_ids(ids)
    assert sample==sample_cluster_ids(ids) and len(sample)==len(ids)
    positions=paired_cluster_indices(['a','a','b','c','d'],sample)
    assert positions==paired_cluster_indices(['a','a','b','c','d'],sample)
    with pytest.raises(ValueError):sample_cluster_ids(['a','a'])


def test_p5_feasible_threshold_is_not_support_qualified():
    from src.protocol.calibration_primitives import ci_coverage
    threshold=threshold_stability_summary([10]*4900+[None]*100)
    coverage=ci_coverage(['VALID_SUPPORT']*4700+['LOW_SUPPORT']*200+['NO_FEASIBLE_THRESHOLD']*100)
    assert threshold['feasible_count']==4900
    assert coverage['valid']==4700 and coverage['status']=='CI_INSUFFICIENT_VALID_REPETITIONS'
