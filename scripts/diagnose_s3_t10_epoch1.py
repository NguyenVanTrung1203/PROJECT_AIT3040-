"""Read-only Train/Validation research audit; never trains or fits scalers."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
import torch
from scipy.stats import ks_2samp, wasserstein_distance, spearmanr
from src.data.dataset_loader import DatasetLoader
from src.models.kinematics import cv_displacement, project_forecast
from src.models.m5a import ResidualGRU
from src.models.scalers import TrainOnlyScaler
from src.training.data import VesselTrainingData, load_verified_data
from src.training.engine import severe_qc
from scripts.train_s3_t10 import predictions

SOURCE = ROOT/'artifacts/checkpoints/s3_t10_20261124_seed20261110_run01'
BASE_SHA = 'f3096fd2d44471ce7bbf455932cd7c3d5634f692'
CHECKPOINT_SHA = 'e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc'
MANIFEST_SHA = '5f0af2eb5a4e418026b775fa412e2fc8bbc803c7438123038a1c519e5a082eb2'
LABELS = {'yanglei':'Yang Lei', 'real_ais_kattegat_v3':'Real AIS', 'augmented_real_ais_kattegat_v3':'Synthetic AIS'}


def guarded_split(original, loader, name):
    if name not in ('train','validation'):raise RuntimeError('Test split forbidden')
    return original(loader,name)


def forbidden_fit(*args,**kwargs):
    raise RuntimeError('scaler fit forbidden in diagnostic')


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''): h.update(data)
    return h.hexdigest()


def verify_t10():
    manifest=SOURCE/'checksums.sha256'
    if digest(manifest)!=MANIFEST_SHA: raise ValueError('T10 checksum manifest changed')
    lines=manifest.read_text(encoding='utf8').splitlines()
    for line in lines:
        expected,name=line.split('  ',1)
        if Path(name).name!=name or digest(SOURCE/name)!=expected: raise ValueError('T10 artifact mismatch: '+name)
    m=json.loads((SOURCE/'training_manifest.json').read_text(encoding='utf8'))
    if m['best_epoch']!=1 or m['git_base_commit']!=BASE_SHA or m['checkpoint_sha256']!=CHECKPOINT_SHA or digest(SOURCE/'best_model.pt')!=CHECKPOINT_SHA:
        raise ValueError('checkpoint provenance mismatch')
    return m,len(lines)


def circular_delta(a,b):
    return (b-a+180)%360-180


def history_features(x):
    """Per-vessel history-only features; EN nm, EN velocity knots, 1 min grid."""
    if x.ndim!=3 or x.shape[1:]!=(10,4) or not np.isfinite(x).all(): raise ValueError('history shape/values')
    v=x[:,:,2:].astype(np.float64); pos=x[:,:,:2].astype(np.float64)
    speed=np.linalg.norm(v,axis=-1); delta=np.diff(speed,axis=1)
    heading=np.degrees(np.arctan2(v[:,:,0],v[:,:,1]))
    turns=np.abs(circular_delta(heading[:,:-1],heading[:,1:]))
    valid=(speed[:,:-1]>=.5)&(speed[:,1:]>=.5)
    sum_turn=np.where(valid,turns,0).sum(axis=1); n=valid.sum(axis=1)
    mean_turn=np.divide(sum_turn,n,out=np.full(len(x),np.nan),where=n>0)
    offsets=np.arange(-9,1,dtype=np.float64)[None,:,None]/60
    cv_error=np.linalg.norm(pos-v[:,-1:, :]*offsets,axis=-1).mean(axis=1)
    return pd.DataFrame({'anchor_speed_kn':speed[:,-1], 'mean_speed_kn':speed.mean(axis=1),
        'anchor_east_velocity_kn':v[:,-1,0], 'anchor_north_velocity_kn':v[:,-1,1],
        'speed_std_kn':speed.std(axis=1), 'speed_change_kn':speed[:,-1]-speed[:,0],
        'mean_abs_speed_change_kn_per_min':np.abs(delta).mean(axis=1),
        'mean_vector_accel_kn_per_min':np.linalg.norm(np.diff(v,axis=1),axis=-1).mean(axis=1),
        'mean_abs_turn_deg_per_min':mean_turn, 'history_cv_residual_nm':cv_error,
        'history_displacement_nm':np.linalg.norm(pos[:,-1]-pos[:,0],axis=-1)})


def errors(pred,truth):
    if pred.shape!=truth.shape or pred.ndim!=3 or pred.shape[1:]!=(15,2):raise ValueError('forecast shape')
    d=np.linalg.norm(pred-truth,axis=-1)
    if not np.isfinite(d).all():raise ValueError('nonfinite forecast error')
    return d.mean(axis=1),d[:,-1]


def paired_bootstrap(values,seed=20261124,repetitions=5000):
    x=np.asarray(values,dtype=np.float64)
    if x.ndim!=1 or len(x)<2 or not np.isfinite(x).all():raise ValueError('invalid bootstrap sample')
    rng=np.random.default_rng(seed); means=np.empty(repetitions)
    for i in range(repetitions): means[i]=x[rng.integers(0,len(x),len(x))].mean()
    return np.quantile(means,[.025,.975]).tolist()


def compare_metrics(df):
    ca,ma,cf,mf=(df[k].mean() for k in ('cv_ade','m5a_ade','cv_fde','m5a_fde'))
    return {'vessels':len(df),'encounters':df.encounter_id.nunique(),'cv_ade_nm':ca,'m5a_ade_nm':ma,
            'ade_improvement_nm':ca-ma,'ade_improvement_pct':100*(ca-ma)/ca if ca else None,
            'cv_fde_nm':cf,'m5a_fde_nm':mf,'fde_improvement_nm':cf-mf,
            'fde_improvement_pct':100*(cf-mf)/cf if cf else None,
            'vessel_win_rate':float((df.improvement>0).mean()),'cv_severe_vessels':int(df.cv_severe.sum()),
            'm5a_severe_vessels':int(df.m5a_severe.sum())}


def distribution(train,real,val_yang):
    rows=[]
    for name in train.columns:
        a=train[name].dropna().to_numpy(); b=real[name].dropna().to_numpy(); c=val_yang[name].dropna().to_numpy()
        if len(a)<2 or len(b)<2:continue
        pooled=np.sqrt((np.var(a,ddof=1)+np.var(b,ddof=1))/2); smd=(b.mean()-a.mean())/pooled if pooled>0 else None
        row={'feature':name,'train_n':len(a),'real_n':len(b),'train_missing':len(train)-len(a),'real_missing':len(real)-len(b),
             'smd_real_minus_train':smd,'ks_statistic':ks_2samp(a,b).statistic,'wasserstein':wasserstein_distance(a,b),'yang_val_mean':float(c.mean()) if len(c) else None,
             'real_fraction_below_train_p25':float(np.mean(b<np.quantile(a,.25))),
             'real_fraction_train_p25_to_p75':float(np.mean((b>=np.quantile(a,.25))&(b<=np.quantile(a,.75)))),
             'real_fraction_above_train_p75':float(np.mean(b>np.quantile(a,.75)))}
        for prefix,values in [('train',a),('real',b)]:
            q=np.quantile(values,[0,.1,.25,.5,.75,.9,1]);
            row.update({prefix+'_mean':values.mean(),prefix+'_std':values.std(ddof=1),**{prefix+'_'+k:float(v) for k,v in zip(('min','p10','p25','median','p75','p90','max'),q)}})
        rows.append(row)
    return pd.DataFrame(rows).sort_values('smd_real_minus_train',key=lambda v:v.abs(),ascending=False)


def run(dataset_root,out):
    out=Path(out).resolve(); allowed=(ROOT/'artifacts/checkpoints').resolve()
    if out.exists() or not out.is_relative_to(allowed) or not out.name.startswith('s3_t10_epoch1_diagnostic_'):raise ValueError('output must be a new diagnostic-only ignored directory')
    m,count=verify_t10()
    ck=torch.load(SOURCE/'best_model.pt',map_location='cpu',weights_only=True)
    if ck['epoch']!=1 or ck['artifact_kind']!='TRAINING_CANDIDATE':raise ValueError('invalid checkpoint')
    xs=TrainOnlyScaler.load(SOURCE/'x_scaler.json');rs=TrainOnlyScaler.load(SOURCE/'residual_scaler.json')
    if xs.kind!='input' or rs.kind!='residual':raise ValueError('invalid scalers')
    TrainOnlyScaler.fit=forbidden_fit
    original_load=DatasetLoader.load_split
    def guarded(self,name):
        return guarded_split(original_load,self,name)
    DatasetLoader.load_split=guarded
    loader,splits,checksum=load_verified_data(dataset_root)
    val=VesselTrainingData(splits['validation']); train=splits['train']; s=splits['validation']
    stored=np.load(SOURCE/'validation_predictions.npz',allow_pickle=False)
    if not np.array_equal(stored['x_row'],np.arange(len(val))) or not np.array_equal(stored['encounter_id'],s.vessels.encounter_id.astype(str).to_numpy()) or not np.array_equal(stored['vessel'],s.vessels.vessel.astype(str).to_numpy()):raise ValueError('A/B mapping mismatch')
    if not torch.cuda.is_available(): raise RuntimeError('original CUDA device required to verify epoch-1 prediction')
    torch.use_deterministic_algorithms(True);model=ResidualGRU().cuda();model.load_state_dict(ck['model_state']);model.eval()
    m5a=predictions(model,val,xs,rs,'cuda'); saved=stored['prediction_common_EN_nm']
    match=float(np.max(np.abs(m5a-saved)))
    if match!=0:raise ValueError(f'checkpoint prediction mismatch on original device: {match}')
    x=np.asarray(s.X);anchor=val.anchors;velocity=torch.from_numpy(x[:,-1,2:].astype(np.float64));a=torch.from_numpy(anchor)
    cv_raw=(a[:,None,:]+cv_displacement(velocity)).numpy()
    cv=project_forecast(torch.from_numpy(cv_raw),a,velocity).numpy()
    true=anchor[:,None,:]+np.asarray(s.displacement,dtype=np.float64)
    raw_ade,raw_fde=errors(cv_raw,true);cv_ade,cv_fde=errors(cv,true);m_ade,m_fde=errors(m5a,true)
    cv_bad=severe_qc(torch.from_numpy(cv),a).numpy();raw_bad=severe_qc(torch.from_numpy(cv_raw),a).numpy();m_bad=severe_qc(torch.from_numpy(m5a),a).numpy()
    frame=pd.DataFrame({'encounter_id':s.vessels.encounter_id.astype(str),'vessel':s.vessels.vessel.astype(str),'vessel_id':s.vessels.vessel_id.astype(str),'source':val.sources,'x_row':np.arange(len(val)),
                        'cv_raw_ade':raw_ade,'cv_raw_fde':raw_fde,'cv_ade':cv_ade,'m5a_ade':m_ade,'cv_fde':cv_fde,'m5a_fde':m_fde,'cv_severe':cv_bad,'cv_raw_severe':raw_bad,'m5a_severe':m_bad})
    frame['improvement']=frame.cv_ade-frame.m5a_ade
    if len(frame)!=1670 or frame.encounter_id.nunique()!=835 or not frame.groupby('encounter_id').vessel.agg(lambda a:set(a)=={'A','B'}).all():raise ValueError('encounter coverage invalid')
    metrics=[]
    for name,g in [(n,frame[frame.source==key]) for key,n in LABELS.items()]+[('Overall',frame)]: metrics.append({'source':name,**compare_metrics(g)})
    enc=frame.groupby(['encounter_id','source'],sort=False).agg(vessels=('vessel','size'),cv_ade=('cv_ade','mean'),m5a_ade=('m5a_ade','mean'),cv_fde=('cv_fde','mean'),m5a_fde=('m5a_fde','mean')).reset_index()
    if not (enc.vessels==2).all():raise ValueError('encounter has wrong vessel count')
    enc['improvement']=enc.cv_ade-enc.m5a_ade
    ci={}
    for name,key in [('Real AIS','real_ais_kattegat_v3'),('Yang Lei','yanglei')]:
        group=enc[enc.source==key]; ci[name]={'n_encounters':len(group),'mean_m5a_minus_cv_nm':float(-group.improvement.mean()),'ci_95_m5a_minus_cv_nm':paired_bootstrap(-group.improvement.to_numpy()),'resamples':5000,'seed':20261124,'unit':'encounter','method':'paired percentile bootstrap'}
    features=history_features(x);features['source']=val.sources
    real=features[features.source=='real_ais_kattegat_v3'];turnq=real.mean_abs_turn_deg_per_min.quantile(.75); speedq=real.speed_change_kn.quantile([.25,.75]);midturn=real.mean_abs_turn_deg_per_min.median();midchange=real.speed_change_kn.abs().median()
    turn=features.mean_abs_turn_deg_per_min; change=features.speed_change_kn
    behavior=np.select([(turn>=turnq)&turn.notna(),(turn<turnq)&(change<=speedq.loc[.25]),(turn<turnq)&(change>=speedq.loc[.75]),(turn<=midturn)&(change.abs()<=midchange)],['đổi hướng cao','giảm tốc','tăng tốc','tương đối thẳng/ổn định'],default='hỗn hợp/không rõ')
    frame['behavior']=behavior
    groups=[]
    for (source,kind),g in frame.groupby(['source','behavior'],sort=True):groups.append({'source':LABELS.get(source,source),'behavior':kind,**compare_metrics(g)})
    trfeat=history_features(np.asarray(train.X)); vals=history_features(x)
    domain=distribution(trfeat,vals[val.sources=='real_ais_kattegat_v3'],vals[val.sources=='yanglei'])
    hist=pd.read_csv(SOURCE/'training_history.csv'); cols={'yanglei_ade_nm':'yang_ade','real_ais_kattegat_v3_ade_nm':'real_ade','augmented_real_ais_kattegat_v3_ade_nm':'synthetic_ade','ade_nm':'overall_ade'}
    if not set(cols).issubset(hist.columns) or len(hist)!=25:raise ValueError('training history mismatch')
    epoch=hist[['epoch','loss_total',*cols]].rename(columns=cols)
    best={k:int(epoch.loc[epoch[k].idxmin(),'epoch']) for k in ('yang_ade','real_ade','synthetic_ade','overall_ade')}
    realcorr=float(spearmanr(epoch.loss_total,epoch.real_ade).statistic)
    out.mkdir(parents=True,exist_ok=False)
    pd.DataFrame(metrics).to_csv(out/'cv_vs_m5a_metrics.csv',index=False);frame.to_csv(out/'vessel_level_comparison.csv',index=False);enc.to_csv(out/'encounter_level_comparison.csv',index=False)
    pd.DataFrame(groups).to_csv(out/'behavior_group_analysis.csv',index=False);domain.to_csv(out/'domain_shift_features.csv',index=False);epoch.to_csv(out/'epoch_analysis.csv',index=False)
    summary={'diagnostic_script_sha256':digest(__file__),'checkpoint_epoch':1,'validation_encounters':835,'validation_vessels':1670,'dataset_checksum':checksum,'t10_artifacts_verified':count,'t10_manifest_sha256':MANIFEST_SHA,'saved_gpu_prediction_max_error_nm':match,'raw_vs_projected_cv_max_abs_nm':float(np.max(np.abs(cv_raw-cv))),'cv_raw_severe_vessels':int(raw_bad.sum()),'bootstrap':ci,'epoch_best':best,'epoch_spearman_train_loss_vs_real_ade':realcorr,'behavior_thresholds_from_real_ais_validation_history':{'mean_abs_turn_q75_deg_per_min':float(turnq),'speed_change_q25_kn':float(speedq.loc[.25]),'speed_change_q75_kn':float(speedq.loc[.75]),'mean_abs_turn_median_deg_per_min':float(midturn),'absolute_speed_change_median_kn':float(midchange),'heading_min_speed_kn':.5},'metrics':metrics,'test_tensors_loaded':False,'test_integrity_byte_reads':'checksum only','scaler_fit':False,'model_retrained':False}
    (out/'diagnostic_manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    (out/'bootstrap.json').write_text(json.dumps(ci,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset-root',required=True);p.add_argument('--output-dir',required=True);a=p.parse_args();run(a.dataset_root,a.output_dir)
