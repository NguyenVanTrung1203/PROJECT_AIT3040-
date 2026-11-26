"""Execute one T15 benchmark only after pinned authorization and regression evidence."""
import argparse,hashlib,json,os,platform,subprocess,sys,time,traceback
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.release.offline_lock import verify_active,digest
from src.evaluation.t15_authorization import run_gated,TASK,LOCK_SHA,PAYLOAD_SHA
from src.evaluation.t15_trusted_test import load_authorized_test
from src.evaluation.t15_benchmark import evaluate_loaded


def write(path,x):Path(path).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')

def access_state(path, completed=False):
    """Derive status from durable events, including when a loader raises."""
    path=Path(path)
    if not path.exists():return 'NOT_ACCESSED'
    events=[json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]
    observed=any(e.get('state')=='SEMANTIC_ACCESS_OBSERVED' for e in events)
    attempted=any(e.get('state')=='SEMANTIC_ACCESS_ATTEMPTED' for e in events)
    if observed:return 'AUTHORIZED_ACCESS_COMPLETED' if completed else 'AUTHORIZED_ACCESS_FAILED_DURING_LOAD'
    return 'SEMANTIC_ACCESS_ATTEMPTED' if attempted else 'NOT_ACCESSED'

def run(args):
    out=Path(args.run_dir).resolve();package=Path(args.package).resolve();dataset=Path(args.dataset_root).resolve()
    if not out.is_dir() or out.is_relative_to(package) or out.is_relative_to(dataset):raise ValueError('run output must be outside package and dataset')
    lock=verify_active(package,LOCK_SHA)
    if lock['package_identity']!=PAYLOAD_SHA:raise ValueError('package identity mismatch')
    for name,expected in lock['worktree_source_hashes'].items():
        if digest(ROOT/name)!=expected:raise ValueError('locked worktree source differs: '+name)
    t0=time.perf_counter();status={'status':'STARTED','test_semantic_access':'NOT_ACCESSED','classification':'REUSED_DEVELOPMENT_BENCHMARK'};write(out/'run_status.json',status)
    try:
        loaded,report,gate_sha=run_gated(report_path=out/'pre_access_gate_report.json',loader=lambda ctx:load_authorized_test(ctx,out/'test_access_events.jsonl'),authorization_path=args.authorization,expected_authorization_sha256=args.authorization_sha,protocol_path=args.protocol,expected_protocol_sha256=args.protocol_sha,package_root=package,expected_lock_sha256=LOCK_SHA,dataset_root=dataset,task_id=TASK,split='test',pre_access_evidence_path=args.pre_access_evidence,expected_pre_access_evidence_sha256=args.pre_access_evidence_sha)
        status.update(test_semantic_access=access_state(out/'test_access_events.jsonl',True),first_authorized_test_read=next((e for e in loaded.access_audit if e.get('state')=='SEMANTIC_ACCESS_OBSERVED'),None));write(out/'run_status.json',status)
        result=evaluate_loaded(loaded,out,package/'snapshot/artifacts/checkpoints/s3_t10_20261124_seed20261110_run01')
        # T15 may not mutate the active lock, config or Contract.
        after=verify_active(package,LOCK_SHA)
        if after['package_identity']!=PAYLOAD_SHA:raise RuntimeError('lock changed after benchmark')
        for cmd in (['git','diff','--exit-code','HEAD','--','contracts','configs/risk_config.yaml'],['git','merge-base','--is-ancestor','99bdb2649f5aec39d67a6f64645bce4f7fc49a3d','HEAD']):subprocess.run(cmd,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
        for name,expected in lock['worktree_source_hashes'].items():
            if digest(ROOT/name)!=expected:raise RuntimeError('locked source changed after execution: '+name)
        pre=json.loads(Path(args.pre_access_evidence).read_text(encoding='utf8'))
        for name,expected in pre['source_hashes'].items():
            if digest(ROOT/name)!=expected:raise RuntimeError('T15 source changed after regression: '+name)
        payload=sorted(p.name for p in out.iterdir() if p.is_file() and p.name not in ('run_manifest.json','checksums.sha256','run_status.json'))
        validation_path=ROOT.parent.parent/'s4_t14_batch02_runs/s4_t14_batch02_20261125T031911Z_cb53e739/performance_metrics.json'
        # The parent path is explicitly supplied in the protocol evidence; never use Test to change it.
        base=Path(args.validation_reference);vmetrics=json.loads(base.read_text(encoding='utf8'));testmetrics=json.loads((out/'performance_metrics.json').read_text(encoding='utf8'))
        def overall(rows,model):return next(x for x in rows if x['group']=='overall' and x['model']==model)
        slide={'benchmark_classification':'REUSED_DEVELOPMENT_BENCHMARK','dataset':result['distribution'],'model':{'architecture':'Residual-GRU 4-48-96-30','parameters':15390},'thresholds':{'CV':.435,'M5a':.42,'comparator':'>='},'validation':{k:overall(vmetrics,k) for k in ('CV','M5a')},'test':{k:overall(testmetrics,k) for k in ('CV','M5a')},'benchmark_status':result['benchmark'],'limitations':['Test reused in development','Validation selected checkpoint and thresholds','not independent external validation','no production approval'],'regression':'pre-access full regression passed','latency':result['latency']};write(out/'t15_slide_metrics.json',slide)
        payload=sorted(p.name for p in out.iterdir() if p.is_file() and p.name not in ('run_manifest.json','checksums.sha256','run_status.json'))
        import numpy,pandas,torch,joblib,sklearn,pyarrow
        manifest={'run_id':out.name,'created_utc':datetime.now(timezone.utc).isoformat(),'authorization_sha256':args.authorization_sha,'pre_access_gate_sha256':gate_sha,'lock_id':lock['lock_id'],'lock_manifest_sha256':LOCK_SHA,'package_identity':PAYLOAD_SHA,'dataset':lock['dataset'],'protocol_sha256':args.protocol_sha,'checkpoint_sha256':lock['model']['checkpoint_sha256'],'risk_sha256':lock['risk_reference_sha256'],'t15_source_hashes':pre['source_hashes'],'locked_source_hashes':lock['worktree_source_hashes'],'execution_environment':{'python':platform.python_version(),'numpy':numpy.__version__,'pandas':pandas.__version__,'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,'joblib':joblib.__version__,'scikit_learn':sklearn.__version__,'pyarrow':pyarrow.__version__},'module_paths':{'M5aInference':str(Path(sys.modules['src.inference.m5a_wrapper'].__file__).resolve()),'RiskV4':str(Path(sys.modules['src.risk.reference_v4.risk_pipeline'].__file__).resolve())},'source_execution':'worktree files verified byte-identical to locked snapshot','thresholds':lock['operating_points'],'benchmark_status':result['benchmark'],'run_seconds':time.perf_counter()-t0,'limitations':['REUSED_DEVELOPMENT_BENCHMARK','not independent evaluation','clean environment NOT_VERIFIED','production not approved'],'output_sha256':{n:digest(out/n) for n in payload}}
        write(out/'run_manifest.json',manifest);status.update(status='PASS',benchmark=result['benchmark'],completed=True);write(out/'run_status.json',status)
        files=payload+['run_manifest.json','run_status.json'];(out/'checksums.sha256').write_text(''.join(digest(out/n)+'  '+n+'\n' for n in files),encoding='utf8')
        for line in (out/'checksums.sha256').read_text().splitlines():
            sha,name=line.split('  ',1)
            if digest(out/name)!=sha:raise RuntimeError('output checksum mismatch')
        print(json.dumps({'run_dir':str(out),'result':result,'output_count':len(files)},ensure_ascii=False),flush=True)
    except Exception as exc:
        current=access_state(out/'test_access_events.jsonl')
        if status.get('test_semantic_access')!='AUTHORIZED_ACCESS_COMPLETED':status['test_semantic_access']=current
        status.update(status='FAILED',error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc());write(out/'run_status.json',status);raise

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('run-dir','package','dataset-root','authorization','authorization-sha','protocol','protocol-sha','pre-access-evidence','pre-access-evidence-sha','validation-reference'):p.add_argument('--'+name,required=True)
    run(p.parse_args())
if __name__=='__main__':main()
