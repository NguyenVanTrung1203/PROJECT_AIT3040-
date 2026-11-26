"""Offline T14 Batch 03 D3 and D4; parent verification required, no Test decode."""
import gzip, json, os, sys, time, traceback
from collections import Counter
from datetime import datetime,timezone
from fractions import Fraction
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.protocol import clustered_bootstrap as cb
from src.protocol.group_assignment import assign_groups, FIELDS,MINIMUM
from scripts.run_s4_t14_step03_batch01 import verify_reuse,verify_output,digest,require
from scripts.run_s4_t14_step03_batch02 import validate_input,SOURCE
from src.protocol.calibration_protocol import load_protocol,semantic_sha256
B=Path(r'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2')
P1=B/'s4_t14_batch01_runs/s4_t14_batch01_20261125T025749Z_fbf7f18e'
P2=B/'s4_t14_batch02_runs/s4_t14_batch02_20261125T031911Z_cb53e739'
DATASET=Path(r'C:\Users\MSI\Desktop\PROJECT_AIT3040\DATASET_FINAL')
ART=ROOT/'artifacts/checkpoints/s3_t10_20261124_seed20261110_run01'
ORIGINAL=Path(r'C:\Users\MSI\Desktop\Môn học Dự án\MODEL_FINAL_VERIFICATION_V4\MODEL_CANDIDATE_PACKAGE\inference\risk_pipeline.py')

def dump(path,x):path.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')

def verify_parents():
    require(verify_output(P1)==8 and verify_reuse(P1,DATASET,ART,ORIGINAL),'PARENT_BATCH01_REUSE_BLOCKED')
    require(verify_output(P2)==9,'PARENT_BATCH02_REUSE_BLOCKED')
    m=json.loads((P2/'run_manifest.json').read_text(encoding='utf8'));s=json.loads((P2/'run_status.json').read_text(encoding='utf8'))
    require(s['status']=='PASS' and s['d2_status']=='D2_PASS' and m['parent_manifest_sha256']==digest(P1/'run_manifest.json') and m['parent_checksums_sha256']==digest(P1/'checksums.sha256'),'parent identity mismatch')
    for name,sha in m['source_sha256'].items():require(digest(ROOT/name)==sha,'source changed: '+name)
    for name,sha in m['parent_input_sha256'].items():require(digest(P1/name)==sha,'parent input changed: '+name)
    require(semantic_sha256(load_protocol(ROOT/'configs/s4_calibration_protocol.yaml'))==m['protocol_semantic_sha256'],'protocol mismatch')
    d=json.loads((P2/'d1_calibration_results.json').read_text(encoding='utf8'));require(d['CV']['status']==d['M5a']['status']=='D1_PASS' and d['CV']['selected_grid_index']==87 and d['M5a']['selected_grid_index']==84,'threshold mismatch')
    return m

def group_records(meta):
    records=[]
    for ident,t in meta.groupby('dependency_group_id',sort=True):
        records.append({'id':str(ident),'encounters':len(t),'positive':int((t.label==1).sum()),'negative':int((t.label==0).sum()),'real_negative':int((t.source=='real_ais_kattegat_v3').sum()),'synthetic_positive':int((t.source=='augmented_real_ais_kattegat_v3').sum()),'close_positive':int(t.close_positive.sum()),'yang_lei':int((t.source=='yanglei').sum())})
    return records

def d3_search(meta,out):
    records=group_records(meta);result=assign_groups(records);total={f:sum(x[f] for x in records) for f in FIELDS};largest=max(records,key=lambda x:x['encounters'])
    structural=[{'field':f,'outside_largest':total[f]-largest[f],'required_calibration_support':m} for f,m in zip(FIELDS,MINIMUM) if total[f]-largest[f]<m]
    if structural:
        result['status']='GROUPED_CV_INFEASIBLE';result['structural_proof']=structural;result['proof']='Every K>=2 keeps largest group in one held-out fold; its calibration complement has at most the outside-largest support.'
    result['largest_group']=largest;result['totals']=total;result['selection_uses_scores']=False;result['seed']=20261124
    dump(out/'d3_group_assignment.json',result)
    return result

# Exact histogram optimization for the existing bootstrap runner; comparator is
# evaluated on precisely the same float64 k/200 grid as original _candidate.
def make_fast_choose(data):
    y=np.asarray(data.labels);src=np.asarray(data.source);close=np.asarray(data.close);threshold=np.array([k/200 for k in range(201)],dtype=np.float64)
    bins={model:np.searchsorted(threshold,np.asarray(getattr(data,model+'_score')),side='right') for model in ('cv','m5a')}
    def choose(data,idx,model):
        yy=y[idx];ss=src[idx];cc=close[idx];n=len(idx);positive=int((yy==1).sum());negative=n-positive;real=(ss=='REAL_AIS');syn=(ss=='SYNTHETIC_AIS');rn=int(real.sum());sn=int(syn.sum());cn=int(cc.sum())
        if min(positive,negative,rn,sn)<30 or cn<10 or np.asarray(getattr(data,model+'_severe'))[idx].any():return None
        bb=bins[model][idx]
        def count(mask):
            hist=np.bincount(bb[mask],minlength=202);return np.cumsum(hist[::-1],dtype=np.int64)[::-1][1:202]
        tp=count(yy==1);fp=count(yy==0);rfp=count(real);stp=count(syn);ctp=count(cc)
        feasible=(tp*10>=9*positive)&(rfp*25<=3*rn)&(stp*10>=9*sn)&(ctp*20>=19*cn)
        choices=np.flatnonzero(feasible)
        if not len(choices):return None
        return int(max(choices,key=lambda k:(Fraction(int(2*tp[k]),int(positive+tp[k]+fp[k])),-Fraction(int(rfp[k]),rn),Fraction(int(tp[k]),positive),-int(k))))
    return choose

