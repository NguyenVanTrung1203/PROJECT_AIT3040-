import json
import numpy as np
import pandas as pd
import pytest
from fractions import Fraction
from src.protocol.calibration_primitives import CountMetrics,select_candidate,metric_support,ade_gate,comparison_gates,close_positive_comparison
from scripts import run_s4_t14_step03_batch02 as b


def fixture():
    m=pd.DataFrame({'encounter_id':['a','b'],'source':['real_ais_kattegat_v3','augmented_real_ais_kattegat_v3'],'label':np.array([0,1],dtype=np.int8),'dependency_group_id':['g1','g2'],'close_positive':[False,True]})
    for k in ['CV_ade_nm','CV_fde_nm','M5a_ade_nm','M5a_fde_nm']:m[k]=np.array([1.,2.],dtype=np.float64)
    risk=pd.concat([pd.DataFrame({'encounter_id':['a','b'],'model_id':[name]*2,'source':m.source,'cc_dri':np.array([.2,.7]),'qc_status':['PASS']*2,'scoring_implementation':['original_and_packaged_exact']*2}) for name in ('CV','M5a')],ignore_index=True)
    return m,risk


def test_alignment_accepts_reordered_score_rows():
    m,r=fixture();a=b.validate_input(m,r.iloc[::-1],strict=False);assert a['CV'].cc_dri.tolist()==[.2,.7]

@pytest.mark.parametrize('mutation',[lambda m,r:r.drop(index=0,inplace=True),lambda m,r:r.loc.__setitem__((0,'encounter_id'),'b'),lambda m,r:r.loc.__setitem__((0,'source'),'yanglei'),lambda m,r:r.loc.__setitem__((0,'qc_status'),'FALLBACK'),lambda m,r:m.loc.__setitem__((0,'label'),1),lambda m,r:r.loc.__setitem__((0,'cc_dri'),float('nan'))])
def test_alignment_rejects_invalid_inputs(mutation):
    m,r=fixture();mutation(m,r)
    with pytest.raises(ValueError):b.validate_input(m,r,strict=False)


def test_grid_all_201_and_infeasible():
    y=np.array([0,1]);src=np.array(['REAL_AIS','SYNTHETIC_AIS']);close=np.array([False,True]);score=np.array([.1,.9]);c,rows,k=b.grid(y,src,close,score)
    assert len(c)==len(rows)==201 and k is None and not any(r['feasible'] for r in rows)
    assert b.infeasibility_diagnostics(rows)['diagnostic_only']


def test_exact_gate_boundary_and_threshold_tie():
    c={'k':3,'overall':CountMetrics(383,10,42,400),'real':CountMetrics(0,35,0,260),'synthetic_tp_fn':(270,30),'close_tp_fn':(57,3),'severe_qc':0}
    row=b.describe_candidate(c);assert row['feasible'];assert select_candidate([dict(c,k=4),c])==3
    assert select_candidate([c,dict(c,k=4)])==3
    assert not b.describe_candidate({**c,'real':CountMetrics(0,36,0,259)})['feasible']


def test_real_fpr_d2_regression_and_exact_boundaries():
    cv=CountMetrics(90,2,10,98);m=CountMetrics(90,2,10,98)
    cr=CountMetrics(0,0,0,100);mr=CountMetrics(0,2,0,98)
    assert comparison_gates(m,cv,m5a_real=mr,cv_real=cr)=='COUNT_GATES_FAIL'
    assert ade_gate(1.1,1.0)=='D2_PASS' and ade_gate(np.nextafter(1.1,2),1.0)=='D2_FAIL'
    assert close_positive_comparison(['a','b'],['a'],['b'])['added_m5a_fn']=={'a'}


def test_d2_infeasible_and_new_miss():
    assert b.d2_eval(None,{'x':1},None,None,None,None,[],[],[])['status']=='D2_CONDITIONAL'
    assert b.d2_eval({'x':1},None,None,None,None,None,[],[],[])['status']=='D2_FAIL'
    c={'overall':CountMetrics(90,5,10,95),'real':CountMetrics(0,5,0,95)};ids=[str(i) for i in range(10)]
    d=b.d2_eval(c,c,1,1,1,1,ids,ids,ids[1:]);assert d['status']=='D2_FAIL' and d['close']['added_m5a_fn']==['0']


def test_low_support_and_undefined_are_distinct():
    assert metric_support('recall',positive=1)=='LOW_SUPPORT'
    assert metric_support('roc_auc',positive=1,negative=0)=='NA'
    result=b.score_metric(np.ones(3,dtype=int),np.array([.1,.2,.3]),'average_precision')
    assert result['value']==1 and result['support']=='LOW_SUPPORT'


def test_reuse_checksum_rejects_tamper(tmp_path):
    p=tmp_path/'x';p.write_text('one');(tmp_path/'checksums.sha256').write_text(b.digest(p)+'  x\n');p.write_text('two')
    with pytest.raises(ValueError):b.verify_output(tmp_path)


def test_validation_only_command_rejects_test(monkeypatch):
    import sys
    monkeypatch.setattr(sys,'argv',['runner','--scope','test','--parent','x','--dataset-root','x','--artifact-dir','x','--original-v4','x','--output-root','x'])
    with pytest.raises(SystemExit):b.main()
