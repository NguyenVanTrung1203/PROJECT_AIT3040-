import numpy as np
import pandas as pd
import pytest
import torch
from scripts.diagnose_s3_t10_epoch1 import circular_delta, compare_metrics, errors, history_features, paired_bootstrap, guarded_split, forbidden_fit
from src.models.kinematics import cv_displacement, project_forecast


def test_circular_wrap():
    np.testing.assert_array_equal(circular_delta(np.array([359.,1.,0.]),np.array([1.,359.,180.])),[2.,-2.,-180.])


def test_history_only_features_and_zero_speed():
    x=np.zeros((2,10,4),np.float32); x[0,:,2]=6; x[0,:,0]=np.arange(-9,1)/10
    features=history_features(x)
    assert features.loc[0,'anchor_speed_kn']==6
    assert features.loc[0,'history_cv_residual_nm']==pytest.approx(0,abs=1e-7)
    assert features.loc[0,'mean_abs_turn_deg_per_min']==0
    assert np.isnan(features.loc[1,'mean_abs_turn_deg_per_min'])
    with pytest.raises(ValueError):history_features(np.zeros((2,25,4)))


def test_cv_reference_horizon_and_projection():
    v=torch.tensor([[6.,12.]],dtype=torch.float64); a=torch.tensor([[3.,-2.]],dtype=torch.float64)
    raw=a[:,None,:]+cv_displacement(v)
    torch.testing.assert_close(raw[0,0],a[0]+v[0]/60)
    torch.testing.assert_close(raw[0,-1],a[0]+v[0]/4)
    torch.testing.assert_close(project_forecast(raw,a,v),raw,atol=1e-12,rtol=1e-12)


def test_ade_fde_and_shape():
    truth=np.zeros((2,15,2)); pred=np.zeros_like(truth);pred[:,:,0]=2;pred[1,-1,0]=4
    ade,fde=errors(pred,truth)
    np.testing.assert_allclose(ade,[2,32/15]); np.testing.assert_allclose(fde,[2,4])
    with pytest.raises(ValueError):errors(pred[:,:14],truth[:,:14])


def test_encounter_aggregation_and_zero_denominator():
    df=pd.DataFrame({'encounter_id':['a','a','b','b'],'cv_ade':[2,4,2,0],'m5a_ade':[1,3,3,1], 'cv_fde':[2,4,2,0], 'm5a_fde':[1,3,3,1], 'cv_severe':[0,0,0,0], 'm5a_severe':[0,0,0,0]})
    df['improvement']=df.cv_ade-df.m5a_ade
    groups=df.groupby('encounter_id').improvement.mean()
    assert groups['a']==1 and groups['b']==-1
    result=compare_metrics(df);assert result['encounters']==2 and result['ade_improvement_nm']==0
    z=df.copy();z['cv_ade']=0;z['cv_fde']=0
    assert compare_metrics(z)['ade_improvement_pct'] is None


def test_bootstrap_reproducible_and_paired():
    values=np.array([-.2,.1,.4,.9]);a=paired_bootstrap(values,seed=123,repetitions=500);b=paired_bootstrap(values,seed=123,repetitions=500)
    assert a==b and a[0]<=a[1]
    with pytest.raises(ValueError):paired_bootstrap([np.nan,1])


def test_forbid_test_split_and_scaler_fit():
    def load(loader, name): return name
    assert guarded_split(load,None,'train')=='train'
    assert guarded_split(load,None,'validation')=='validation'
    with pytest.raises(RuntimeError,match='Test split forbidden'):guarded_split(load,None,'test')
    with pytest.raises(RuntimeError,match='scaler fit forbidden'):forbidden_fit(None,split='train')
