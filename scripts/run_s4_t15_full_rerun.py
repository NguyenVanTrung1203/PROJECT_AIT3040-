"""Full audited T15 rerun; no Test access before all pinned gates pass."""
import argparse
import json
import os
import sys
import traceback
import uuid
import platform
import time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from src.evaluation.t15_authorization import TASK,LOCK_SHA,PAYLOAD_SHA,run_gated
from src.evaluation.t15_full_authorization import validate_pins
from src.evaluation.t15_full_access_audit import Audit,supported_path_guard
from src.evaluation.t15_full_data_boundary import read_inputs
from src.evaluation.t15_full_benchmark import evaluate_loaded
from src.release.offline_lock import digest,verify_active


def write(path,value):
    with Path(path).open('x',encoding='utf8') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())


def verify_r2(parent):
    if parent.name!='s4_t15_r2_20261125T152141Z_2cd800cd' or digest(parent/'run_manifest.json')!='8ba0913490dd8f56fc5f445e43e16dbb7a254a9dd4818861db1d0ecdbf160a15':raise ValueError('wrong parent')
    manifest=json.loads((parent/'run_manifest.json').read_text());checks={}
    for line in (parent/'checksums.sha256').read_text().splitlines():
        sha,name=line.split('  ',1)
        if Path(name).name!=name or name in checks or digest(parent/name)!=sha:raise ValueError('parent checksum mismatch')
        checks[name]=sha
    if len(checks)!=29 or any(checks.get(name)!=sha for name,sha in manifest['output_sha256'].items()):raise ValueError('parent checksum inventory mismatch')
    sup=parent.parent/'s4_t15_r2_reporting_supplement_20261125';lines=(sup/'checksums.sha256').read_text().splitlines()
    if len(lines)!=5:raise ValueError('supplement checksum inventory mismatch')
    for line in lines:
        sha,name=line.split('  ',1)
        if Path(name).name!=name or digest(sup/name)!=sha:raise ValueError('supplement checksum mismatch')
    return {'run_files_verified':len(checks),'supplement_files_verified':len(lines)}


def compare_r2(out,parent):
    problems=[];summary={}
    for name in ('cv_predictions.npz','m5a_predictions.npz'):
        with np.load(out/name,allow_pickle=False) as a,np.load(parent/name,allow_pickle=False) as b:
            bad=[k for k in set(a.files)|set(b.files) if k not in a.files or k not in b.files or not np.array_equal(a[k],b[k])]
            detail={}
            if 'coordinates_nm' in bad and a['coordinates_nm'].shape==b['coordinates_nm'].shape:
                delta=np.abs(a['coordinates_nm']-b['coordinates_nm']);mask=np.any(delta!=0,axis=(1,2,3));indices=np.flatnonzero(mask)
                detail={'max_absolute_difference':float(np.max(delta)),'affected_count':len(indices),'affected_ids':a['encounter_id'][indices].tolist()}
        summary[name]={'exact':not bad,'mismatched_fields':bad,'detail':detail};problems.extend(name+':'+k for k in bad)
    a=pd.read_parquet(out/'risk_scores.parquet');b=pd.read_parquet(parent/'risk_scores.parquet')
    score_exact=a.equals(b);summary['risk_scores_exact']=score_exact
    if not score_exact:problems.append('risk_scores')
    for name in ('performance_metrics.json','fixed_threshold_d1_results.json','fixed_threshold_d2_results.json','dataset_distribution.json'):
        same=json.loads((out/name).read_text())==json.loads((parent/name).read_text());summary[name+'_exact']=same
        if not same:problems.append(name)
    summary['status']='PASS' if not problems else 'FAIL';summary['mismatches']=problems
    return summary


