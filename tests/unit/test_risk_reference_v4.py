import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
import yaml
from src.risk import adapter
from src.risk.reference_v4 import risk_pipeline as packaged

EXPECTED='8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e'

@pytest.fixture(scope='module')
def original():
    path=os.environ.get('V4_REFERENCE_RISK_PATH')
    if not path or not Path(path).is_file(): pytest.skip('set V4_REFERENCE_RISK_PATH to verify original parity')
    import hashlib
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==EXPECTED
    spec=importlib.util.spec_from_file_location('original_v4_for_fixture',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def test_manifest_and_hash():
    m=yaml.safe_load(Path('configs/risk_reference_manifest.yaml').read_text(encoding='utf-8-sig'))
    adapter.verify_reference()
    assert m['original_sha256']==m['packaged_sha256']==EXPECTED
    assert m['redistribution_permission']=='confirmed_by_Trung' and not m['algorithm_modified'] and not m['production_approved']


def test_exact_components_and_score_parity(original):
    pos=np.zeros((3,2,10,2),dtype=np.float64);pos[:,1,:,0]=np.array([1,2,3])[:,None];vel=np.zeros_like(pos);vel[:,0,:,0]=2
    roles0,scene0=original.infer_roles(pos,vel);roles1,scene1=packaged.infer_roles(pos,vel)
    np.testing.assert_array_equal(roles0,roles1);np.testing.assert_array_equal(scene0,scene1)
    cog=np.zeros((3,2,10));sog=np.ones_like(cog)
    rule0=original.rule_component(cog,sog,roles0);rule1=packaged.rule_component(cog,sog,roles1)
    np.testing.assert_array_equal(rule0,rule1)
    feat={'last':pos[:,:,-1], 'vel':vel,'rule':rule0}
    pred=np.repeat(feat['last'][:,:,None,:],15,axis=2)
    score0,details0=original.calculate(feat,pred);score1,details1=packaged.calculate(feat,pred)
    for k in score0:np.testing.assert_array_equal(score0[k],score1[k])
    for k in details0:np.testing.assert_array_equal(details0[k],details1[k])
    for threshold in (.0,.42,.5,1.):
        np.testing.assert_array_equal(score0['CC-DRI']>=threshold,score1['CC-DRI']>=threshold)


def test_portable_clean_subprocess():
    repo=Path(__file__).resolve().parents[2]
    code='from src.risk import adapter; adapter.verify_reference(); print("PORTABLE_OK")'
    env=os.environ.copy();env['PYTHONPATH']=str(repo);env.pop('V4_REFERENCE_RISK_PATH',None);env['PYTHONDONTWRITEBYTECODE']='1'
    result=subprocess.run([sys.executable,'-c',code],cwd=repo,env=env,text=True,capture_output=True,timeout=40)
    assert result.returncode==0, result.stderr
    assert 'PORTABLE_OK' in result.stdout


def test_runtime_rejects_input():
    with pytest.raises(adapter.InferenceError) as e:adapter.predict_runtime({'verified':True})
    assert e.value.code=='INVALID_INPUT'


def test_hash_mismatch_fail_closed(monkeypatch,tmp_path):
    altered=tmp_path/'risk_pipeline.py';altered.write_text('not trusted',encoding='utf-8')
    monkeypatch.setattr(adapter.ref,'__file__',str(altered))
    with pytest.raises(adapter.InferenceError) as e:adapter.verify_reference()
    assert e.value.code=='ARTIFACT_INTEGRITY_FAILURE'

def test_near_zero_cpa_and_score_boundary_parity(original):
    a=np.array([[0.,0.],[0.,0.]]);b=np.array([[1.,0.],[2.,0.]])
    va=np.zeros((2,2));vb=np.array([[0.,0.],[-1.,0.]])
    for x,y in zip(original.cpa(a,va,b,vb),packaged.cpa(a,va,b,vb)):
        np.testing.assert_array_equal(x,y)
    values=np.array([.42,np.nextafter(.42,-np.inf),np.nextafter(.42,np.inf)])
    assert (values>=.42).tolist()==[True,False,True]


def test_malformed_input_errors_match(original):
    feat={'last':np.zeros((1,2,2)), 'vel':np.zeros((1,2,10,2)), 'rule':np.array([.5])}
    malformed=np.zeros((1,2,0,2))
    types=[]
    for engine in (original,packaged):
        try:engine.calculate(feat,malformed)
        except Exception as exc:types.append(type(exc))
    assert len(types)==2 and types[0] is types[1]


def test_invalid_or_nonfinite_runtime_path_rejected():
    with pytest.raises(adapter.InferenceError):adapter.predict_runtime({'input':np.array([float('nan')])})
    with pytest.raises(adapter.InferenceError):adapter.evaluate_validation('nonexistent_dataset','nonexistent_artifact')
