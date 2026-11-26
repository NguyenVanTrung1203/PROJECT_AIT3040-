"""Locked Validation-only T14 batch 01; no threshold selection or Test inference."""
import argparse, copy, hashlib, importlib.util, json, os, platform, sys, traceback, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
import torch
from src.protocol.calibration_protocol import load_protocol,semantic_sha256
from src.inference.offline_validation import load_validation
from src.inference.m5a_wrapper import M5aInference,verify_artifacts
from src.models.kinematics import cv_displacement,project_forecast
from src.training.engine import severe_qc
from src.risk.adapter import REFERENCE_HASH,verify_reference
from src.risk.reference_v4 import risk_pipeline as packaged

DATASET_MANIFEST='21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441'
LOCK_SHA='036d9c0e3652e526613238b91151002cbca35615552eba687b588da01b0fe764'
GROUP_SHA='f0702ca49f289ec2a2ec9169e1b5632dcaf330fc634b027a7b11cf89d60ce2ea'

def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,msg):
    if not bool(ok): raise ValueError(msg)
def write_json(path,obj): path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')

def verify_dataset_lock(root):
    require(digest(Path(root)/'DATASET_LOCK_MANIFEST.json')==LOCK_SHA,'dataset lock hash mismatch')

def verify_pairing(s,outputs):
    n=len(s.pairs); values=np.empty((n,2,15,2),dtype=np.float64); seen=set()
    ids=s.encounters.encounter_id.astype(str).tolist(); lookup={x:i for i,x in enumerate(ids)}
    require(len(lookup)==n,'duplicate encounter identity')
    for out in outputs:
        require(not out['fallback_used'] and out['qc_status']=='PASS' and out['input_scope']=='LOCKED_OFFLINE_VALIDATION','untrusted result or fallback')
        v=out['forecast_common_en_nm'].cpu().numpy(); rows=np.asarray(out['x_rows']); names=out['encounter_ids']
        require(v.shape==(len(names),2,15,2) and v.dtype==np.float64 and np.isfinite(v).all() and rows.shape==(len(names),2),'invalid forecast shape/dtype')
        for j,eid in enumerate(names):
            require(eid in lookup and eid not in seen,'missing or duplicate encounter')
            i=lookup[eid]; seen.add(eid)
            require(np.array_equal(rows[j],s.pairs[i]),'A/B row mismatch')
            expected_ids=tuple(str(s.vessels.iloc[int(k)].vessel_id) for k in s.pairs[i])
            require(tuple(out['vessel_ids'][j])==expected_ids,'A/B vessel mismatch')
            anchor=s.metadata.iloc[i].anchor_timestamp.to_pydatetime()
            require(tuple(out['forecast_timestamps'][j])==tuple(anchor+timedelta(minutes=k) for k in range(1,16)),'forecast timestamp mismatch')
            values[i]=v[j]
    require(len(seen)==n,'missing encounters')
    return values

def compare_arrays(original,other,ids):
    require(original.keys()==other.keys(),'risk field keys differ')
    summary={}; failures=[]
    for key in original:
        a=np.asarray(original[key]); b=np.asarray(other[key]); require(a.shape==b.shape and a.shape[0]==len(ids),'risk field shape mismatch '+key)
        if np.issubdtype(a.dtype,np.number):
            require(np.isfinite(a).all() and np.isfinite(b).all(),'nonfinite risk field '+key)
            diff=np.abs(a.astype(np.float64)-b.astype(np.float64)); mismatch=a!=b
            maximum=float(diff.max(initial=0))
        else: mismatch=a!=b; maximum=None
        bad=np.flatnonzero(mismatch.reshape(len(ids),-1).any(axis=1))
        summary[key]={'values':int(a.size),'exact':int(a.size-np.count_nonzero(mismatch)),'mismatches':int(np.count_nonzero(mismatch)),'max_absolute_difference':maximum,'affected_encounter_ids':[ids[i] for i in bad]}
        if len(bad): failures.append(key)
    return summary,failures

