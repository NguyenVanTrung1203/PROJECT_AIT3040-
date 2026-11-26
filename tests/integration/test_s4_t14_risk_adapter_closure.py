"""Controlled synthetic spies; no fixture is accepted as production provenance."""
from types import SimpleNamespace
from datetime import datetime,timezone,timedelta
import numpy as np
import pandas as pd
import pytest
import torch
from src.risk import adapter

@pytest.fixture
def synthetic(monkeypatch):
    x=np.zeros((2,10,4),dtype=np.float32); anchors=np.array([[[0.,0.],[1.,0.]]],dtype=np.float64)
    anchor_time=datetime(2026,1,1,tzinfo=timezone.utc)
    split=SimpleNamespace(pairs=np.array([[0,1]]),X=x,anchors=anchors,metadata=pd.DataFrame({'anchor_timestamp':[pd.Timestamp(anchor_time)]}),
                          encounters=pd.DataFrame({'encounter_id':['fixture-e']}))
    h=pd.DataFrame({'SOG':np.zeros(20),'COG':np.zeros(20)})
    pred=np.repeat(anchors[:,:,None,:],15,axis=2)
    result={'x_rows':np.array([[0,1]]),'forecast_common_en_nm':torch.from_numpy(pred),
            'fallback_used':False,'qc_status':'PASS','input_scope':'LOCKED_OFFLINE_VALIDATION','encounter_ids':('fixture-e',),'forecast_timestamps':(tuple(anchor_time+timedelta(minutes=i) for i in range(1,16)),)}
    calls=[]
    def fake_loader(root):calls.append(('loader',root));return split,h,{}
    class FakeModel:
        def __init__(self,artifact,device):calls.append(('model_init',device))
        def predict_validation(self,root,*,batch_size,allow_fallback):
            calls.append(('predict',root,allow_fallback));return [result],{}
    monkeypatch.setattr(adapter,'load_validation',fake_loader);monkeypatch.setattr(adapter,'M5aInference',FakeModel)
    return split,result,calls


def test_adapter_scoring_uses_trusted_loader_same_engine_for_both(synthetic,monkeypatch):
    split,result,calls=synthetic
    count=[];original=adapter.ref.calculate
    def spy(feat,pred):count.append(pred.copy());return original(feat,pred)
    monkeypatch.setattr(adapter.ref,'calculate',spy)
    out=adapter.evaluate_validation('fixture-dataset','fixture-artifact',device='cpu')
    assert calls==[('loader','fixture-dataset'),('model_init','cpu'),('predict','fixture-dataset',False)]
    assert len(count)==2 and out['scope']=='LOCKED_OFFLINE_VALIDATION' and out['alert_triggered'] is None
    assert out['encounter_ids']==('fixture-e',)


@pytest.mark.parametrize('mutation',['missing','duplicate','wrong_mapping','wrong_identity','bad_timestamp','bad_index_dtype','short_forecast','float32','nan','inf','severe','fallback','qc_fail','unverified'])
def test_adapter_rejects_invalid_forecast_before_scoring(synthetic,monkeypatch,mutation):
    _,result,_=synthetic
    if mutation=='missing':result['x_rows']=np.empty((0,2),dtype=int);result['forecast_common_en_nm']=torch.empty((0,2,15,2),dtype=torch.float64)
    elif mutation=='duplicate':result['x_rows']=np.array([[0,1],[0,1]]);result['forecast_common_en_nm']=result['forecast_common_en_nm'].repeat(2,1,1,1);result['encounter_ids']=('fixture-e','fixture-e');result['forecast_timestamps']=result['forecast_timestamps']*2
    elif mutation=='bad_timestamp':result['forecast_timestamps']=(result['forecast_timestamps'][0][:-1],)
    elif mutation=='bad_index_dtype':result['x_rows']=result['x_rows'].astype(float)
    elif mutation=='wrong_identity':result['encounter_ids']=('other',)
    elif mutation=='wrong_mapping':result['x_rows']=np.array([[1,0]])
    elif mutation=='short_forecast':result['forecast_common_en_nm']=result['forecast_common_en_nm'][:,:,:14]
    elif mutation=='float32':result['forecast_common_en_nm']=result['forecast_common_en_nm'].float()
    elif mutation=='nan':result['forecast_common_en_nm'][0,0,0,0]=float('nan')
    elif mutation=='inf':result['forecast_common_en_nm'][0,0,0,0]=float('inf')
    elif mutation=='severe':result['forecast_common_en_nm'][0,0,:,0]=torch.arange(15,dtype=torch.float64)*10
    elif mutation=='fallback':result['fallback_used']=True
    elif mutation=='qc_fail':result['qc_status']='FAIL'
    elif mutation=='unverified':result['input_scope']='TEST_ONLY_UNVERIFIED'
    monkeypatch.setattr(adapter.ref,'calculate',lambda *a,**k:pytest.fail('must not score invalid forecasts'))
    with pytest.raises(adapter.InferenceError):adapter.evaluate_validation('fixture','fixture',device='cpu')


