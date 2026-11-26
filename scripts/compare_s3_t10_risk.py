"""Validation-only CV/M5a risk comparison using the hash-verified V4 reference engine."""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import average_precision_score, roc_auc_score
from scipy.stats import spearmanr
from src.data.dataset_loader import DatasetLoader
from src.data.tensor_verification import checksum_dataset, timestamp_checks
from src.models.kinematics import cv_displacement, project_forecast
from src.models.m5a import ResidualGRU
from src.models.scalers import TrainOnlyScaler
from src.training.data import VesselTrainingData
from src.training.engine import severe_qc
from scripts.train_s3_t10 import predictions

RUN=ROOT/'artifacts/checkpoints/s3_t10_20261124_seed20261110_run01'
CHECKPOINT_SHA='e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc'
RUN_SHA='5f0af2eb5a4e418026b775fa412e2fc8bbc803c7438123038a1c519e5a082eb2'
RISK_SHA='8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e'
DATA_SHA='21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
    return h.hexdigest()


def reference(path):
    if sha(path)!=RISK_SHA:raise ValueError('V4 risk engine hash mismatch')
    spec=importlib.util.spec_from_file_location('frozen_v4_risk',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def verify_artifacts():
    if sha(RUN/'checksums.sha256')!=RUN_SHA:raise ValueError('T10 checksum manifest changed')
    for line in (RUN/'checksums.sha256').read_text(encoding='utf8').splitlines():
        h,n=line.split('  ',1)
        if Path(n).name!=n or sha(RUN/n)!=h:raise ValueError('T10 artifact mismatch: '+n)
    m=json.loads((RUN/'training_manifest.json').read_text(encoding='utf8'))
    if m['best_epoch']!=1 or m['checkpoint_sha256']!=CHECKPOINT_SHA or sha(RUN/'best_model.pt')!=CHECKPOINT_SHA:raise ValueError('invalid T10 checkpoint')
    for file,key in [('x_scaler.json','x_scaler_sha256'),('residual_scaler.json','residual_scaler_sha256'),('validation_predictions.npz','validation_predictions_sha256'),('run_config.yaml','model_config_sha256')]:
        if sha(RUN/file)!=m[key]:raise ValueError('run artifact provenance mismatch '+file)
    return m


def metric(y,score,threshold=None):
    y=np.asarray(y);score=np.asarray(score,dtype=float)
    if y.shape!=score.shape or y.ndim!=1 or not np.isin(y,[0,1]).all() or not np.isfinite(score).all():raise ValueError('invalid labels or scores')
    npos=int((y==1).sum());nneg=int((y==0).sum())
    out={'n':len(y),'positive':npos,'negative':nneg,'roc_auc':float(roc_auc_score(y,score)) if npos and nneg else None,
         'pr_auc_average_precision':float(average_precision_score(y,score)) if npos and nneg else None}
    if threshold is not None:
        pred=score>=threshold;tp=int((pred&(y==1)).sum());fn=int((~pred&(y==1)).sum());fp=int((pred&(y==0)).sum());tn=int((~pred&(y==0)).sum())
        prec=tp/(tp+fp) if tp+fp else None;rec=tp/(tp+fn) if tp+fn else None
        f1=2*tp/(2*tp+fp+fn) if npos and nneg and 2*tp+fp+fn else None
        out.update({'threshold':float(threshold),'tp':tp,'tn':tn,'fp':fp,'fn':fn,'precision':prec,'recall':rec,'f1':f1,'fpr':fp/(fp+tn) if fp+tn else None})
    return out


def optimal_threshold(y,score,real,target=.9):
    rows=[]
    for t in np.arange(201,dtype=np.float64)/200:
        m=metric(y,score,t);m['real_fpr']=float((score[real]>=t).mean())
        if m['recall'] is not None and m['recall']>=target:rows.append(m)
    if not rows:return None
    return min(rows,key=lambda v:(-v['f1'],v['real_fpr'],-v['recall'],v['threshold']))


def fixed_fpr_threshold(y,score,real,target):
    rows=[]
    for t in np.arange(201,dtype=np.float64)/200:
        m=metric(y,score,t);m['real_fpr']=float((score[real]>=t).mean())
        if m['real_fpr']<=target:rows.append(m)
    return min(rows,key=lambda v:(-v['recall'],v['real_fpr'],-v['threshold'])) if rows else None


def paired_categories(y, cv_pred, m5a_pred):
    categories=np.select([(cv_pred==y)&(m5a_pred==y),(cv_pred!=y)&(m5a_pred!=y),(cv_pred!=y)&(m5a_pred==y),(cv_pred==y)&(m5a_pred!=y)],['both_correct','both_wrong','m5a_correct_cv_wrong','cv_correct_m5a_wrong'],default='invalid')
    if (categories=='invalid').any():raise ValueError('invalid paired categories')
    return categories


def paired_bootstrap(y,sc,sm,real,groups,tc,tm,repetitions=2000,seed=20261124):
    """Fixed thresholds; resample whole dependency groups, paired across methods."""
    unique=np.unique(groups); members=[np.flatnonzero(groups==g) for g in unique];rng=np.random.default_rng(seed)
    values={k:[] for k in ('auc_delta','pr_auc_delta','f1_delta','recall_delta','real_fpr_delta','fp_count_delta','fn_count_delta','fp_rate_delta','fn_rate_delta')}
    for _ in range(repetitions):
        idx=np.concatenate([members[i] for i in rng.integers(0,len(members),len(members))]); yy=y[idx]; c=sc[idx];m=sm[idx]; rr=real[idx]
        cm=metric(yy,c,tc);mm=metric(yy,m,tm)
        for k,field in [('auc_delta','roc_auc'),('pr_auc_delta','pr_auc_average_precision'),('f1_delta','f1'),('recall_delta','recall')]:
            if cm[field] is not None and mm[field] is not None:values[k].append(mm[field]-cm[field])
        if rr.any():values['real_fpr_delta'].append(float((m[rr]>=tm).mean()-(c[rr]>=tc).mean()))
        values['fp_count_delta'].append(mm['fp']-cm['fp']);values['fn_count_delta'].append(mm['fn']-cm['fn'])
        if cm['fpr'] is not None:values['fp_rate_delta'].append(mm['fpr']-cm['fpr'])
        if cm['recall'] is not None:values['fn_rate_delta'].append(cm['recall']-mm['recall'])
    return {'unit':'locked dependency_group_id (whole connected group)','groups':len(unique),'seed':seed,'replicates':repetitions,'thresholds_fixed_from_full_validation':True,'selection_uncertainty_included':False,
            'intervals':{k:{'valid':len(v),'ci_95':[float(z) for z in np.quantile(v,[.025,.975])] if v else None} for k,v in values.items()}}


def validation_history(loader,split):
    path=loader.root/'validation/data'/loader.config['splits']['validation']['data']
    cols=['encounter_id','vessel','relative_minute','is_history','is_future','timestamp_utc','anchor_timestamp','SOG','COG']
    df=pd.read_parquet(path,columns=cols,filters=[('is_history','=',True)])
    if not df.is_history.all() or df.is_future.any() or not df.relative_minute.between(-9,0).all():raise ValueError('future leakage in history')
    df=df.merge(split.vessels[['encounter_id','vessel','X_row']],on=['encounter_id','vessel'],validate='many_to_one')
    df=df.sort_values(['X_row','relative_minute'],kind='stable')
    if len(df)!=len(split.X)*10 or not np.array_equal(df.X_row,np.repeat(np.arange(len(split.X)),10)) or not np.array_equal(df.relative_minute,np.tile(np.arange(-9,1),len(split.X))):raise ValueError('history alignment mismatch')
    if not (df.timestamp_utc==df.anchor_timestamp+pd.to_timedelta(df.relative_minute,unit='min')).all():raise ValueError('history timestamp mismatch')
    values=df[['SOG','COG']].to_numpy(dtype=np.float64).reshape(-1,10,2)
    if not np.isfinite(values).all() or (values[:,:,0]<0).any() or (values[:,:,1]<0).any() or (values[:,:,1]>=360).any():raise ValueError('invalid observed SOG/COG')
    rad=np.deg2rad(values[:,:,1]); v=np.stack((values[:,:,0]*np.sin(rad),values[:,:,0]*np.cos(rad)),axis=-1)
    if np.max(np.abs(v-split.X[:,:,2:]))>=1e-5:raise ValueError('observed SOG/COG does not match X')
    return values[split.pairs]


def main(dataset_root,risk_path,out):
    out=Path(out).resolve();base=(ROOT/'artifacts/checkpoints').resolve()
    if out.exists() or not out.is_relative_to(base) or not out.name.startswith('s3_post_t10_risk_comparison_'):raise ValueError('output must be a new ignored directory')
    manifest=verify_artifacts(); rp=reference(risk_path)
    ck=torch.load(RUN/'best_model.pt',map_location='cpu',weights_only=True)
    if ck['epoch']!=1 or ck['artifact_kind']!='TRAINING_CANDIDATE' or ck['dataset_manifest_sha256']!=DATA_SHA:raise ValueError('checkpoint metadata mismatch')
    xs=TrainOnlyScaler.load(RUN/'x_scaler.json');rs=TrainOnlyScaler.load(RUN/'residual_scaler.json')
    if xs.kind!='input' or rs.kind!='residual':raise ValueError('invalid scalers')
    def forbidden_fit(*args,**kwargs):raise RuntimeError('scaler fitting forbidden')
    TrainOnlyScaler.fit=forbidden_fit
    original=DatasetLoader.load_split
    def guarded(self,name):
        if name!='validation':raise RuntimeError('only Validation split may be loaded')
        return original(self,name)
    DatasetLoader.load_split=guarded
    loader=DatasetLoader(dataset_root)
    if loader.lock['checksums_manifest_sha256']!=DATA_SHA:raise ValueError('dataset hash mismatch')
    checksum=checksum_dataset(loader.root,loader.lock); s=loader.load_split('validation');timestamp_checks(loader,'validation')
    if len(s.encounters)!=835 or len(s.X)!=1670:raise ValueError('validation coverage mismatch')
    sc_history=validation_history(loader,s); x=np.asarray(s.X)[s.pairs];anchor=np.array(s.anchors,dtype=np.float64,copy=True);vel=x[:,:,:,2:].astype(np.float64);pos=x[:,:,:,:2].astype(np.float64)+anchor[:,:,None,:]
    roles,scene=rp.infer_roles(pos,vel);rule=rp.rule_component(sc_history[:,:,:,1],sc_history[:,:,:,0],roles)
    feat={'last':anchor,'vel':vel,'rule':rule}
    saved=np.load(RUN/'validation_predictions.npz',allow_pickle=False)
    if not np.array_equal(saved['x_row'],np.arange(len(s.X))) or not np.array_equal(saved['encounter_id'],s.vessels.encounter_id.astype(str).to_numpy()) or not np.array_equal(saved['vessel'],s.vessels.vessel.astype(str).to_numpy()):raise ValueError('mapping mismatch')
    m5a=saved['prediction_common_EN_nm'][s.pairs]
    raw=anchor[:,:,None,:]+cv_displacement(torch.from_numpy(vel[:,:,-1,:].reshape(-1,2))).numpy().reshape(835,2,15,2)
    cv=project_forecast(torch.from_numpy(raw.reshape(-1,15,2)),torch.from_numpy(anchor.reshape(-1,2)),torch.from_numpy(vel[:,:,-1,:].reshape(-1,2))).numpy().reshape(835,2,15,2)
    if not torch.cuda.is_available():raise ValueError('original CUDA device unavailable for forecast parity')
    torch.use_deterministic_algorithms(True); model=ResidualGRU();model.load_state_dict(ck['model_state']);model.eval(); val=VesselTrainingData(s)
    gpu=predictions(model.cuda(),val,xs,rs,'cuda'); max_gpu=float(np.max(np.abs(gpu-saved['prediction_common_EN_nm'])))
    if max_gpu!=0:raise ValueError('GPU forecast does not match stored T10 predictions')
    cpu=predictions(model.cpu(),val,xs,rs,'cpu')[s.pairs]; max_cpu=float(np.max(np.abs(cpu-m5a)))
    cscore,cdata=rp.calculate(feat,cv);mscore,mdata=rp.calculate(feat,m5a);pscore,_=rp.calculate(feat,cpu)
    sc=np.asarray(cscore['CC-DRI']);sm=np.asarray(mscore['CC-DRI']);sp=np.asarray(pscore['CC-DRI'])
    for result in (cscore,mscore,pscore):
        expected=.68*result['GRU-P-CPA']+.12*result['Current-CPA']+.20*rule
        np.testing.assert_allclose(result['CC-DRI'],expected,atol=1e-14,rtol=0)
    if not all(np.isfinite(z).all() and (z>=0).all() and (z<=1).all() for z in (sc,sm,sp)):raise ValueError('nonfinite/out-of-range scores')
    # Only after producing scores may labels and source affect evaluation.
    y=np.asarray(s.labels,dtype=int);source=s.encounters.data_source.astype(str).to_numpy();real=source=='real_ais_kattegat_v3';syn=source=='augmented_real_ais_kattegat_v3'
    if not np.array_equal(s.encounters.high_risk_label.to_numpy(),y) or len(y)!=835 or not np.isin(y,[0,1]).all():raise ValueError('label alignment invalid')
    cc=optimal_threshold(y,sc,real); mc=optimal_threshold(y,sm,real)
    if cc is None or mc is None:raise ValueError('recall-constrained threshold unavailable')
    tc,tm=cc['threshold'],mc['threshold'];cp=sc>=tc;mp=sm>=tm
    group=pd.read_parquet(loader.root/'manifests/dependency_groups.parquet',filters=[('package_split','=', 'validation')]); idx=pd.DataFrame({'encounter_id':s.encounters.encounter_id.astype(str)}).merge(group[['encounter_id','dependency_group_id']],on='encounter_id',how='left',validate='one_to_one')
    if idx.dependency_group_id.isna().any():raise ValueError('missing dependency groups')
    groups=idx.dependency_group_id.astype(str).to_numpy();sizes=pd.Series(groups).value_counts()
    bootstrap=paired_bootstrap(y,sc,sm,real,groups,tc,tm)
    op=[]
    for method,z,reference_t in [('CV',sc,.435),('M5a',sm,.420)]:
        for mode,t in [('reference_method',reference_t),('common_0.420',.420),('common_0.435',.435)]:
            q=metric(y,z,t);q.update({'method':method,'mode':mode,'real_ais_fpr':float((z[real]>=t).mean()),'synthetic_recall':float((z[syn]>=t).mean())});op.append(q)
        for target in (.9,.95,.98):
            q=optimal_threshold(y,z,real,target)
            if q:q.update({'method':method,'mode':f'target_recall_{target:.2f}','real_ais_fpr':q['real_fpr'],'synthetic_recall':float((z[syn]>=q['threshold']).mean())});op.append(q)
        for target in (.10,.15):
            q=fixed_fpr_threshold(y,z,real,target)
            if q:q.update({'method':method,'mode':f'target_real_fpr_{target:.2f}','real_ais_fpr':q['real_fpr'],'synthetic_recall':float((z[syn]>=q['threshold']).mean())});op.append(q)
    curves=[]
    for i in range(201):
        t=i/200
        for method,z in [('CV',sc),('M5a',sm)]:
            q=metric(y,z,t);q.update({'method':method,'real_ais_fpr':float((z[real]>=t).mean()),'synthetic_recall':float((z[syn]>=t).mean())});curves.append(q)
    categories=paired_categories(y,cp,mp)
    result=pd.DataFrame({'encounter_id':s.encounters.encounter_id.astype(str),'source':source,'label':y,'cv_score':sc,'m5a_score':sm,'cv_pred':cp,'m5a_pred':mp,'cv_predicted_dcpa_nm':cdata['pred_dmin_nm'],'m5a_predicted_dcpa_nm':mdata['pred_dmin_nm'],'cv_predicted_tcpa_min':cdata['pred_tmin'],'m5a_predicted_tcpa_min':mdata['pred_tmin'],'current_dcpa_nm':cdata['dcpa_nm'],'current_tcpa_min':cdata['tcpa_clipped_min'],'rule_score':rule,'category':categories,'dependency_group_id':groups,'cv_threshold_margin':sc-tc,'m5a_threshold_margin':sm-tm,'cpu_m5a_score':sp})
    counts={name:int((categories==name).sum()) for name in ('both_correct','both_wrong','m5a_correct_cv_wrong','cv_correct_m5a_wrong')}
    source_summary={}
    for source_name in sorted(set(source)):
        mask=source==source_name
        source_summary[source_name]={'cv':metric(y[mask],sc[mask],tc),'m5a':metric(y[mask],sm[mask],tm),'cv_score_mean':float(sc[mask].mean()),'m5a_score_mean':float(sm[mask].mean()),'cv_alert_frequency':float(cp[mask].mean()),'m5a_alert_frequency':float(mp[mask].mean())}
    pair=counts
    cpu_alert_changes=int(((sp>=tm)!=(sm>=tm)).sum());cv_bad=int(severe_qc(torch.from_numpy(cv.reshape(-1,15,2)),torch.from_numpy(anchor.reshape(-1,2))).sum());m_bad=int(severe_qc(torch.from_numpy(m5a.reshape(-1,15,2)),torch.from_numpy(anchor.reshape(-1,2))).sum())
    cpu_bad=int(severe_qc(torch.from_numpy(cpu.reshape(-1,15,2)),torch.from_numpy(anchor.reshape(-1,2))).sum())
    summary={'task_id':'AIT3040_S3_POST_T10_RISK_COMPARISON','dataset_version':loader.lock['dataset_version'],'dataset_checksum':checksum,'checkpoint_sha256':CHECKPOINT_SHA,'t10_manifest_sha256':RUN_SHA,'risk_reference_sha256':RISK_SHA,'risk_reference_kind':'V4 research implementation, not production runtime','diagnostic_thresholds_only':True,'threshold_selection':'each method; grid .005; recall>=.90; max F1; tie lower Real FPR, higher recall, lower threshold','same_validation_selection_bias':True,'cv':cc,'m5a':mc,'cv_pr_auc':metric(y,sc)['pr_auc_average_precision'],'m5a_pr_auc':metric(y,sm)['pr_auc_average_precision'],'synthetic_recall_cv':float(cp[syn].mean()),'synthetic_recall_m5a':float(mp[syn].mean()),'confusion_pair_categories':counts,'cv_severe_vessels':cv_bad,'m5a_severe_vessels':m_bad,'cpu_m5a_severe_vessels':cpu_bad,'gpu_prediction_max_error_nm':max_gpu,'cpu_prediction_max_error_nm':max_cpu,'cpu_max_abs_risk_difference':float(np.max(np.abs(sp-sm))),'cpu_alert_difference_at_m5a_threshold':cpu_alert_changes,'spearman_score_rank':float(spearmanr(sc,sm).statistic),'groups':len(sizes),'largest_group_encounters':int(sizes.iloc[0]),'near_threshold_within_0_005':{'cv':int((np.abs(sc-tc)<=.005).sum()),'m5a':int((np.abs(sm-tm)<=.005).sum())},'source_labels':pd.crosstab(source,y).to_dict(),'test_tensor_loaded':False,'test_bytes_read_for_checksum_only':True,'scaler_refit':False,'model_retrained':False,'runtime_production_verified':False,'bootstrap':bootstrap}
    out.mkdir(parents=True,exist_ok=False)
    result.to_csv(out/'risk_scores_by_encounter.csv',index=False);pd.DataFrame(op).to_csv(out/'operating_points.csv',index=False);pd.DataFrame(curves).to_csv(out/'threshold_sensitivity.csv',index=False)
    pd.DataFrame([{'category':k,'encounters':v} for k,v in pair.items()]).to_csv(out/'paired_alert_changes.csv',index=False)
    (out/'risk_comparison_metrics.json').write_text(json.dumps({'summary':summary,'by_source':source_summary},indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
    (out/'bootstrap_summary.json').write_text(json.dumps(bootstrap,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
    (out/'comparison_manifest.json').write_text(json.dumps({'summary':summary,'script_sha256':sha(__file__),'reference_risk_sha256':sha(risk_path),'checkpoint_sha256':sha(RUN/'best_model.pt'),'dataset_manifest_sha256':DATA_SHA},indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
    files=sorted(q for q in out.iterdir() if q.is_file());(out/'checksums.sha256').write_text(''.join(sha(q)+'  '+q.name+'\n' for q in files),encoding='utf8')
    print(json.dumps(summary,indent=2,ensure_ascii=False,allow_nan=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset-root',required=True);p.add_argument('--reference-risk-path',required=True);p.add_argument('--output-dir',required=True);a=p.parse_args();main(a.dataset_root,a.reference_risk_path,a.output_dir)