def score_pair(original, packaged_engine, features, forecast, ids):
    """Score independent copies of the same canonical input and compare exactly."""
    one=copy.deepcopy(features);two=copy.deepcopy(features);f1=forecast.copy();f2=forecast.copy()
    require(all(np.array_equal(one[k],two[k]) for k in one) and np.array_equal(f1,f2),'scoring input mismatch')
    oscores,odetails=original.calculate(one,f1);pscores,pdetails=packaged_engine.calculate(two,f2)
    fields0={**{'score_'+k:v for k,v in oscores.items()},**{'detail_'+k:v for k,v in odetails.items()}}
    fields1={**{'score_'+k:v for k,v in pscores.items()},**{'detail_'+k:v for k,v in pdetails.items()}}
    summary,bad=compare_arrays(fields0,fields1,ids)
    return oscores,odetails,summary,bad

def verify_output(directory):
    d=Path(directory); lines=(d/'checksums.sha256').read_text(encoding='utf8').splitlines()
    require(bool(lines),'empty checksum manifest')
    for line in lines:
        h,name=line.split('  ',1);require(Path(name).name==name and digest(d/name)==h,'output checksum mismatch')
    return len(lines)

def verify_reuse(directory, dataset_root, artifact_dir, original_v4):
    """Check checksums and current identities before a later batch consumes a run."""
    d=Path(directory); verify_output(d)
    manifest=json.loads((d/'run_manifest.json').read_text(encoding='utf8'))
    status=json.loads((d/'run_status.json').read_text(encoding='utf8'))
    require(status.get('status')=='PASS' and status.get('scope')=='validation' and not status.get('threshold_selection'),'run is not an approved Validation handoff')
    require(manifest['protocol_semantic_sha256']==semantic_sha256(load_protocol(ROOT/'configs/s4_calibration_protocol.yaml')),'protocol identity changed')
    require(manifest['dataset_lock_sha256']==digest(Path(dataset_root)/'DATASET_LOCK_MANIFEST.json')==LOCK_SHA,'dataset lock identity changed')
    require(manifest['dataset_manifest_sha256']==digest(Path(dataset_root)/'manifests/checksums_sha256.txt')==DATASET_MANIFEST,'dataset manifest identity changed')
    require(manifest['dependency_manifest_sha256']==digest(Path(dataset_root)/'manifests/dependency_groups.parquet')==GROUP_SHA,'dependency identity changed')
    require(manifest['artifacts']==verify_artifacts(artifact_dir),'model artifacts changed')
    require(manifest['risk_original_sha256']==digest(original_v4)==REFERENCE_HASH,'original V4 identity changed')
    from src.data.dataset_loader import DatasetLoader
    from src.data.tensor_verification import checksum_dataset
    loader=DatasetLoader(dataset_root)
    require(checksum_dataset(loader.root,loader.lock)['files_verified']==93,'dataset contents changed')
    for name,sha in manifest['source_sha256'].items():
        require(digest(ROOT/name)==sha,'source or config identity changed: '+name)
    for name,sha in manifest['output_sha256'].items():
        require(Path(name).name==name and digest(d/name)==sha,'output identity changed')
    with np.load(d/'cv_predictions.npz',allow_pickle=False) as cv, np.load(d/'m5a_predictions.npz',allow_pickle=False) as m:
        for key in ('encounter_id','source','vessel_ids','anchor_timestamp','forecast_timestamps','frame'):
            require(np.array_equal(cv[key],m[key]),'prediction pairing changed: '+key)
        ids=cv['encounter_id'].astype(str)
        require(len(ids)==835 and len(set(ids))==835 and cv['coordinates_nm'].shape==m['coordinates_nm'].shape==(835,2,15,2),'prediction completeness changed')
    meta=pd.read_parquet(d/'evaluation_metadata.parquet');risk=pd.read_parquet(d/'risk_scores.parquet')
    require(meta.encounter_id.astype(str).tolist()==ids.tolist(),'evaluation identity changed')
    require(len(risk)==1670 and not risk.duplicated(['encounter_id','model_id']).any() and set(risk.model_id)=={'CV','M5a'} and all(set(g.encounter_id.astype(str))==set(ids) for _,g in risk.groupby('model_id')),'risk pairing changed')
    return True

