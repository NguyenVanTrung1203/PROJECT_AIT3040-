"""Finalize and checksum existing Batch 03 evidence after regression."""
import hashlib,json,platform,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,pandas as pd,torch,joblib,sklearn,pyarrow
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_s4_t14_step03_batch01 import verify_output,digest,require
from scripts.run_s4_t14_step03_batch03 import P1,P2,verify_parents
B=Path(r'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2')
OUT=B/'s4_t14_batch03_runs/s4_t14_batch03_20261125T033810Z'
D5=B/'s4_t14_batch03_runs/d5_comparison_verified_20261125T033609Z'

def read(name):return json.loads((OUT/name).read_text(encoding='utf8'))
def write(name,x):(OUT/name).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')
def run():
    require(not (OUT/'checksums.sha256').exists(),'refusing overwrite')
    import os
    os.environ['DATASET_ROOT']=r'C:\Users\MSI\Desktop\PROJECT_AIT3040\DATASET_FINAL'
    import scripts.q1_test_access_guard as guard
    guard.pytest_sessionstart(None);parent=verify_parents()
    d3=read('d3_group_assignment.json');l1=read('d4_l1_summary.json');l2=read('d4_l2_summary.json');l3=read('d4_l3_sensitivity_enriched.json');status=read('d4_d3_status.json');extra=read('d4_l2_stability_details.json');eq=read('selector_equivalence.json')
    require(verify_output(D5)==1,'D5 checksum mismatch');d5=json.loads((D5/'d5_parity_results.json').read_text(encoding='utf8'))
    require(d3['status']=='GROUPED_CV_INFEASIBLE' and bool(d3['structural_proof']),'D3 proof missing')
    require(l1['attempts']==l2['attempts']==5000 and status['l1_attempts']==status['l2_attempts']==5000,'attempt count mismatch')
    require(all(v['execution_error_count']==0 for v in l1['metrics'].values()) and all(v['execution_error_count']==0 for v in l2['metrics'].values()),'bootstrap errors')
    require(eq['status']=='PASS' and eq['comparisons']==64 and d5['status']=='D5_PASS','selector/D5 mismatch')
    require({k:v['encounters'] for k,v in l3['subsets'].items()}=={'S1':835,'S2':279,'S3':556},'sensitivity subsets invalid')
    (OUT/'d5_parity_results.json').write_bytes((D5/'d5_parity_results.json').read_bytes())
    analysis={'cv_d1_status':'D1_PASS','m5a_d1_status':'D1_PASS','d2_status':'D2_PASS','d3_status':d3['status'],'d4_status':'D4_EVIDENCE_LIMITED','d5_status':d5['status'],'batch03_execution_acceptance':'PASS','step03_analysis_complete':True,'model_quality_acceptance':'PASS_WITH_LIMITATIONS','ready_for_step04_review':'YES_WITH_LIMITATIONS','model_status':'CANDIDATE','model_lock':False,'production_approved':False,'test_benchmark':False,'limitations':['D3 structurally infeasible: largest group leaves 4 close-positive outside vs minimum 10','D4 L1 Real AIS FPR and close-positive insufficient support-qualified repetitions','dependency lineage/provenance PARTIAL and grouping CONDITIONAL','Validation reused for epoch and threshold selection; not independent','MMSI ownership and clean environment NOT_VERIFIED','V1 baseline review required'],'test_guard':guard.counters,'full_regression':'SEE_BATCH03_REPORT','fixed_thresholds':{'cv':.435,'m5a':.42}}
    write('step03_final_evaluation.json',analysis)
    payload=sorted(p.name for p in OUT.iterdir() if p.is_file() and p.name not in ('run_manifest.json','checksums.sha256'))
    source_names=['scripts/run_s4_t14_step03_batch03.py','scripts/summarize_s4_t14_batch03.py','scripts/analyze_s4_t14_d5.py','scripts/finalize_s4_t14_batch03.py','src/protocol/group_assignment.py','src/protocol/clustered_bootstrap.py','src/protocol/calibration_primitives.py','configs/s4_calibration_protocol.yaml']
    manifest={'run_id':OUT.name,'created_utc':datetime.now(timezone.utc).isoformat(),'parents':[{'run_id':p.name,'manifest_sha256':digest(p/'run_manifest.json'),'checksums_sha256':digest(p/'checksums.sha256')} for p in (P1,P2)],'d5_reference':{'directory':str(D5),'checksum_manifest_sha256':digest(D5/'checksums.sha256'),'cpu_dir':d5['device_runs']['cpu'],'cuda_dir':d5['device_runs']['cuda']},'protocol_semantic_sha256':parent['protocol_semantic_sha256'],'dataset_manifest_sha256':parent['dataset_manifest_sha256'],'dataset_lock_sha256':parent['dataset_lock_sha256'],'dependency_manifest_sha256':parent['dependency_manifest_sha256'],'artifact_manifest_sha256':parent['model_artifact_manifest_sha256'],'model_artifacts':parent['model_artifacts'],'risk_sha256':parent['risk_reference_sha256'],'parent_source_sha256':parent['source_sha256'],'batch03_source_sha256':{n:digest(ROOT/n) for n in source_names},'group_plan_sha256':digest(OUT/'d4_resample_plan.npz'),'group_assignment_sha256':digest(OUT/'d3_group_assignment.json'),'rng':'numpy.default_rng PCG64; canonical UTF8 group ordering','seed':20261124,'attempts':5000,'fixed_thresholds':{'cv':.435,'m5a':.42},'environment':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'torch':torch.__version__,'joblib':joblib.__version__,'sklearn':sklearn.__version__,'pyarrow':pyarrow.__version__},'outputs':{n:digest(OUT/n) for n in payload},'limitations':analysis['limitations']}
    write('run_manifest.json',manifest);allfiles=payload+['run_manifest.json'];(OUT/'checksums.sha256').write_text(''.join(digest(OUT/n)+'  '+n+'\n' for n in allfiles),encoding='utf8');require(verify_output(OUT)==len(allfiles),'output checksum failed')
    print('FINALIZED',OUT,'files',len(allfiles),'Q1',guard.counters,flush=True)
if __name__=='__main__':run()