def check_fast_equivalence(data,fast):
    baseline=cb._choose;plan=cb.resample_plan(data.groups,repetitions=32,seed=20261124)
    for j,draw in enumerate(plan):
        idx=cb._indices(data.groups,draw)
        for model in ('cv','m5a'):
            a=baseline(data,idx,model);b=fast(data,idx,model)
            if a!=b:raise ValueError(f'optimized selector mismatch repetition {j} model {model}: {a} != {b}')
    return 64

def create_data(meta,risk):
    frames=validate_input(meta,risk); ids=tuple(meta.encounter_id.astype(str));y=tuple(meta.label.to_numpy());source=tuple(meta.source.map(SOURCE));close=tuple(meta.close_positive.to_numpy());groups=tuple(meta.dependency_group_id.astype(str));none=tuple(False for _ in ids)
    return cb.PairedData(ids,groups,y,source,close,ids,tuple(frames['CV'].cc_dri.to_numpy(dtype=np.float64)),tuple(meta.CV_ade_nm.to_numpy(dtype=np.float64)),tuple(meta.CV_fde_nm.to_numpy(dtype=np.float64)),none,ids,tuple(frames['M5a'].cc_dri.to_numpy(dtype=np.float64)),tuple(meta.M5a_ade_nm.to_numpy(dtype=np.float64)),tuple(meta.M5a_fde_nm.to_numpy(dtype=np.float64)),none)

def save_bootstrap(out,name,result):
    details=result.pop('details');dump(out/(name+'_summary.json'),result)
    with gzip.open(out/(name+'_attempts.jsonl.gz'),'wt',encoding='utf8') as f:
        for i,d in enumerate(details):
            d=dict(d);d.pop('draws',None);d.pop('sample_indices',None);d['attempt']=i;f.write(json.dumps(d,allow_nan=False)+'\n')
    return details

def l3(data,out):
    groups=np.asarray(data.groups);counter=Counter(groups);largest=max(counter,key=counter.get);sets={'S1':np.arange(len(groups)), 'S2':np.flatnonzero(groups!=largest),'S3':np.flatnonzero(groups==largest)};res={}
    for name,idx in sets.items():
        y=np.asarray(data.labels)[idx];src=np.asarray(data.source)[idx];close=np.asarray(data.close)[idx]
        cv=cb._metric_values(data,idx,'cv',87);m=cb._metric_values(data,idx,'m5a',84)
        res[name]={'encounters':len(idx),'groups':len(set(groups[idx])),'encounter_ids':np.asarray(data.ids)[idx].tolist(),'source_counts':dict(Counter(src)),'positive':int((y==1).sum()),'negative':int((y==0).sum()),'close_positive':int(close.sum()),'cv':cv,'m5a':m,'delta':{k:(m[k][1]-cv[k][1] if m[k][1] is not None and cv[k][1] is not None else None) for k in cb.METRICS},'fixed_thresholds':{'cv':0.435,'m5a':0.42}}
    dump(out/'d4_l3_sensitivity.json',{'largest_group':largest,'subsets':res});return res

def run():
    os.environ['DATASET_ROOT']=str(DATASET);import scripts.q1_test_access_guard as guard;guard.pytest_sessionstart(None)
    parent=verify_parents();rid='s4_t14_batch03_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=B/'s4_t14_batch03_runs'/rid;out.mkdir(parents=True,exist_ok=False)
    try:
        meta=pd.read_parquet(P1/'evaluation_metadata.parquet');result=d3_search(meta,out);print('D3',result['status'],'path',str(out),flush=True)
        risk=pd.read_parquet(P1/'risk_scores.parquet');data=create_data(meta,risk);cb.validate_data(data)
        plan=cb.resample_plan(data.groups);ordered=sorted(set(data.groups),key=lambda x:x.encode('utf8'));lookup={g:i for i,g in enumerate(ordered)}
        np.savez_compressed(out/'d4_resample_plan.npz',groups=np.array(ordered),draws=np.array([[lookup[g] for g in row] for row in plan],dtype=np.uint16));del plan
        fixed=cb.run_bootstrap(data,cv_threshold_index=87,m5a_threshold_index=84,mode='fixed');details=save_bootstrap(out,'d4_l1',fixed);print('D4_L1',len(details),'errors',sum(x['status']!='OK' for x in details),flush=True);del details
        fast=make_fast_choose(data);tests=check_fast_equivalence(data,fast);dump(out/'selector_equivalence.json',{'comparisons':tests,'actual_sample_plan':32,'models':2,'status':'PASS','method':'exact histograms and Fraction ties','seed':20261124});cb._choose=fast
        original_d2=cb._d2
        def corrected_d2(d,idx,ck,mk):
            if mk is None:return 'D2_BLOCKED'
            return original_d2(d,idx,ck,mk)
        cb._d2=corrected_d2
        print('D4_L2 starting exact histogram selector; D2 blocks M5a-infeasible samples',flush=True)
        stability=cb.run_bootstrap(data,cv_threshold_index=87,m5a_threshold_index=84,mode='stability');details=save_bootstrap(out,'d4_l2',stability);print('D4_L2',len(details),'errors',sum(x['status']!='OK' for x in details),flush=True);del details
        l3(data,out);dump(out/'d4_d3_status.json',{'d3':result['status'],'l1_attempts':5000,'l2_attempts':5000,'guard':guard.counters,'parent_protocol':parent['protocol_semantic_sha256']});print('D3_D4_COMPLETE',str(out),flush=True)
    except Exception as e:
        dump(out/'d3_d4_failure.json',{'error':str(e),'traceback':traceback.format_exc()});raise
if __name__=='__main__':run()
