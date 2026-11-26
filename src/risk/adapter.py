"""Offline Risk adapter. Runtime inputs and alerts are intentionally unsupported."""
from pathlib import Path
import hashlib
from datetime import timedelta
import numpy as np
import torch
from src.inference.m5a_wrapper import M5aInference, InferenceError
from src.inference.offline_validation import load_validation
from src.models.kinematics import cv_displacement, project_forecast
from src.training.engine import severe_qc
REFERENCE_HASH='8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e'

_REFERENCE_PATH=Path(__file__).resolve().parent/'reference_v4'/'risk_pipeline.py'
if hashlib.sha256(_REFERENCE_PATH.read_bytes()).hexdigest()!=REFERENCE_HASH:
    raise InferenceError('ARTIFACT_INTEGRITY_FAILURE','V4 reference hash mismatch before import')
from src.risk.reference_v4 import risk_pipeline as ref


def verify_reference():
    actual=hashlib.sha256(Path(ref.__file__).read_bytes()).hexdigest()
    if actual!=REFERENCE_HASH:
        raise InferenceError('ARTIFACT_INTEGRITY_FAILURE','V4 reference hash mismatch')


def predict_runtime(*args, **kwargs):
    raise InferenceError('INVALID_INPUT','runtime adapter is not implemented')


def evaluate_validation(dataset_root, artifact_dir, *, device='auto', batch_size=128):
    """Load/check Validation internally; returns diagnostic scores, never decisions.

    This is not production inference. Fixed V4 raw reference has no validation;
    this adapter derives inputs solely from the trusted locked offline loader.
    No threshold fitting, labels, or Test split are consumed for scoring.
    """
    verify_reference()
    s,h,_=load_validation(dataset_root)
    model=M5aInference(artifact_dir,device)
    outputs,_=model.predict_validation(dataset_root,batch_size=batch_size,allow_fallback=False)
    preds=np.empty((len(s.pairs),2,15,2),dtype=np.float64)
    seen=set()
    for result in outputs:
        idx=np.asarray(result['x_rows'])
        values_all=result['forecast_common_en_nm'].cpu().numpy()
        if idx.ndim!=2 or idx.shape[1]!=2 or not np.issubdtype(idx.dtype,np.integer) or values_all.shape!=(len(idx),2,15,2) or values_all.dtype!=np.float64 or not np.isfinite(values_all).all():
            raise InferenceError('FORECAST_UNAVAILABLE','invalid forecast shape, dtype or values')
        if result.get('fallback_used') or result.get('qc_status')!='PASS' or result.get('input_scope')!='LOCKED_OFFLINE_VALIDATION':
            raise InferenceError('FORECAST_UNAVAILABLE','M5a is unavailable, unverified or failed QC')
        encounter_ids=result.get('encounter_ids')
        if not isinstance(encounter_ids,tuple) or len(encounter_ids)!=len(idx):
            raise InferenceError('INVALID_INPUT','missing encounter identity')
        timestamps=result.get('forecast_timestamps')
        if not isinstance(timestamps,tuple) or len(timestamps)!=len(idx):
            raise InferenceError('INVALID_INPUT','missing forecast timestamps')
        for pair,values,encounter_id,times in zip(idx,values_all,encounter_ids,timestamps):
            matches=np.flatnonzero(np.all(s.pairs==pair,axis=1))
            if len(matches)!=1:raise InferenceError('INVALID_INPUT','A/B mapping mismatch')
            i=int(matches[0])
            anchor_time=s.metadata.iloc[i].anchor_timestamp.to_pydatetime()
            if tuple(times)!=tuple(anchor_time+timedelta(minutes=k) for k in range(1,16)):
                raise InferenceError('INVALID_INPUT','forecast timestamp mismatch')
            if str(s.encounters.iloc[i].encounter_id)!=encounter_id:
                raise InferenceError('INVALID_INPUT','encounter identity mismatch')
            if i in seen:raise InferenceError('INVALID_INPUT','duplicate A/B mapping')
            seen.add(i)
            preds[i]=values
    if len(seen)!=len(s.pairs):raise InferenceError('FORECAST_UNAVAILABLE','missing encounters')
    pred_t=torch.from_numpy(preds.reshape(-1,15,2)); anchor_t=torch.from_numpy(np.asarray(s.anchors).reshape(-1,2))
    if severe_qc(pred_t,anchor_t).any():raise InferenceError('FORECAST_UNAVAILABLE','M5a severe QC')
    x=np.asarray(s.X[s.pairs]);anchors=np.asarray(s.anchors)
    values=h[['SOG','COG']].to_numpy(dtype=np.float64).reshape(len(s.X),10,2)[s.pairs]
    pos=x[:,:,:,:2].astype(np.float64)+anchors[:,:,None,:]
    vel=x[:,:,:,2:].astype(np.float64)
    roles,_=ref.infer_roles(pos,vel)
    rule=ref.rule_component(values[:,:,:,1],values[:,:,:,0],roles)
    feat={'last':anchors,'vel':vel,'rule':rule}
    a=torch.from_numpy(anchors.reshape(-1,2));v=torch.from_numpy(vel[:,:,-1,:].reshape(-1,2))
    try:
        cv=project_forecast(a[:,None,:]+cv_displacement(v),a,v)
    except (ValueError,RuntimeError) as exc:
        raise InferenceError('FORECAST_UNAVAILABLE','CV failed') from exc
    if severe_qc(cv,a).any() or not torch.isfinite(cv).all():
        raise InferenceError('FORECAST_UNAVAILABLE','CV failed QC')
    cv=cv.numpy().reshape(len(s.pairs),2,15,2)
    try:
        cv_scores,cv_details=ref.calculate(feat,cv)
        m_scores,m_details=ref.calculate(feat,preds)
    except (AssertionError,ValueError,FloatingPointError) as exc:
        raise InferenceError('FORECAST_UNAVAILABLE','risk calculation failed') from exc
    if not all(np.isfinite(z).all() for z in list(cv_scores.values())+list(m_scores.values())):
        raise InferenceError('FORECAST_UNAVAILABLE','risk score nonfinite')
    return {'scope':'LOCKED_OFFLINE_VALIDATION','encounter_ids':tuple(s.encounters.encounter_id.astype(str)),
            'CV':cv_scores,'M5a':m_scores,'cv_details':cv_details,'m5a_details':m_details,
            'alert_triggered':None,'reference_sha256':REFERENCE_HASH}