def run(a):
    started=time.perf_counter();start_utc=datetime.now(timezone.utc).isoformat()
    out=Path(a.run_dir).resolve();pkg=Path(a.package).resolve();dataset=Path(a.dataset_root).resolve();parent=Path(a.parent_r2).resolve()
    if not out.is_dir() or out.is_relative_to(pkg) or out.is_relative_to(dataset) or out.is_relative_to(parent):raise ValueError('unsafe output')
    record,protocol,evidence=validate_pins(record_path=a.authorization,record_sha=a.authorization_sha,protocol_path=a.protocol,protocol_sha=a.protocol_sha,evidence_path=a.pre_access_evidence,evidence_sha=a.pre_access_evidence_sha,inventory_path=a.inventory,inventory_sha=a.inventory_sha)
    parent_integrity=verify_r2(parent)
    source_lock=verify_active(pkg,LOCK_SHA)
    for name,sha in source_lock['worktree_source_hashes'].items():
        if digest(ROOT/name)!=sha:raise RuntimeError('locked worktree source differs: '+name)
    audit=Audit(out/'test_access_events.jsonl',out.name,record['authorization_id'],a.protocol_sha)
    def loader(ctx):
        audit.emit('authorization','authorization','AUTHORIZATION_VERIFIED',uuid.uuid4().hex,detail='durable pre-access gate report and pin exist')
        return read_inputs(ctx,audit)
    try:
        with supported_path_guard(dataset) as path_guard:
            loaded,gate,gate_sha=run_gated(report_path=out/'pre_access_gate_report.json',loader=loader,authorization_path=a.authorization,expected_authorization_sha256=a.authorization_sha,protocol_path=a.protocol,expected_protocol_sha256=a.protocol_sha,package_root=pkg,expected_lock_sha256=LOCK_SHA,dataset_root=dataset,task_id=TASK,split='test',pre_access_evidence_path=a.pre_access_evidence,expected_pre_access_evidence_sha256=a.pre_access_evidence_sha)
            result=evaluate_loaded(loaded,out,pkg/'snapshot/artifacts/checkpoints/s3_t10_20261124_seed20261110_run01')
        if path_guard['denied']:raise RuntimeError('unauthorized Test path attempted')
        comparison=compare_r2(out,parent);write(out/'r2_reproduction_comparison.json',comparison)
        if comparison['status']!='PASS':raise RuntimeError('R2 reproduction mismatch')
        lock=verify_active(pkg,LOCK_SHA)
        if lock['package_identity']!=PAYLOAD_SHA:raise RuntimeError('package changed')
        for name,sha in source_lock['worktree_source_hashes'].items():
            if digest(ROOT/name)!=sha:raise RuntimeError('locked worktree source changed: '+name)
        if verify_r2(parent)!=parent_integrity:raise RuntimeError('historical evidence changed')
        for name,sha in evidence['source_hashes'].items():
            if digest(ROOT/name)!=sha:raise RuntimeError('source changed after regression')
        metrics=json.loads((out/'performance_metrics.json').read_text());write(out/'source_metrics.json',[x for x in metrics if x['group'] in ('YANG_LEI','REAL_AIS','SYNTHETIC_AIS')]);write(out/'trajectory_metrics.json',[{'model':x['model'],'group':x['group'],'ade':x['ade'],'fde':x['fde']} for x in metrics])
        write(out/'t15_slide_metrics.json',{'dataset':result['distribution'],'classification':'REUSED_DEVELOPMENT_BENCHMARK','metrics':metrics,'d1':{k:v['status'] for k,v in result['d1'].items()},'d2':result['d2'],'benchmark':result['benchmark'],'latency':result['latency'],'limitations':['not independent external validation','clean environment not verified','production not approved']})
        import torch
        manifest={'run_id':out.name,'started_utc':start_utc,'manifest_created_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds_to_manifest':time.perf_counter()-started,'parent_r2':parent.name,'historical_integrity':parent_integrity,'gate_sha256':gate_sha,'protocol_sha256':a.protocol_sha,'authorization_id':record['authorization_id'],'lock_sha256':LOCK_SHA,'package_sha256':PAYLOAD_SHA,'source_hashes':evidence['source_hashes'],'reproduction':comparison,'benchmark':result['benchmark'],'access_audit':'PASS','environment':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},'production_approved':False}
        write(out/'run_manifest.json',manifest)
        files=sorted(p for p in out.iterdir() if p.is_file() and p.name!='checksums.sha256');(out/'checksums.sha256').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in files),encoding='utf8')
        for line in (out/'checksums.sha256').read_text(encoding='utf8').splitlines():
            sha,name=line.split('  ',1)
            if digest(out/name)!=sha:raise RuntimeError('artifact checksum mismatch')
        print(json.dumps({'status':'COMPLETE','run_dir':str(out),'result':result,'reproduction':comparison,'files':len(files)},ensure_ascii=False))
    except Exception as exc:
        failure={'status':'FAILED','error_type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc()}
        if not (out/'run_failure.json').exists():write(out/'run_failure.json',failure)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('run-dir','package','dataset-root','parent-r2','authorization','authorization-sha','protocol','protocol-sha','pre-access-evidence','pre-access-evidence-sha','inventory','inventory-sha'):p.add_argument('--'+name,required=True)
    run(p.parse_args())


if __name__=='__main__':main()
