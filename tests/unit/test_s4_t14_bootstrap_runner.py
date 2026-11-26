"""Q3 runner and grouped policy tests use synthetic data only."""
from dataclasses import replace
import numpy as np
import pytest
from src.protocol.clustered_bootstrap import PairedData,resample_plan,run_bootstrap
from src.protocol.group_assignment import assign_groups,partition_supported,FIELDS,MINIMUM


def synthetic():
    ids=[];groups=[];labels=[];sources=[];close=[];scores=[]
    for group in range(8):
        for i in range(20):
            ids.append(f'e{group:02}-{i:02}');groups.append(f'g{group:02}')
            src='REAL_AIS' if i<5 else ('SYNTHETIC_AIS' if i<10 else 'YANG_LEI')
            label=0 if i<5 else (1 if i<15 else 0)
            sources.append(src);labels.append(label);close.append(5<=i<7)
            scores.append(.8 if label else .2)
    n=len(ids);ids=tuple(ids);scores=tuple(scores)
    return PairedData(ids,tuple(groups),tuple(labels),tuple(sources),tuple(close),ids,scores,(1.,)*n,(2.,)*n,(False,)*n,ids,scores,(1.,)*n,(2.,)*n,(False,)*n)


def test_sampler_is_paired_with_replacement_and_reproducible():
    d=synthetic();p=resample_plan(d.groups,repetitions=20);assert p==resample_plan(d.groups,repetitions=20)
    assert all(len(draws)==8 for draws in p)
    assert any(len(set(draws))<8 for draws in p)
    out=run_bootstrap(d,cv_threshold_index=100,m5a_threshold_index=100,repetitions=20,plan=p,fixture_mode=True)
    assert out['attempts']==len(out['details'])==20
    first=out['details'][0];idx=first['sample_indices']
    assert len(idx)==160 and tuple(d.ids[i] for i in idx)==tuple(d.cv_ids[i] for i in idx)==tuple(d.m5a_ids[i] for i in idx)
    assert len(set(idx))<len(idx)
    assert out['metrics']['recall']['all_defined_descriptive_ci']==[0.,0.]
    assert out['metrics']['recall']['support_qualified_ci'] is None
    assert out['metrics']['recall']['status']=='SYNTHETIC_POLICY_ONLY'


def test_stability_reselects_both_and_preserves_feasible_denominator():
    out=run_bootstrap(synthetic(),cv_threshold_index=100,m5a_threshold_index=100,repetitions=3,mode='stability',fixture_mode=True)
    assert out['attempts']==3 and out['stability']['cv_feasible']==3 and out['stability']['m5a_feasible']==3
    assert out['stability']['both_feasible']==3 and out['stability']['d2_comparable']==3
    assert out['stability']['cv_thresholds']==[41]*3 and out['stability']['m5a_thresholds']==[41]*3
    assert out['stability']['d2_counts']=={'D2_PASS':3,'D2_FAIL':0,'D2_CONDITIONAL':0,'D2_BLOCKED':0}


def test_no_retry_on_low_support_or_execution_error():
    d=synthetic();bad=[('missing',)*8]*2
    r=run_bootstrap(d,cv_threshold_index=100,m5a_threshold_index=100,repetitions=2,plan=bad,fixture_mode=True)
    assert len(r['details'])==2 and r['metrics']['f1']['status']=='EXECUTION_ERROR'
    assert r['metrics']['f1']['execution_error_count']==2
    tiny=replace(d,close=tuple(False for _ in d.close))
    r=run_bootstrap(tiny,cv_threshold_index=100,m5a_threshold_index=100,repetitions=2,mode='stability',fixture_mode=True)
    assert len(r['details'])==2 and r['stability']['both_feasible']==0
    assert r['stability']['cv_feasible_rate']==0 and r['metrics']['f1']['no_feasible_count']==2


def test_pair_identity_mismatch_is_rejected():
    d=synthetic()
    with pytest.raises(ValueError,match='identity'):run_bootstrap(replace(d,m5a_ids=tuple(reversed(d.ids))),cv_threshold_index=1,m5a_threshold_index=1,repetitions=1,fixture_mode=True)


def test_fixed_threshold_undefined_metric_not_fake_zero():
    d=synthetic();d=replace(d,close=tuple(False for _ in d.close))
    r=run_bootstrap(d,cv_threshold_index=100,m5a_threshold_index=100,repetitions=2,fixture_mode=True)
    assert r['metrics']['close_recall']['undefined_count']==2
    assert r['metrics']['close_recall']['all_defined_descriptive_ci'] is None


def test_partition_support_both_sides():
    base=dict(zip(FIELDS,MINIMUM));held=dict(base);total={k:2*v for k,v in base.items()}
    assert partition_supported(held,total)
    for key in FIELDS:
        low=dict(held);low[key]-=1;assert not partition_supported(low,total)
        poor=dict(total);poor[key]-=1;assert not partition_supported(held,poor)


def group(i):return {'id':f'g{i:02}','encounters':100,'positive':50,'negative':50,'real_negative':30,'synthetic_positive':30,'close_positive':10,'yang_lei':30}