def run(root,artifact_dir,original_path,outbase,device,batch_size):
    root=Path(root).resolve(); artifact_dir=Path(artifact_dir).resolve(); original_path=Path(original_path).resolve()
    outbase=Path(outbase).resolve(); outbase.mkdir(parents=True,exist_ok=True)
    run_id='s4_t14_batch01_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    out=outbase/run_id;out.mkdir(exist_ok=False)
    status={'run_id':run_id,'status':'STARTED','scope':'validation','threshold_selection':False}
    write_json(out/'run_status.json',status)
    try:
        os.environ['DATASET_ROOT']=str(root)
        import scripts.q1_test_access_guard as guard
        guard.pytest_sessionstart(None)
        torch.manual_seed(20261124);np.random.seed(20261124);torch.use_deterministic_algorithms(True)
        protocol=load_protocol(ROOT/'configs/s4_calibration_protocol.yaml')
        require(protocol['model_candidate']['status']=='CANDIDATE' and not protocol['model_lock']['locked'] and not protocol['test_benchmark']['authorized'] and not protocol['production_restrictions']['approved'] and protocol['calibration']['calibrated_m5a_threshold'] is None and protocol['calibration']['calibrated_cv_threshold'] is None,'invalid protocol state')
        verify_dataset_lock(root)
        ah=verify_artifacts(artifact_dir)
        require(ah['x_scaler.json']=='a538be921104ed1bb2fa495c0c3f527c0385fd6c737aa69afda81ba1962d452a' and ah['residual_scaler.json']=='96b062fab9a5d4e27c9b1cc32a649e44e98d29648c7dcc3b7f482eba3d50358f','scaler mismatch')
        require(digest(original_path)==REFERENCE_HASH,'original V4 hash mismatch');verify_reference()
        spec=importlib.util.spec_from_file_location('verified_original_v4',original_path); original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        s,h,checks=load_validation(root);require(checks['manifest_sha256']==DATASET_MANIFEST,'dataset checksum manifest mismatch')
        ids=s.encounters.encounter_id.astype(str).tolist();n=len(ids);require(n==835,'validation count mismatch')
        gp=root/'manifests/dependency_groups.parquet';require(digest(gp)==GROUP_SHA,'dependency manifest hash mismatch')
        groups=pd.read_parquet(gp,filters=[('package_split','==','validation')]);require(len(groups)==n and not groups.encounter_id.duplicated().any() and groups.dependency_group_id.notna().all() and set(groups.encounter_id.astype(str))==set(ids),'dependency identity mismatch')
        groupmap=groups.set_index('encounter_id').dependency_group_id;groupids=[str(groupmap.loc[x]) for x in ids];counts=pd.Series(groupids).value_counts();require(len(counts)==260 and counts.iloc[0]==556 and all(groupids),'dependency group mismatch')
        model=M5aInference(artifact_dir,device=device);outputs,_=model.predict_validation(root,batch_size=batch_size,allow_fallback=False)
        pred=verify_pairing(s,outputs); a=torch.from_numpy(np.array(s.anchors,dtype=np.float64).reshape(-1,2));x=np.asarray(s.X[s.pairs]);vel=x[:,:,:,2:].astype(np.float64);v=torch.from_numpy(vel[:,:,-1,:].reshape(-1,2));
        with torch.inference_mode(): cv=project_forecast(a[:,None,:]+cv_displacement(v),a,v).numpy().reshape(n,2,15,2)
        qcm=severe_qc(torch.from_numpy(pred.reshape(-1,15,2)),a).numpy().reshape(n,2);qcc=severe_qc(torch.from_numpy(cv.reshape(-1,15,2)),a).numpy().reshape(n,2)
        qc={'CV':{'severe_vessels':int(qcc.sum()),'severe_encounters':int(qcc.any(axis=1).sum())},'M5a':{'severe_vessels':int(qcm.sum()),'severe_encounters':int(qcm.any(axis=1).sum())}}
        write_json(out/'qc_summary.json',qc);require(not qcc.any() and not qcm.any(),'severe QC detected')
        values=h[['SOG','COG']].to_numpy(dtype=np.float64).reshape(len(s.X),10,2)[s.pairs]
        pos=x[:,:,:,:2].astype(np.float64)+np.asarray(s.anchors)[:,:,None,:]
        r0,scene0=original.infer_roles(pos,vel);r1,scene1=packaged.infer_roles(pos,vel)
        rule0=original.rule_component(values[:,:,:,1],values[:,:,:,0],r0);rule1=packaged.rule_component(values[:,:,:,1],values[:,:,:,0],r1)
        role_summary,role_bad=compare_arrays({'role':r0,'scene':scene0,'rule':rule0},{'role':r1,'scene':scene1,'rule':rule1},ids);require(not role_bad,'role/rule mismatch')
        feat={'last':np.array(s.anchors,copy=True),'vel':vel,'rule':rule0};scores={};parity={'roles':role_summary,'models':{}}
        for name,forecast in [('CV',cv),('M5a',pred)]:
            oscores,odetails,summary,bad=score_pair(original,packaged,feat,forecast,ids)
            parity['models'][name]=summary;write_json(out/'parity.json',parity)
            require(not bad,'risk exact parity mismatch: '+str(bad));scores[name]=(oscores,odetails)
        # Scoring is complete; evaluation-only future and labels are read only below.
        labels=np.asarray(s.labels).copy();sources=s.metadata.data_source.astype(str).to_numpy()
        source_counts=pd.crosstab(pd.Series(sources,name='source'),pd.Series(labels,name='label')).to_dict()
        require(int((labels==1).sum())==425 and int((labels==0).sum())==410,'unexpected label counts')
        loader_path=root/'validation/data/validation_835.parquet'; cols=['encounter_id','vessel','relative_minute','is_future','LAT','LON','timestamp_utc','anchor_timestamp']
        future=pd.read_parquet(loader_path,columns=cols,filters=[('is_future','==',True)])
        future=future.merge(s.vessels[['encounter_id','vessel','X_row']],on=['encounter_id','vessel'],validate='many_to_one').sort_values(['X_row','relative_minute'])
        require(len(future)==1670*15 and future.is_future.all() and np.array_equal(future.X_row,np.repeat(np.arange(1670),15)) and np.array_equal(future.relative_minute,np.tile(np.arange(1,16),1670)),'future mapping failure')
        require((future.timestamp_utc==future.anchor_timestamp+pd.to_timedelta(future.relative_minute,unit='min')).all(),'future timestamp mismatch')
        coords=future[['LAT','LON']].to_numpy(dtype=np.float64).reshape(1670,15,2)[s.pairs]; require(np.isfinite(coords).all(),'nonfinite future')
        lat=np.deg2rad(coords[:,:,:,0]);lon=np.deg2rad(coords[:,:,:,1]);hv=np.sin((lat[:,0]-lat[:,1])/2)**2+np.cos(lat[:,0])*np.cos(lat[:,1])*np.sin((lon[:,0]-lon[:,1])/2)**2
        dist=(6880.13*np.arcsin(np.sqrt(np.clip(hv,0,1)))).min(axis=1)
        close=(sources=='augmented_real_ais_kattegat_v3')&(labels==1)&(dist<0.1);require(int(close.sum())==60,'unexpected close-positive count')
        truth=np.asarray(s.common,dtype=np.float64);require(truth.shape==(n,2,15,2) and np.isfinite(truth).all(),'invalid future target')
        meta=pd.DataFrame({'encounter_id':ids,'source':sources,'label':labels,'dependency_group_id':groupids,'close_positive':close,'minimum_future_haversine_nm':dist})
        for name,forecast in [('CV',cv),('M5a',pred)]:
            error=np.linalg.norm(forecast-truth,axis=-1);meta[name+'_ade_nm']=error.mean(axis=(1,2),dtype=np.float64);meta[name+'_fde_nm']=error[:,:,-1].mean(axis=1,dtype=np.float64)
        meta.to_parquet(out/'evaluation_metadata.parquet',index=False)
        vessels=s.vessels.iloc[s.pairs.ravel()].vessel_id.to_numpy(dtype=str).reshape(n,2)
        times=np.array([[str(t+pd.Timedelta(minutes=k)) for k in range(1,16)] for t in s.metadata.anchor_timestamp])
        for name,forecast in [('CV',cv),('M5a',pred)]:
            np.savez_compressed(out/(name.lower()+'_predictions.npz'),encounter_id=np.array(ids),source=sources.astype(str),vessel_ids=vessels,anchor_timestamp=s.metadata.anchor_timestamp.astype(str).to_numpy(dtype=str),forecast_timestamps=times,frame=np.array('common_EN_origin_A_t-9'),coordinates_nm=forecast,qc_status=np.full(n,'PASS'))
        rows=[]
        for name,(sc,de) in scores.items():
            frame=pd.DataFrame({'encounter_id':ids,'model_id':name,'source':sources,'role':r0,'scene':scene0,'current_dcpa_nm':de['dcpa_nm'],'current_tcpa_min':de['tcpa_clipped_min'],'predicted_dcpa_nm':de['pred_dmin_nm'],'predicted_tcpa_min':de['pred_tmin'],'rule':de['rule'],'current_cpa_risk':sc['Current-CPA'],'predicted_cpa_risk':sc['GRU-P-CPA'],'cc_dri':sc['CC-DRI'],'scoring_implementation':'original_and_packaged_exact','qc_status':'PASS'});rows.append(frame)
        pd.concat(rows,ignore_index=True).to_parquet(out/'risk_scores.parquet',index=False)
        import joblib, sklearn, pyarrow
        relevant=['configs/s4_calibration_protocol.yaml','configs/data_config.yaml','configs/model_config.yaml','configs/projection_config.yaml','configs/risk_config.yaml','configs/risk_reference_manifest.yaml','configs/s4_t14_observed_dependency_closure.yaml','src/inference/offline_validation.py','src/inference/m5a_wrapper.py','src/data/dataset_loader.py','src/data/tensor_verification.py','src/utils/paths.py','src/training/data.py','scripts/verify_feature_contract.py','src/models/kinematics.py','src/models/pipeline.py','src/models/m5a.py','src/models/scalers.py','src/training/engine.py','src/risk/adapter.py','src/risk/reference_v4/risk_pipeline.py','src/protocol/calibration_protocol.py','scripts/q1_test_access_guard.py','scripts/run_s4_t14_step03_batch01.py']
        import subprocess
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        output_names=['cv_predictions.npz','m5a_predictions.npz','risk_scores.parquet','evaluation_metadata.parquet','parity.json','qc_summary.json']
        manifest={'run_id':run_id,'created_utc':datetime.now(timezone.utc).isoformat(),'git_head':head,'protocol_semantic_sha256':semantic_sha256(protocol),'dataset_manifest_sha256':DATASET_MANIFEST,'dataset_lock_sha256':LOCK_SHA,'dependency_manifest_sha256':GROUP_SHA,'artifact_manifest_sha256':digest(artifact_dir/'checksums.sha256'),'artifacts':ah,'risk_original_sha256':digest(original_path),'risk_packaged_sha256':digest(Path(packaged.__file__)),'source_sha256':{p:digest(ROOT/p) for p in relevant},'environment':{'python':platform.python_version(),'numpy':np.__version__,'torch':torch.__version__,'cuda_available':torch.cuda.is_available(),'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,'pandas':pd.__version__,'joblib':joblib.__version__,'scikit_learn':sklearn.__version__,'pyarrow':pyarrow.__version__,'device':str(model.device),'batch_size':batch_size,'model_dtype':'float32','projection_dtype':'float64','seed':20261124,'deterministic_algorithms':True},'validation_encounters':n,'vessels':2*n,'source_labels':source_counts,'close_positive':int(close.sum()),'parent_run_ids':[],'limitations':['dependency provenance PARTIAL; grouping CONDITIONAL','clean environment NOT_VERIFIED','V1 review required','not production'], 'output_sha256':{p:digest(out/p) for p in output_names},'test_access_guard':guard.counters,'threshold_selection':False}
        write_json(out/'run_manifest.json',manifest);status.update(status='PASS',qc=qc,encounters=n,close_positive=int(close.sum()),test_access_guard=guard.counters);write_json(out/'run_status.json',status)
        names=output_names+['run_manifest.json','run_status.json'];(out/'checksums.sha256').write_text(''.join(digest(out/p)+'  '+p+'\n' for p in names),encoding='utf8');verify_output(out)
        print(json.dumps({'directory':str(out),'status':status,'source_labels':source_counts,'environment':manifest['environment'],'parity':parity},ensure_ascii=False),flush=True)
    except Exception as e:
        status.update(status='FAILED',error_type=type(e).__name__,error=str(e),traceback=traceback.format_exc());write_json(out/'run_status.json',status);print(json.dumps({'directory':str(out),'status':status},ensure_ascii=False),flush=True);raise
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scope',choices=['validation'],required=True);p.add_argument('--dataset-root',required=True);p.add_argument('--artifact-dir',required=True);p.add_argument('--original-v4',required=True);p.add_argument('--output-root',required=True);p.add_argument('--device',choices=['auto','cuda','cpu'],default='auto');p.add_argument('--batch-size',type=int,default=128);a=p.parse_args();require(a.batch_size>0,'invalid batch size');run(a.dataset_root,a.artifact_dir,a.original_v4,a.output_root,a.device,a.batch_size)
if __name__=='__main__':main()
