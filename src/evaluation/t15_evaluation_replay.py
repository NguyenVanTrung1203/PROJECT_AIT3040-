"""Pinned R2 evaluation replay: no predictor or risk-scoring entrypoints."""
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.dataset_loader import DatasetLoader
from src.data.tensor_verification import checksum_dataset
from src.evaluation.t15_authorization import (AuthorizationError, DATASET_LOCK, DATASET_MANIFEST,
    LOCK_ID, LOCK_SHA, PAYLOAD_SHA, _pre_gate_test_guard, _read_pinned_json)
from src.evaluation.t15_source_registry import TEST_SOURCES
from src.release.offline_lock import digest, verify_active
from scripts.run_s4_t14_step03_batch02 import candidate, describe_candidate, conditional_metrics, score_metric

PARENT='s4_t15_r2_20261125T152141Z_2cd800cd'
PARENT_MANIFEST='8ba0913490dd8f56fc5f445e43e16dbb7a254a9dd4818861db1d0ecdbf160a15'
PROTOCOL='606bf33104c88bb0feac4ce24ef0b95f1efc7966fa5d479d3ec5cd7296c8a735'
POINTS={'CV':0.435,'M5a':0.42,'comparator':'>='}
ROOT=Path(__file__).resolve().parents[2]
READS={'labels':'test/tensors/labels.npy','target':'test/tensors/target_EN_nm.npy',
       'index':'test/tensors/encounter_tensor_index.csv','future':'test/data/test_1320.parquet'}


def require(ok, message):
    if not bool(ok):raise AuthorizationError(message)


def write(path, value):
    with Path(path).open('x',encoding='utf8') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())