def test_adaptive_k_structural_vs_heuristic_and_isolation():
    groups=[group(i) for i in range(4)];a=assign_groups(groups);b=assign_groups(list(reversed(groups)))
    assert a['status']=='GROUPED_CV_READY' and a['k']==4 and a['assignment']==b['assignment']
    assert a['structurally_impossible_k']==[5]
    assert len(a['assignment'])==len(groups) and set(a['assignment'].values())==set(range(4))
    giant=group(0);giant.update({'encounters':400,'positive':200,'negative':200,'real_negative':120,'synthetic_positive':120,'close_positive':40,'yang_lei':120})
    small=group(1);small['close_positive']=0
    limited=assign_groups([giant,small],attempts=1)
    assert limited['status']=='GROUPED_CV_BLOCKED' and not limited['search_is_exhaustive']
    impossible=assign_groups([group(1)])
    assert impossible['status']=='GROUPED_CV_INFEASIBLE' and impossible['structurally_impossible_k']==[5,4,3,2]


def test_one_model_f1_undefined_never_generates_delta():
    d=synthetic();n=len(d.ids)
    d=replace(d,labels=(0,)*n,source=('REAL_AIS',)*n,close=(False,)*n,
              cv_score=(.1,)*n,m5a_score=(.9,)*n)
    result=run_bootstrap(d,cv_threshold_index=100,m5a_threshold_index=100,repetitions=2,fixture_mode=True)
    assert result['metrics']['f1']['undefined_count']==2
    assert result['metrics']['f1']['all_defined_descriptive_ci'] is None
    assert result['details'][0]['cv_metrics']['f1']==('UNDEFINED',None)
    assert result['details'][0]['m5a_metrics']['f1']==('LOW_SUPPORT',0.0)


def test_twenty_attempts_with_three_low_support_are_not_replaced():
    d=synthetic();close=list(d.close)
    close[6]=False
    d=replace(d,close=tuple(close))
    plan=[('g01',)*8]*17+[('g00',)*8]*3
    out=run_bootstrap(d,cv_threshold_index=100,m5a_threshold_index=100,repetitions=20,plan=plan,fixture_mode=True)
    assert out['attempts']==len(out['details'])==20
    assert out['metrics']['close_recall']['low_support_count']==3
    assert out['metrics']['close_recall']['valid_support_count']==17
    assert all(r['status']=='OK' for r in out['details'])


def test_nonstandard_attempts_require_fixture_mode():
    with pytest.raises(ValueError,match='synthetic fixture mode'):
        run_bootstrap(synthetic(),cv_threshold_index=100,m5a_threshold_index=100,repetitions=2)


def test_stability_one_model_infeasible_without_fake_delta():
    d=synthetic();d=replace(d,m5a_severe=(True,)*len(d.ids))
    r=run_bootstrap(d,cv_threshold_index=100,m5a_threshold_index=100,repetitions=2,mode='stability',fixture_mode=True)
    assert r['stability']['cv_feasible']==2 and r['stability']['m5a_feasible']==0
    assert r['stability']['both_feasible']==0 and r['stability']['d2_counts']=={'D2_PASS':0,'D2_FAIL':0,'D2_CONDITIONAL':0,'D2_BLOCKED':2}
    assert r['metrics']['f1']['no_feasible_count']==2


def test_score_dtype_is_not_silently_changed():
    d=synthetic()
    with pytest.raises(ValueError,match='float64'):
        run_bootstrap(replace(d,cv_score=tuple(np.float32(x) for x in d.cv_score)),cv_threshold_index=100,m5a_threshold_index=100,repetitions=1,fixture_mode=True)


def test_ci_qualification_per_metric_and_error_is_not_hidden():
    from src.protocol.clustered_bootstrap import _aggregate
    valid=[('VALID_SUPPORT',0.1)]*4750
    assert _aggregate(valid+[('UNDEFINED',None)]*250,5000)['status']=='VALID_SUPPORT'
    assert _aggregate(valid[:-1]+[('UNDEFINED',None)]*251,5000)['status']=='CI_INSUFFICIENT_VALID_REPETITIONS'
    bad=_aggregate(valid+[('UNDEFINED',None)]*249+[('EXECUTION_ERROR',None)],5000)
    assert bad['status']=='EXECUTION_ERROR' and bad['execution_error_count']==1 and bad['support_qualified_ci'] is None


def test_numpy_scalar_labels_and_flags_preserve_pairing():
    d=synthetic()
    d=replace(d,labels=tuple(np.int64(x) for x in d.labels),close=tuple(np.bool_(x) for x in d.close),
              cv_severe=tuple(np.bool_(x) for x in d.cv_severe),m5a_severe=tuple(np.bool_(x) for x in d.m5a_severe))
    result=run_bootstrap(d,cv_threshold_index=100,m5a_threshold_index=100,repetitions=1,fixture_mode=True)
    assert result['attempts']==1 and result['details'][0]['status']=='OK'


def test_official_scope_cannot_override_seed_or_plan():
    with pytest.raises(ValueError,match='synthetic fixture mode'):
        run_bootstrap(synthetic(),cv_threshold_index=100,m5a_threshold_index=100,seed=7)
    with pytest.raises(ValueError,match='synthetic fixture mode'):
        run_bootstrap(synthetic(),cv_threshold_index=100,m5a_threshold_index=100,plan=[])
