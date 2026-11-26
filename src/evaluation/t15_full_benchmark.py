"""T15 fixed operating-point evaluation; caller must first pass authorization."""
import json,sys,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score,average_precision_score
from src.evaluation.t15_authorization import verify_context,AuthorizationError
from src.evaluation.t15_trusted_test import LoadedTest,make_authorized_batch,append_audit
from src.evaluation.t15_full_data_boundary import PhasedInput,read_evaluation,input_requirements,evaluation_requirements
from src.evaluation.t15_full_access_audit import verify_events
from src.evaluation.t15_source_registry import TEST_SOURCES
from src.inference.m5a_wrapper import M5aInference,validate
from src.models.pipeline import forecast
from src.models.kinematics import cv_displacement,project_forecast
from src.training.engine import severe_qc
from src.risk.adapter import ref
from scripts.run_s4_t14_step03_batch02 import SOURCE,candidate,describe_candidate,d2_eval,conditional_metrics,score_metric


def _write(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')

def _category_values(series):
    return series.astype('string').fillna('MISSING').to_numpy(dtype=str)

def _score_inputs(split,history):
    """Build V4 scoring inputs exclusively from trusted history and anchor."""
    x=np.asarray(split.X[split.pairs]);anchors=np.asarray(split.anchors);vel=x[:,:,:,2:].astype(np.float64)
    vals=history[['SOG','COG']].to_numpy(dtype=np.float64).reshape(len(split.X),10,2)[split.pairs]
    pos=x[:,:,:,:2].astype(np.float64)+anchors[:,:,None,:]
    roles,scenarios=ref.infer_roles(pos,vel);rule=ref.rule_component(vals[:,:,:,1],vals[:,:,:,0],roles)
    return {'last':anchors,'vel':vel,'rule':rule},roles,scenarios


def _sync(device):
    if str(device)=='cuda':torch.cuda.synchronize()


def fixed_d2_status(cv_d1,m5a_d1,comparison_status):
    """Apply pre-Test Trung decision without searching new Test thresholds."""
    if 'D1_INCONCLUSIVE' in (cv_d1,m5a_d1):return 'D2_BLOCKED'
    if m5a_d1!='D1_PASS':return 'D2_FAIL'
    if comparison_status!='D2_PASS':return comparison_status
    return 'D2_CONDITIONAL' if cv_d1=='D1_FAIL' else 'D2_PASS'


def forecast_test(loaded,artifact_dir,device='auto',batch_size=128):
    """Only issued context and T11-validated history enter the locked pipeline."""
    if not isinstance(loaded,LoadedTest):raise AuthorizationError('unverified Test input')
    verify_context(loaded.context);s=loaded.split;n=len(s.pairs);t=time.perf_counter();model=M5aInference(artifact_dir,device);_sync(model.device);load_seconds=time.perf_counter()-t
    if model.model.training or sum(p.numel() for p in model.model.parameters())!=15390:raise RuntimeError('model mismatch')
    out=np.empty((n,2,15,2),dtype=np.float64);ms=[];t0=time.perf_counter()
    with torch.inference_mode():
        for start in range(0,n,batch_size):
            stop=min(start+batch_size,n);batch=make_authorized_batch(loaded,start,stop);validate(batch)
            x=batch.history.reshape(-1,10,4).to(model.device);a=batch.anchors.reshape(-1,2).to(model.device)
            _sync(model.device);start_time=time.perf_counter();result=forecast(model.model,model.x_scaler,model.residual_scaler,x,a)
            if not torch.isfinite(result).all() or severe_qc(result,a).any():raise RuntimeError('M5a nonfinite or severe QC; no fallback')
            _sync(model.device);ms.append(time.perf_counter()-start_time);out[start:stop]=result.cpu().numpy().reshape(stop-start,2,15,2)
    return out,model,{'model_load_seconds':load_seconds,'inference_projection_qc_seconds':time.perf_counter()-t0,'batch_seconds':ms,'batch_size':batch_size,'device':str(model.device),'warmup':'no warmup; primary run includes cold batch','synchronization':'cuda synchronize before/after each batch','samples':n,'fallback':False}


def _timing_replay(loaded,artifact,device,batch_size=128):
    """Timing-only same Test history; output never substituted for primary."""
    t=time.perf_counter();model=M5aInference(artifact,device);_sync(model.device);load=time.perf_counter()-t;n=len(loaded.split.pairs);runs=[]
    with torch.inference_mode():
        # One predeclared warmup batch, excluded from measured batches.
        b=make_authorized_batch(loaded,0,min(batch_size,n));validate(b);x=b.history.reshape(-1,10,4).to(model.device);a=b.anchors.reshape(-1,2).to(model.device);forecast(model.model,model.x_scaler,model.residual_scaler,x,a);_sync(model.device)
        for start in range(0,n,batch_size):
            stop=min(start+batch_size,n);b=make_authorized_batch(loaded,start,stop);validate(b);x=b.history.reshape(-1,10,4).to(model.device);a=b.anchors.reshape(-1,2).to(model.device)
            _sync(model.device);q=time.perf_counter();z=forecast(model.model,model.x_scaler,model.residual_scaler,x,a);assert torch.isfinite(z).all() and not severe_qc(z,a).any();_sync(model.device);runs.append(time.perf_counter()-q)
    total=float(sum(runs));return {'device':str(model.device),'model_load_seconds':load,'batch_size':batch_size,'samples':n,'timed_batches':len(runs),'warmup_batches':1,'batch_seconds':runs,'batch_mean_seconds':float(np.mean(runs)),'batch_median_seconds':float(np.median(runs)),'batch_p95_seconds':float(np.percentile(runs,95)),'throughput_vessels_per_second':2*n/total,'scope':'forecast+projection+QC batch time; excludes loader, transfer and scoring; not single-request or runtime/API latency','cuda_synchronized':str(model.device)=='cuda'}


def evaluate_loaded(loaded,out,artifact_dir,*,synthetic_expected_sources=None,synthetic_skip_timing=False):
    if not isinstance(loaded,PhasedInput):raise AuthorizationError('full audited input required')
    verify_context(loaded.context);out=Path(out);s=loaded.split;h=loaded.history;ids=s.encounters.encounter_id.astype(str).to_numpy();n=len(ids)
    expected=synthetic_expected_sources if synthetic_expected_sources is not None else {'yang_lei':720,'real_ais_denmark_oct2025':300,'synthetic_ais_denmark_oct2025':300}
    if n!=sum(expected.values()) or len(set(ids))!=n:raise RuntimeError('Test identity/count mismatch')
    if len(s.vessels)!=2*n or dict(Counter(s.metadata.data_source.astype(str)))!=expected:raise RuntimeError('Test source/vessel count mismatch before inference')
    pre_events=[json.loads(line) for line in loaded.audit.path.read_text(encoding='utf8').splitlines()]
    if verify_events(pre_events,input_requirements(n),loaded.audit.identity,require_authorization=True)['status']!='PASS':raise RuntimeError('input access audit incomplete')
    loaded.audit.complete_phase('trusted_input');started=time.perf_counter();m5a,model,primary=forecast_test(loaded,artifact_dir)
    x=np.asarray(s.X[s.pairs]);anchors=np.asarray(s.anchors,dtype=np.float64);v=x[:,:,-1,2:].astype(np.float64)
    aa=torch.from_numpy(anchors.reshape(-1,2).copy());vv=torch.from_numpy(v.reshape(-1,2).copy())
    with torch.inference_mode():cv=project_forecast(aa[:,None,:]+cv_displacement(vv),aa,vv)
    if not torch.isfinite(cv).all() or severe_qc(cv,aa).any():raise RuntimeError('CV severe QC')
    cv=cv.numpy().reshape(n,2,15,2)
    loaded.audit.complete_phase('inference')
    # No labels, targets or future rows are used to construct these inputs.
    feat,roles,scenarios=_score_inputs(s,h);rt=time.perf_counter();risk={}
    for name,pred in [('CV',cv),('M5a',m5a)]:
        scores,details=ref.calculate(feat,pred)
        if not all(np.isfinite(q).all() for q in scores.values()) or not np.all((scores['CC-DRI']>=0)&(scores['CC-DRI']<=1)):raise RuntimeError('invalid risk scores')
        risk[name]=(scores,details)
    risk_seconds=time.perf_counter()-rt
    loaded.audit.complete_phase('risk_scoring')
    evaluation_started=time.perf_counter()
    s=read_evaluation(loaded)
    # Evaluation only: label/target values and future rows first consumed here.
    y=np.asarray(s.labels).copy();sources=s.metadata.data_source.astype(str).to_numpy();src=pd.Series(sources).map(TEST_SOURCES).to_numpy()
    if np.any(pd.isna(src)) or not np.isin(y,[0,1]).all():raise RuntimeError('invalid labels/source')
    if dict(Counter(sources))!=expected:raise RuntimeError('source count mismatch')
    fpath=loaded.context.dataset_root/'test/data/test_1320.parquet'
    cols=['encounter_id','vessel','relative_minute','is_future','LAT','LON','timestamp_utc','anchor_timestamp'];future=loaded.audit.read('evaluation','future',lambda:pd.read_parquet(fpath,columns=cols,filters=[('is_future','==',True)]),coverage={'rows':2*n*15,'columns':cols,'filter':'future'},operation='parquet future projected columns')
    future=future.merge(s.vessels[['encounter_id','vessel','X_row']],on=['encounter_id','vessel'],validate='many_to_one').sort_values(['X_row','relative_minute'])
    if len(future)!=2*n*15 or not future.is_future.all() or not np.array_equal(future.X_row,np.repeat(np.arange(2*n),15)) or not np.array_equal(future.relative_minute,np.tile(np.arange(1,16),2*n)) or not (future.timestamp_utc==future.anchor_timestamp+pd.to_timedelta(future.relative_minute,unit='min')).all():raise RuntimeError('future identity or timestamp mismatch')
    coords=future[['LAT','LON']].to_numpy(dtype=np.float64).reshape(2*n,15,2)[s.pairs];lat=np.deg2rad(coords[:,:,:,0]);lon=np.deg2rad(coords[:,:,:,1]);hv=np.sin((lat[:,0]-lat[:,1])/2)**2+np.cos(lat[:,0])*np.cos(lat[:,1])*np.sin((lon[:,0]-lon[:,1])/2)**2;distance=(6880.13*np.arcsin(np.sqrt(np.clip(hv,0,1)))).min(axis=1)
    close=(src=='SYNTHETIC_AIS')&(y==1)&(distance<.1);truth=np.asarray(s.common,dtype=np.float64)
    if truth.shape!=(n,2,15,2) or not np.isfinite(truth).all():raise RuntimeError('invalid evaluation targets')
    meta=pd.DataFrame({'encounter_id':ids,'source':sources,'raw_source_id':sources,'canonical_source_type':src,'label':y,'close_positive':close,'minimum_future_haversine_nm':distance})
    for name,pred in [('CV',cv),('M5a',m5a)]:
        err=np.linalg.norm(pred-truth,axis=-1);meta[name+'_ade_nm']=err.mean(axis=(1,2),dtype=np.float64);meta[name+'_fde_nm']=err[:,:,-1].mean(axis=1,dtype=np.float64)
    meta.to_parquet(out/'evaluation_metadata.parquet',index=False)
    vessels=s.vessels.iloc[s.pairs.ravel()].vessel_id.to_numpy(dtype=str).reshape(n,2);times=np.array([[str(t+pd.Timedelta(minutes=k)) for k in range(1,16)] for t in s.metadata.anchor_timestamp])
    for name,pred in [('CV',cv),('M5a',m5a)]:np.savez_compressed(out/(name.lower()+'_predictions.npz'),encounter_id=ids.astype(str),source=sources.astype(str),raw_source_id=sources.astype(str),canonical_source_type=src.astype(str),vessel_ids=vessels,anchor_timestamp=s.metadata.anchor_timestamp.astype(str).to_numpy(dtype=str),forecast_timestamps=times,frame=np.array('common_EN_origin_A_t-9'),coordinates_nm=pred,qc_status=np.full(n,'PASS'))
    d1={};records=[];metric=[];preds={};scores_by={}
    for name,k in [('CV',87),('M5a',84)]:
        sc,de=risk[name];score=sc['CC-DRI'];scores_by[name]=score;preds[name]=score>=k/200;can=candidate(y,src,close,score,k);row=describe_candidate(can);d1[name]={'status':'D1_PASS' if row['feasible'] else ('D1_INCONCLUSIVE' if any(row[x]!='VALID_SUPPORT' for x in ['overall_recall_support','real_fpr_support','synthetic_recall_support','close_recall_support','f1_support']) else 'D1_FAIL'),'fixed_threshold':k/200,'grid_index':k,'candidate':row}
        records.append(pd.DataFrame({'encounter_id':ids,'model_id':name,'source':sources,'raw_source_id':sources,'canonical_source_type':src,'role':roles,'scenario':scenarios,'current_dcpa_nm':de['dcpa_nm'],'current_tcpa_min':de['tcpa_clipped_min'],'predicted_dcpa_nm':de['pred_dmin_nm'],'predicted_tcpa_min':de['pred_tmin'],'rule':de['rule'],'current_cpa_risk':sc['Current-CPA'],'predicted_cpa_risk':sc['GRU-P-CPA'],'cc_dri':score,'threshold':k/200,'decision':preds[name],'qc_status':'PASS'}))
        for group,mask in [('overall',np.ones(n,dtype=bool)),('YANG_LEI',src=='YANG_LEI'),('REAL_AIS',src=='REAL_AIS'),('SYNTHETIC_AIS',src=='SYNTHETIC_AIS'),('close_positive',close)]:
            item={'model':name,'group':group,'count':int(mask.sum()),'positive':int((y[mask]==1).sum()),'negative':int((y[mask]==0).sum()),'roc_auc':score_metric(y[mask],score[mask],'roc_auc'),'average_precision':score_metric(y[mask],score[mask],'average_precision'),'operating_point':conditional_metrics(y[mask],preds[name][mask])}
            for kind in ('ade','fde'):
                z=meta[name+'_'+kind+'_nm'].to_numpy(dtype=np.float64)[mask];item[kind]={'value':float(z.mean()) if len(z) else None,'support':'VALID_SUPPORT' if len(z)>=30 else ('LOW_SUPPORT' if len(z) else 'NA'),'unit':'nm'}
            metric.append(item)
    pd.concat(records,ignore_index=True).to_parquet(out/'risk_scores.parquet',index=False)
    cvcan=candidate(y,src,close,scores_by['CV'],87);mcan=candidate(y,src,close,scores_by['M5a'],84);real=src=='REAL_AIS'
    if d1['M5a']['status']=='D1_INCONCLUSIVE' or d1['CV']['status']=='D1_INCONCLUSIVE':d2={'status':'D2_BLOCKED','reason':'required support inconclusive'}
    elif d1['M5a']['status']!='D1_PASS':d2={'status':'D2_FAIL','reason':'M5a fixed-threshold D1 failed'}
    else:
        d2=d2_eval(cvcan,mcan,meta.CV_ade_nm.mean(),meta.M5a_ade_nm.mean(),meta.CV_ade_nm[real].mean(),meta.M5a_ade_nm[real].mean(),list(ids[close]),list(ids[close&preds['CV']]),list(ids[close&preds['M5a']]))
        d2['status']=fixed_d2_status(d1['CV']['status'],d1['M5a']['status'],d2['status'])
        if d2['status']=='D2_CONDITIONAL':d2['reason']='CV fixed threshold failed D1; pre-Test Trung decision'
    benchmark='BENCHMARK_PASS' if d2['status']=='D2_PASS' else ('BENCHMARK_CONDITIONAL' if d2['status']=='D2_CONDITIONAL' else ('BENCHMARK_FAIL' if d2['status']=='D2_FAIL' else 'BENCHMARK_BLOCKED'))
    c=preds['CV'];m=preds['M5a'];cat=np.select([(y==1)&c&m,(y==1)&~c&~m,(y==1)&~c&m,(y==1)&c&~m,(y==0)&~c&~m,(y==0)&c&m,(y==0)&c&~m,(y==0)&~c&m],['positive_both_detected','positive_both_missed','positive_m5a_improved','positive_m5a_new_miss','negative_both_rejected','negative_both_false_alarm','negative_m5a_improved','negative_m5a_new_false_alarm'],default='INVALID')
    paired=meta.copy()
    for name,k in [('CV',87),('M5a',84)]:paired[name+'_score']=scores_by[name];paired[name+'_decision']=preds[name];paired[name+'_margin']=scores_by[name]-k/200
    paired['paired_outcome']=cat;paired.to_parquet(out/'paired_encounter_outcomes.parquet',index=False)
    analysis={'paired':{},'real_false_alarm':{},'near_threshold':{},'close':d2.get('close',{})}
    for category in sorted(set(cat)):
        mask=cat==category;analysis['paired'][category]={'count':int(mask.sum()),'ids':ids[mask].tolist(),'source_counts':dict(Counter(src[mask]))}
    for name,mask in [('cv_false_positive',real&c),('m5a_false_positive',real&m),('shared',real&c&m),('eliminated',real&c&~m),('introduced',real&~c&m)]:analysis['real_false_alarm'][name]={'count':int(mask.sum()),'ids':ids[mask].tolist(),'score_deltas':{str(ids[i]):float(scores_by['M5a'][i]-scores_by['CV'][i]) for i in np.flatnonzero(mask)}}
    for name,k in [('CV',87),('M5a',84)]:
        margin=scores_by[name]-k/200;ix=int(np.argmin(np.abs(margin)));analysis['near_threshold'][name]={'nearest_id':str(ids[ix]),'margin':float(margin[ix]),'within_5e_5':int((np.abs(margin)<=5e-5).sum())}
    _write(out/'fixed_threshold_d1_results.json',d1);_write(out/'fixed_threshold_d2_results.json',d2);_write(out/'performance_metrics.json',metric);_write(out/'error_analysis.json',analysis)
    distribution={'encounters':n,'vessels':len(s.vessels),'sources':dict(Counter(sources)),'positive':int((y==1).sum()),'negative':int((y==0).sum()),'close_positive':int(close.sum())};_write(out/'dataset_distribution.json',distribution)
    difficulty={}
    for col in ('difficulty','scenario'):
        if col in s.metadata.columns:
            values=_category_values(s.metadata[col]);difficulty[col]={'counts':dict(Counter(values)),'per_category':{}}
            for val in sorted(set(values)):
                mask=values==val;difficulty[col]['per_category'][val]={'count':int(mask.sum()),'CV':conditional_metrics(y[mask],preds['CV'][mask]),'M5a':conditional_metrics(y[mask],preds['M5a'][mask])}
    _write(out/'difficulty_metrics.json',difficulty if difficulty else {'status':'NOT_AVAILABLE'})
    timing={'primary':primary,'risk_scoring_seconds_two_models':risk_seconds,'evaluation_seconds':time.perf_counter()-evaluation_started,'offline_processing_seconds_excludes_load':time.perf_counter()-started,'cpu':_timing_replay(loaded,artifact_dir,'cpu') if not synthetic_skip_timing else {'status':'SYNTHETIC_ONLY'},'cuda':(_timing_replay(loaded,artifact_dir,'cuda') if torch.cuda.is_available() else {'status':'UNAVAILABLE'}) if not synthetic_skip_timing else {'status':'SYNTHETIC_ONLY'},'audit':dict(loaded.audit.stats),'note':'Timing-only replay; audit statistics cover events through evaluation reads and exclude the final audit-summary event; timing does not represent API latency.'};_write(out/'latency_summary.json',timing)
    loaded.audit.complete_phase('evaluation')
    all_events=[json.loads(line) for line in loaded.audit.path.read_text(encoding='utf8').splitlines()]
    audit_status=verify_events(all_events,{**input_requirements(n),**evaluation_requirements(n)},loaded.audit.identity,require_authorization=True)
    _write(out/'final_full_run_access_audit.json',audit_status)
    if audit_status['status']!='PASS':raise RuntimeError('full access audit incomplete')
    _write(out/'benchmark_acceptance.json',{'classification':'REUSED_DEVELOPMENT_BENCHMARK','status':benchmark,'d1':{k:v['status'] for k,v in d1.items()},'d2':d2['status'],'production_approved':False})
    return {'status':'COMPLETE','distribution':distribution,'d1':d1,'d2':d2,'benchmark':benchmark,'risk_count_per_model':n,'forecast_shape':[n,2,15,2],'latency':timing}