def event(log, identity, state, category, detail=None):
    e={'event_id':uuid.uuid4().hex,**identity,'timestamp_utc':datetime.now(timezone.utc).isoformat(),
       'phase':'EVALUATION_ONLY','category':category,'state':state,'path':READS.get(category),
       'operation':detail}
    with Path(log).open('a',encoding='utf8') as f:
        f.write(json.dumps(e,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())


def audited_read(log, identity, category, operation, fn):
    event(log,identity,'ATTEMPTED',category,operation)
    try:result=fn()
    except Exception as exc:
        event(log,identity,'FAILED',category,type(exc).__name__);raise
    event(log,identity,'OBSERVED',category,operation)
    return result


def event_summary(path):
    es=[json.loads(x) for x in Path(path).read_text(encoding='utf8').splitlines()] if Path(path).exists() else []
    return {k:[e['state'] for e in es if e['category']==k] for k in READS}


def verify_parent(parent, expected_manifest=PARENT_MANIFEST):
    p=Path(parent).resolve();require(p.name==PARENT,'wrong parent run')
    require(digest(p/'run_manifest.json')==expected_manifest==PARENT_MANIFEST,'parent manifest identity mismatch')
    manifest=json.loads((p/'run_manifest.json').read_text(encoding='utf8'))
    require(manifest['run_id']==PARENT and manifest['protocol_sha256']==PROTOCOL and manifest['lock_id']==LOCK_ID and manifest['package_identity']==PAYLOAD_SHA and manifest['dataset']['lock_sha256']==DATASET_LOCK,'parent identity mismatch')
    checks={}
    for line in (p/'checksums.sha256').read_text(encoding='utf8').splitlines():
        sha,name=line.split('  ',1);require(Path(name).name==name and name not in checks,'invalid parent checksum path');require(digest(p/name)==sha,'parent checksum mismatch: '+name);checks[name]=sha
    require(len(checks)==29,'parent inventory mismatch')
    for n,sha in manifest['output_sha256'].items():require(checks.get(n)==sha,'manifest/checksum mismatch: '+n)
    require(json.loads((p/'pre_access_gate_report.json').read_text())['status']=='PASS','parent gate failed')
    status=json.loads((p/'run_status.json').read_text());require(status.get('completed') is True and status.get('benchmark')=='BENCHMARK_FAIL','parent completion mismatch')
    latency=json.loads((p/'latency_summary.json').read_text());require(latency['primary'].get('fallback') is False,'fallback used or evidence missing')
    supplement=p.parent/'s4_t15_r2_reporting_supplement_20261125';supplement_checks={}
    for line in (supplement/'checksums.sha256').read_text(encoding='utf8').splitlines():
        sha,name=line.split('  ',1);require(Path(name).name==name and name not in supplement_checks and digest(supplement/name)==sha,'supplement checksum mismatch');supplement_checks[name]=sha
    require(len(supplement_checks)==5 and 'd2_comparison_supplement.json' in supplement_checks,'supplement inventory mismatch')
    events=[json.loads(s) for s in (p/'test_access_events.jsonl').read_text().splitlines()]
    require(any(e.get('state')=='SEMANTIC_ACCESS_OBSERVED' and e.get('path')=='test/tensors/X_unscaled.npy' for e in events),'parent inference input evidence missing')
    arr={}
    for name in ('CV','M5a'):
        with np.load(p/(name.lower()+'_predictions.npz'),allow_pickle=False) as z:arr[name]={k:z[k].copy() for k in z.files}
        z=arr[name];require(z['coordinates_nm'].shape==(1320,2,15,2) and np.isfinite(z['coordinates_nm']).all(),'invalid forecast')
        require(len(set(z['encounter_id'].tolist()))==1320 and z['vessel_ids'].shape==(1320,2) and np.all(z['vessel_ids'][:,0]!=z['vessel_ids'][:,1]),'forecast identity invalid')
        require(np.all(z['qc_status']=='PASS') and str(z['frame'])=='common_EN_origin_A_t-9','forecast QC/frame invalid')
        require(all(TEST_SOURCES.get(raw)==canonical for raw,canonical in zip(z['raw_source_id'],z['canonical_source_type'])),'source map mismatch')
        anchors=pd.to_datetime(z['anchor_timestamp'],utc=True);ts=pd.to_datetime(z['forecast_timestamps'].reshape(-1),utc=True).to_numpy().reshape(1320,15)
        expected=np.stack([(anchors+pd.Timedelta(minutes=i)).to_numpy() for i in range(1,16)],axis=1)
        require(np.array_equal(ts,expected),'forecast timestamps mismatch')
    for k in ('encounter_id','raw_source_id','canonical_source_type','vessel_ids','anchor_timestamp','forecast_timestamps','frame'):
        require(np.array_equal(arr['CV'][k],arr['M5a'][k]),'paired forecast mismatch '+k)
    scores=pd.read_parquet(p/'risk_scores.parquet');ids=arr['CV']['encounter_id']
    require(len(scores)==2640 and set(scores.model_id)=={'CV','M5a'},'score count/model mismatch')
    model_scores={}
    for name in ('CV','M5a'):
        g=scores[scores.model_id==name].set_index('encounter_id',verify_integrity=True)
        require(set(g.index)==set(ids),'score coverage mismatch');g=g.loc[ids]
        require(np.array_equal(g.raw_source_id.to_numpy(),arr[name]['raw_source_id']) and np.array_equal(g.canonical_source_type.to_numpy(),arr[name]['canonical_source_type']),'score source mismatch')
        require(np.isfinite(g.cc_dri).all() and g.cc_dri.between(0,1).all() and g.qc_status.eq('PASS').all(),'invalid score/QC')
        require(g.threshold.eq(POINTS[name]).all() and np.array_equal(g.decision.to_numpy(),(g.cc_dri>=POINTS[name]).to_numpy()),'threshold/decision mismatch')
        model_scores[name]=g.cc_dri.to_numpy(dtype=np.float64)
    return {'manifest_sha256':expected_manifest,'checksums_verified':len(checks),'supplement_checksums_verified':len(supplement_checks),'encounters':len(ids),'forecast_shape':[1320,2,15,2],'models':['CV','M5a'],'forecast_scoring_reuse':'PASS','fallback':False},arr,model_scores


def validate_authorization(record,spec,spec_sha):
    common={'scope':'R2_EVALUATION_REPLAY_ONLY','parent_run_id':PARENT,'parent_manifest_sha256':PARENT_MANIFEST,'lock_id':LOCK_ID,'lock_manifest_sha256':LOCK_SHA,'package_sha256':PAYLOAD_SHA,'dataset_lock_sha256':DATASET_LOCK,'dataset_manifest_sha256':DATASET_MANIFEST,'r2_protocol_sha256':PROTOCOL,'thresholds':POINTS,'cv_inference':False,'m5a_inference':False,'risk_scoring':False,'training':False,'threshold_selection':False}
    require(all(spec.get(k)==v and record.get(k)==v for k,v in common.items()),'replay scope/identity mismatch')
    require(record.get('approval')=='TRUNG_EVALUATION_ONLY_REPLAY' and record.get('authorization_id') and record.get('spec_sha256')==spec_sha,'missing approval or specification mismatch')
    require(spec.get('allowed_reads')==READS,'unexpected authorized reads')
    require(isinstance(spec.get('source_hashes'),dict) and bool(spec['source_hashes']) and record.get('source_hashes')==spec['source_hashes'],'source binding mismatch')
    for rel,sha in spec['source_hashes'].items():
        path=(ROOT/rel).resolve();require(path.is_relative_to(ROOT) and digest(path)==sha,'replay source mismatch')


def run(*,parent,package,dataset,out,authorization,authorization_sha,specification,spec_sha,evidence,evidence_sha):
    p=Path(parent).resolve();out=Path(out).resolve();ds=Path(dataset).resolve();pkg=Path(package).resolve()
    require(out.is_dir() and not out.is_relative_to(ds) and not out.is_relative_to(pkg) and not out.is_relative_to(p),'unsafe output path')
    record=_read_pinned_json(authorization,authorization_sha);spec=_read_pinned_json(specification,spec_sha);proof=_read_pinned_json(evidence,evidence_sha)
    validate_authorization(record,spec,spec_sha)
    require(proof.get('full_regression') is True and proof.get('targeted') is True and proof.get('q1_no_test_deserialization') is True,'regression proof missing')
    for rel,sha in proof['source_hashes'].items():require(digest(ROOT/rel)==sha,'source changed after testing')
    for file,sha in proof['test_evidence_files'].items():require(digest(Path(file))==sha,'regression evidence tampered')
    require(digest(ROOT/'configs/t15_execution_protocol_r2.json')==PROTOCOL,'R2 protocol changed')
    lock=verify_active(pkg,LOCK_SHA);require(lock['lock_id']==LOCK_ID and lock['package_identity']==PAYLOAD_SHA,'lock mismatch')
    with _pre_gate_test_guard(ds) as guard:
        loader=DatasetLoader(ds);require(digest(ds/'DATASET_LOCK_MANIFEST.json')==DATASET_LOCK,'dataset lock mismatch');dataset_checksum=checksum_dataset(ds,loader.lock)
    require(dataset_checksum.get('files_verified')==93 and dataset_checksum.get('manifest_sha256')==DATASET_MANIFEST and not guard['blocked_deserialization'] and not guard['blocked_other_opens'],'dataset verification failed')
    reuse,forecasts,scores=verify_parent(p)
    require(spec.get('parent_artifacts')=={n:digest(p/n) for n in spec.get('parent_artifacts',{})} and set(spec.get('parent_artifacts',{}))=={'cv_predictions.npz','m5a_predictions.npz','risk_scores.parquet'},'artifact pins mismatch')
    write(out/'parent_r2_reuse_verification.json',reuse)
    gate={'status':'PASS','parent':PARENT,'authorization_sha256':authorization_sha,'specification_sha256':spec_sha,'evidence_sha256':evidence_sha,'dataset':dataset_checksum,'guard':guard,'reuse':reuse,'pre_gate_test_semantic_access':False,'inference_authorized':False,'risk_scoring_authorized':False}
    gate_path=out/'pre_access_gate_report.json';write(gate_path,gate);write(out/'gate_pin.json',{'sha256':digest(gate_path)})
    identity={'run_id':out.name,'authorization_id':record['authorization_id'],'protocol_sha256':spec_sha};log=out/'test_access_events.jsonl'
    event(log,identity,'AUTHORIZATION_CHECKED','authorization','verified gate persisted')
    labels=audited_read(log,identity,'labels','numpy load without mmap',lambda:np.load(ds/READS['labels'],allow_pickle=False))
    target=audited_read(log,identity,'target','numpy load without mmap',lambda:np.load(ds/READS['target'],allow_pickle=False))
    index=audited_read(log,identity,'index','pandas csv deserialization',lambda:pd.read_csv(ds/READS['index']))
    cols=['encounter_id','vessel','relative_minute','is_future','LAT','LON','timestamp_utc','anchor_timestamp']
    future=audited_read(log,identity,'future','pandas parquet future-column deserialization',lambda:pd.read_parquet(ds/READS['future'],columns=cols,filters=[('is_future','==',True)]))
    result=evaluate(p,forecasts,scores,labels,target,index,future)
    for filename,value in result['outputs'].items():write(out/filename,value)
    event(log,identity,'EVALUATION_COMPLETED','evaluation','all comparisons completed')
    summary=event_summary(log);require(all(summary[k]==['ATTEMPTED','OBSERVED'] for k in READS),'incomplete evaluation access log')
    write(out/'evaluation_access_audit.json',{'status':'PASS','events_by_category':summary,'gate_sha256':digest(gate_path),'limitation':'Python-level call-path logging is not an OS sandbox; ndarray loads use mmap_mode=None.'})
    write(out/'evaluation_replay_manifest.json',{'run_id':out.name,'parent':PARENT,'parent_manifest_sha256':PARENT_MANIFEST,'authorization_id':record['authorization_id'],'spec_sha256':spec_sha,'gate_sha256':digest(gate_path),'reproduction':result['comparison']['status'],'cv_inference':False,'m5a_inference':False,'risk_scoring':False})
    files=sorted(x for x in out.iterdir() if x.is_file() and x.name!='checksums.sha256')
    (out/'checksums.sha256').write_text(''.join(digest(x)+'  '+x.name+'\n' for x in files),encoding='utf8')
    return result['comparison']


def evaluate(parent, forecasts, scores, labels, target, index, future):
    ids=forecasts['CV']['encounter_id'];raw=forecasts['CV']['raw_source_id'];src=forecasts['CV']['canonical_source_type'];n=len(ids)
    require(np.array_equal(index.encounter_id.astype(str).to_numpy(),ids) and np.array_equal(index.high_risk_label.to_numpy(),labels),'index/label mismatch')
    require(labels.shape==(n,) and np.isin(labels,[0,1]).all() and target.shape==(n,2,15,2) and np.isfinite(target).all(),'evaluation arrays invalid')
    order=pd.DataFrame({'encounter_id':np.repeat(ids,2),'vessel':np.tile(['A','B'],n),'row':np.arange(2*n)})
    future=future.merge(order,on=['encounter_id','vessel'],validate='many_to_one').sort_values(['row','relative_minute'])
    require(len(future)==n*30 and future.is_future.all() and np.array_equal(future.row,np.repeat(np.arange(2*n),15)) and np.array_equal(future.relative_minute,np.tile(np.arange(1,16),2*n)),'future coverage mismatch')
    require((future.timestamp_utc==future.anchor_timestamp+pd.to_timedelta(future.relative_minute,unit='min')).all(),'future timestamp mismatch')
    coords=future[['LAT','LON']].to_numpy(dtype=np.float64).reshape(n,2,15,2);lat=np.deg2rad(coords[:,:,:,0]);lon=np.deg2rad(coords[:,:,:,1]);hv=np.sin((lat[:,0]-lat[:,1])/2)**2+np.cos(lat[:,0])*np.cos(lat[:,1])*np.sin((lon[:,0]-lon[:,1])/2)**2;distance=(6880.13*np.arcsin(np.sqrt(np.clip(hv,0,1)))).min(axis=1)
    close=(src=='SYNTHETIC_AIS')&(labels==1)&(distance<.1);meta=pd.read_parquet(parent/'evaluation_metadata.parquet')
    require(np.array_equal(meta.encounter_id.to_numpy(),ids) and np.array_equal(meta.label.to_numpy(),labels) and np.array_equal(meta.raw_source_id.to_numpy(),raw) and np.array_equal(meta.canonical_source_type.to_numpy(),src) and np.array_equal(meta.close_positive.to_numpy(),close),'evaluation membership mismatch')
    require(np.array_equal(meta.minimum_future_haversine_nm.to_numpy(),distance),'future distance mismatch')
    metrics=[];d1={};decisions={};paired=pd.read_parquet(parent/'paired_encounter_outcomes.parquet')
    require(np.array_equal(paired.encounter_id.to_numpy(),ids),'paired encounter order mismatch')
    for name,k in [('CV',87),('M5a',84)]:
        err=np.linalg.norm(forecasts[name]['coordinates_nm']-target,axis=-1);ade=err.mean(axis=(1,2),dtype=np.float64);fde=err[:,:,-1].mean(axis=1,dtype=np.float64)
        require(np.array_equal(meta[name+'_ade_nm'].to_numpy(),ade) and np.array_equal(meta[name+'_fde_nm'].to_numpy(),fde),'trajectory metric mismatch')
        score=scores[name];pred=score>=k/200;decisions[name]=pred
        require(np.array_equal(paired[name+'_score'].to_numpy(),score) and np.array_equal(paired[name+'_decision'].to_numpy(),pred),'score/decision mismatch')
        row=describe_candidate(candidate(labels,src,close,score,k));d1[name]={'status':'D1_PASS' if row['feasible'] else ('D1_INCONCLUSIVE' if any(row[x]!='VALID_SUPPORT' for x in ['overall_recall_support','real_fpr_support','synthetic_recall_support','close_recall_support','f1_support']) else 'D1_FAIL'),'fixed_threshold':k/200,'grid_index':k,'candidate':row}
        for group,mask in [('overall',np.ones(n,dtype=bool)),('YANG_LEI',src=='YANG_LEI'),('REAL_AIS',src=='REAL_AIS'),('SYNTHETIC_AIS',src=='SYNTHETIC_AIS'),('close_positive',close)]:
            item={'model':name,'group':group,'count':int(mask.sum()),'positive':int((labels[mask]==1).sum()),'negative':int((labels[mask]==0).sum()),'roc_auc':score_metric(labels[mask],score[mask],'roc_auc'),'average_precision':score_metric(labels[mask],score[mask],'average_precision'),'operating_point':conditional_metrics(labels[mask],pred[mask])}
            for kind,vals in [('ade',ade),('fde',fde)]:
                z=vals[mask];item[kind]={'value':float(z.mean()) if len(z) else None,'support':'VALID_SUPPORT' if len(z)>=30 else ('LOW_SUPPORT' if len(z) else 'NA'),'unit':'nm'}
            metrics.append(item)
    historical_metrics=json.loads((parent/'performance_metrics.json').read_text());historical_d1=json.loads((parent/'fixed_threshold_d1_results.json').read_text());historical_d2=json.loads((parent/'fixed_threshold_d2_results.json').read_text())
    require(metrics==historical_metrics and d1==historical_d1,'metric or D1 reproduction mismatch')
    require(d1['M5a']['status']=='D1_FAIL' and historical_d2=={'status':'D2_FAIL','reason':'M5a fixed-threshold D1 failed'},'D2 reproduction mismatch')
    cv=set(ids[close & ~decisions['CV']]);m=set(ids[close & ~decisions['M5a']]);supplement=json.loads((parent.parent/'s4_t15_r2_reporting_supplement_20261125/d2_comparison_supplement.json').read_text())
    require(sorted(cv)==supplement['cv_close_misses'] and sorted(m)==supplement['m5a_close_misses'] and sorted(m-cv)==supplement['new_close_misses'],'close-positive IDs mismatch')
    comparison={'status':'PASS','encounters':n,'metrics_exact':True,'d1_exact':True,'d2_exact':True,'decisions_exact':True,'close_positive_ids_exact':True,'close_positive_count':int(close.sum()),'cv_close_missed_ids':sorted(cv),'m5a_close_missed_ids':sorted(m),'m5a_new_close_misses':sorted(m-cv),'mismatches':[]}
    return {'comparison':comparison,'outputs':{'reproduced_performance_metrics.json':metrics,'reproduced_d1_results.json':d1,'reproduced_d2_results.json':historical_d2,'r2_reproduction_comparison.json':comparison}}
