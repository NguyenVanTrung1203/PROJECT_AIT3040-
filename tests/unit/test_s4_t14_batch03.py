from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from src.protocol import clustered_bootstrap as cb
from scripts.run_s4_t14_step03_batch03 import make_fast_choose,group_records,d3_search
from tests.unit.test_s4_t14_bootstrap_runner import synthetic


def test_fast_selector_matches_reference_with_ties_boundaries_and_multiplicity():
    base=synthetic();rng=np.random.default_rng(7);n=len(base.ids)
    # Include exact grid values and floats on either side of boundaries.
    score=np.array([.2,.205,np.nextafter(.205,0),np.nextafter(.205,1),.5,.8,.9],dtype=np.float64)
    values=tuple(score[rng.integers(0,len(score),size=n)])
    d=replace(base,cv_score=values,m5a_score=tuple(reversed(values)));fast=make_fast_choose(d)
    for draws in cb.resample_plan(d.groups,repetitions=24,seed=20261124):
        idx=cb._indices(d.groups,draws)
        for name in ('cv','m5a'):assert fast(d,idx,name)==cb._choose(d,idx,name)


def test_fast_selector_no_feasible_when_support_missing():
    d=synthetic();d=replace(d,close=tuple(False for _ in d.close));idx=np.arange(len(d.ids));assert make_fast_choose(d)(d,idx,'cv') is None


def test_group_construction_ignores_score_columns():
    m=pd.DataFrame({'dependency_group_id':['g','g'],'label':[0,1],'source':['real_ais_kattegat_v3','augmented_real_ais_kattegat_v3'],'close_positive':[False,True],'score':[.1,.9]})
    a=group_records(m);m['score']=[.999,.001];assert group_records(m)==a


def test_structural_proof_largest_group_traps_required_support(tmp_path):
    from src.protocol.group_assignment import MINIMUM
    ids=['a']*20+['b']*20;labels=[1]*20+[0]*20
    m=pd.DataFrame({'dependency_group_id':ids,'label':labels,'source':['augmented_real_ais_kattegat_v3']*20+['real_ais_kattegat_v3']*20,'close_positive':[True]*15+[False]*25})
    result=d3_search(m,tmp_path);assert result['status']=='GROUPED_CV_INFEASIBLE';assert any(x['field']=='close_positive' and x['outside_largest']==0 for x in result['structural_proof'])
    assert (tmp_path/'d3_group_assignment.json').is_file()


def test_official_bootstrap_forbids_custom_repetitions_and_plan():
    with pytest.raises(ValueError):cb.run_bootstrap(synthetic(),cv_threshold_index=87,m5a_threshold_index=84,repetitions=5)
    with pytest.raises(ValueError):cb.run_bootstrap(synthetic(),cv_threshold_index=87,m5a_threshold_index=84,plan=[])


def test_d5_exact_tolerance_boundaries_and_mismatches():
    from scripts.analyze_s4_t14_d5 import gates_ok
    assert gates_ok(5e-5,1e-6,1e-6,5e-5,0,0,True,True,True,True)
    for index in range(4):
        values=[5e-5,1e-6,1e-6,5e-5];values[index]=np.nextafter(values[index],np.inf)
        assert not gates_ok(*values,0,0,True,True,True,True)
    assert not gates_ok(0.,0.,0.,0.,1,0,True,True,True,True)
    assert not gates_ok(0.,0.,0.,0.,0,1,True,True,True,True)
    assert not gates_ok(0.,0.,0.,0.,0,0,True,False,True,True)
