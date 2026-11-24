import os
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from types import SimpleNamespace
from scripts.compare_s3_t10_risk import metric, optimal_threshold, paired_bootstrap, reference, paired_categories, validation_history


def test_metric_and_undefined_single_class():
    y=np.array([0,0,1,1]); s=np.array([.1,.8,.9,.3]);m=metric(y,s,.5)
    assert (m['tp'],m['tn'],m['fp'],m['fn'])==(1,1,1,1)
    assert m['precision']==m['recall']==m['f1']==m['fpr']==.5
    z=metric(np.zeros(4,dtype=int),s,.5)
    assert z['roc_auc'] is None and z['pr_auc_average_precision'] is None and z['f1'] is None and z['recall'] is None
    p=metric(np.ones(4,dtype=int),s,.5)
    assert p['roc_auc'] is None and p['f1'] is None and p['fpr'] is None
    with pytest.raises(ValueError):metric(np.array([0,2]),np.array([.1,.9]),.5)


def test_threshold_selection_exact_grid():
    y=np.array([0,0,1,1]);s=np.array([.05,.1,.7,.8]);real=y==0
    result=optimal_threshold(y,s,real)
    assert result['f1']==1 and result['recall']==1 and result['real_fpr']==0
    assert result['threshold']==.105


def test_paired_bootstrap_cluster_deterministic_and_identity():
    y=np.array([0,1,0,1]);s=np.array([.2,.8,.3,.7]);g=np.array(['a','a','b','b'])
    a=paired_bootstrap(y,s,s,y==0,g,.5,.5,repetitions=50,seed=7)
    assert a==paired_bootstrap(y,s,s,y==0,g,.5,.5,repetitions=50,seed=7)
    assert a['intervals']['auc_delta']['ci_95']==[0.,0.]
    assert a['intervals']['fp_count_delta']['ci_95']==[0.,0.]


def test_paired_correctness_categories():
    y=np.array([0,0,1,1]);cv=np.array([0,1,0,1],dtype=bool);m5a=np.array([0,1,1,0],dtype=bool)
    assert paired_categories(y,cv,m5a).tolist()==['both_correct','both_wrong','m5a_correct_cv_wrong','cv_correct_m5a_wrong']


def test_reject_changed_reference(tmp_path):
    p=tmp_path/'risk.py';p.write_text('print("not trusted")',encoding='utf8')
    with pytest.raises(ValueError,match='hash mismatch'):reference(p)


def test_checkpoint_scaler_artifact_integrity(tmp_path,monkeypatch):
    import json
    import scripts.compare_s3_t10_risk as compare
    files=['best_model.pt','x_scaler.json','residual_scaler.json','validation_predictions.npz','run_config.yaml']
    for name in files:(tmp_path/name).write_bytes(name.encode())
    manifest={'best_epoch':1,'checkpoint_sha256':compare.sha(tmp_path/'best_model.pt'),
              'x_scaler_sha256':compare.sha(tmp_path/'x_scaler.json'),'residual_scaler_sha256':compare.sha(tmp_path/'residual_scaler.json'),
              'validation_predictions_sha256':compare.sha(tmp_path/'validation_predictions.npz'),'model_config_sha256':compare.sha(tmp_path/'run_config.yaml')}
    (tmp_path/'training_manifest.json').write_text(json.dumps(manifest),encoding='utf8')
    checks=''.join(compare.sha(tmp_path/name)+'  '+name+'\n' for name in files+['training_manifest.json'])
    (tmp_path/'checksums.sha256').write_text(checks,encoding='utf8')
    monkeypatch.setattr(compare,'RUN',tmp_path);monkeypatch.setattr(compare,'RUN_SHA',compare.sha(tmp_path/'checksums.sha256'));monkeypatch.setattr(compare,'CHECKPOINT_SHA',manifest['checkpoint_sha256'])
    assert compare.verify_artifacts()['best_epoch']==1
    (tmp_path/'x_scaler.json').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='artifact mismatch'):compare.verify_artifacts()


def test_v4_reference_cpa_near_zero_and_score():
    configured=os.environ.get('V4_REFERENCE_RISK_PATH')
    if not configured or not Path(configured).is_file():pytest.skip('Set V4_REFERENCE_RISK_PATH to the pinned V4 risk reference')
    path=Path(configured)
    rp=reference(path)
    p=np.array([[0.,0.]]); q=np.array([[1.,0.]]); z=np.array([[0.,0.]])
    d,t,raw=rp.cpa(p,z,q,z)
    np.testing.assert_allclose([d[0],t[0],raw[0]],[1.,0.,0.])
    assert rp.score(d,t,.16)[0]==pytest.approx(.10087862273005652)


def test_validation_history_filters_future_and_mapping(monkeypatch):
    anchor=pd.Timestamp('2025-01-01T00:00:00Z');rows=[]
    for vessel in ['A','B']:
        for minute in range(-9,1):
            rows.append({'encounter_id':'e','vessel':vessel,'relative_minute':minute,'is_history':True,'is_future':False,'timestamp_utc':anchor+pd.Timedelta(minutes=minute),'anchor_timestamp':anchor,'SOG':1.,'COG':90.})
    frame=pd.DataFrame(rows); seen={}
    def read(path,columns,filters):
        seen['columns']=columns;seen['filters']=filters;return frame.copy()
    monkeypatch.setattr(pd,'read_parquet',read)
    x=np.zeros((2,10,4),dtype=np.float32);x[:,:,2]=1
    split=SimpleNamespace(X=x,pairs=np.array([[0,1]]),vessels=pd.DataFrame({'encounter_id':['e','e'],'vessel':['A','B'],'X_row':[0,1]}))
    loader=SimpleNamespace(root=Path('.'),config={'splits':{'validation':{'data':'v.parquet'}}})
    assert validation_history(loader,split).shape==(1,2,10,2)
    assert seen['filters']==[('is_history','=',True)] and 'high_risk_label' not in seen['columns']
    frame.loc[0,'is_future']=True
    with pytest.raises(ValueError,match='future leakage'):validation_history(loader,split)


def test_reference_score_ignores_future_and_label():
    configured=os.environ.get('V4_REFERENCE_RISK_PATH')
    if not configured or not Path(configured).is_file():pytest.skip('Set V4_REFERENCE_RISK_PATH to the pinned V4 risk reference')
    path=Path(configured)
    rp=reference(path);feat={'last':np.array([[[0.,0.],[1.,0.]]]),'vel':np.zeros((1,2,10,2)),'rule':np.array([.5])}
    pred=np.zeros((1,2,15,2));pred[:,1,:,0]=1.
    a=rp.calculate(feat,pred)[0]['CC-DRI']
    other={**feat,'label':np.array([1]),'future_truth':np.ones((1,2,15,2))*999}
    b=rp.calculate(other,pred)[0]['CC-DRI']
    np.testing.assert_array_equal(a,b)