def test_nonfinite_score_fails_closed(synthetic,monkeypatch):
    def invalid(*a):return {'CC-DRI':np.array([np.nan])},{}
    monkeypatch.setattr(adapter.ref,'calculate',invalid)
    with pytest.raises(adapter.InferenceError,match='nonfinite'):adapter.evaluate_validation('fixture','fixture',device='cpu')


def test_test_directory_cannot_be_used_as_dataset(monkeypatch,tmp_path):
    def forbidden(*a,**k):pytest.fail('model must not be constructed')
    monkeypatch.setattr(adapter,'M5aInference',forbidden)
    test=tmp_path/'test';test.mkdir()
    with pytest.raises(adapter.InferenceError):adapter.evaluate_validation(test,'not-used',device='cpu')


def test_loader_failure_does_not_invoke_model_or_fallback(monkeypatch):
    def fail(*a):raise adapter.InferenceError('INVALID_INPUT','bad source or timestamp')
    monkeypatch.setattr(adapter,'load_validation',fail)
    monkeypatch.setattr(adapter,'M5aInference',lambda *a,**k:pytest.fail('model must not be loaded'))
    with pytest.raises(adapter.InferenceError) as e:adapter.evaluate_validation('fixture','fixture')
    assert e.value.code=='INVALID_INPUT'


def test_portable_scoring_from_external_cwd_without_research_path(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    repo=Path(__file__).resolve().parents[2]
    code="import sys;sys.path.insert(0,sys.argv[1]);from src.risk.reference_v4 import risk_pipeline as r;import numpy as n;d,t,raw=r.cpa(n.array([[0.,0.]]),n.zeros((1,2)),n.array([[1.,0.]]),n.zeros((1,2)));assert d[0]==1. and t[0]==0.;assert n.isfinite(r.score(d,t)).all();print('SCORING_OK')"
    env=os.environ.copy();env.pop('V4_REFERENCE_RISK_PATH',None);env.pop('PYTHONPATH',None);env['PYTHONDONTWRITEBYTECODE']='1'
    p=subprocess.run([sys.executable,'-I','-c',code,str(repo)],cwd=tmp_path,env=env,text=True,capture_output=True,timeout=60)
    assert p.returncode==0,p.stderr
    assert 'SCORING_OK' in p.stdout


def test_cv_failure_and_cv_qc_do_not_create_scores(synthetic,monkeypatch):
    monkeypatch.setattr(adapter.ref,'calculate',lambda *a,**k:pytest.fail('must not score invalid CV'))
    def fail(*a,**kw):raise ValueError('synthetic CV failure')
    monkeypatch.setattr(adapter,'project_forecast',fail)
    with pytest.raises(adapter.InferenceError) as exc:adapter.evaluate_validation('fixture','fixture')
    assert exc.value.code=='FORECAST_UNAVAILABLE'


def test_nonfinite_component_fails_closed(synthetic,monkeypatch):
    def invalid(*a):return {'CC-DRI':np.array([.5]),'Current-CPA':np.array([np.inf])},{}
    monkeypatch.setattr(adapter.ref,'calculate',invalid)
    with pytest.raises(adapter.InferenceError,match='nonfinite'):adapter.evaluate_validation('fixture','fixture')


def test_model_technical_failure_is_not_silently_relabelled(synthetic,monkeypatch):
    class Broken:
        def __init__(self,*a,**k):pass
        def predict_validation(self,*a,**kw):raise adapter.InferenceError('MODEL_TECHNICAL_FAILURE','fixture failure')
    monkeypatch.setattr(adapter,'M5aInference',Broken)
    monkeypatch.setattr(adapter.ref,'calculate',lambda *a,**k:pytest.fail('must not score after M5a failure'))
    with pytest.raises(adapter.InferenceError) as exc:adapter.evaluate_validation('fixture','fixture')
    assert exc.value.code=='MODEL_TECHNICAL_FAILURE'


def test_severe_cv_qc_fails_before_scoring(synthetic,monkeypatch):
    calls=[]
    def qc(pred,anchor):
        calls.append(1)
        return torch.tensor([False,False]) if len(calls)==1 else torch.tensor([True,False])
    monkeypatch.setattr(adapter,'severe_qc',qc)
    monkeypatch.setattr(adapter.ref,'calculate',lambda *a,**k:pytest.fail('severe CV must not score'))
    with pytest.raises(adapter.InferenceError) as e:adapter.evaluate_validation('fixture','fixture')
    assert e.value.code=='FORECAST_UNAVAILABLE' and len(calls)==2


def test_artifact_failure_does_not_score_or_fallback(synthetic,monkeypatch):
    def fail(*a,**kw):raise adapter.InferenceError('ARTIFACT_INTEGRITY_FAILURE','fixture')
    monkeypatch.setattr(adapter,'M5aInference',fail)
    monkeypatch.setattr(adapter.ref,'calculate',lambda *a,**k:pytest.fail('artifact failure must not score'))
    with pytest.raises(adapter.InferenceError) as e:adapter.evaluate_validation('fixture','fixture')
    assert e.value.code=='ARTIFACT_INTEGRITY_FAILURE'
