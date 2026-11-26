"""Read-only enrichment of saved D4 attempts; uses same sampled group plan."""
import gzip,json,sys
from collections import Counter
from fractions import Fraction
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_s4_t14_step03_batch03 import P1,create_data
from scripts.run_s4_t14_step03_batch02 import conditional_metrics
from src.protocol import clustered_bootstrap as cb
from src.protocol.calibration_primitives import ade_gate
out=Path(r'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\s4_t14_batch03_runs\s4_t14_batch03_20261125T033810Z')
meta=pd.read_parquet(P1/'evaluation_metadata.parquet');risk=pd.read_parquet(P1/'risk_scores.parquet');data=create_data(meta,risk)
with np.load(out/'d4_resample_plan.npz',allow_pickle=False) as p: groups=p['groups'];draws=p['draws']
with gzip.open(out/'d4_l2_attempts.jsonl.gz','rt',encoding='utf8') as f:details=[json.loads(line) for line in f]
assert len(details)==len(draws)==5000
reasons=Counter();combos=Counter();entries=[]
for i,d in enumerate(details):
    if d['status']!='OK':reasons['EXECUTION_ERROR']+=1;continue
    ck,mk=d['cv_threshold_index'],d['m5a_threshold_index']
    if ck is None or mk is None:
        label='both_infeasible' if ck is None and mk is None else ('cv_only_feasible' if ck is not None else 'm5a_only_feasible');reasons[label]+=1;continue
    idx=cb._indices(data.groups,tuple(groups[draws[i]].tolist()));c=cb._candidate(data,idx,'cv',ck);m=cb._candidate(data,idx,'m5a',mk)
    drec=m['overall'].ratio('recall')-c['overall'].ratio('recall');dfpr=m['real'].ratio('fpr')-c['real'].ratio('fpr');df1=m['overall'].ratio('f1')-c['overall'].ratio('f1')
    src=np.asarray(data.source)[idx];real=src=='REAL_AIS';ca=np.asarray(data.cv_ade)[idx];ma=np.asarray(data.m5a_ade)[idx];cl=np.asarray(data.close)[idx];cv=np.asarray(data.cv_score)[idx]>=ck/200;mm=np.asarray(data.m5a_score)[idx]>=mk/200
    flags={'recall_delta':drec>=Fraction(-1,100),'real_fpr_delta':dfpr<=Fraction(1,100),'f1_delta':df1>=Fraction(-1,100),'overall_ade':ade_gate(ma.mean(),ca.mean())=='D2_PASS','real_ade':ade_gate(ma[real].mean(),ca[real].mean())=='D2_PASS','new_close_misses':not bool(np.any(cl&cv&~mm)),'severe_qc':m['severe_qc']==0}
    failed=[k for k,v in flags.items() if not v]
    for k in failed:reasons[k]+=1
    if failed:combos[','.join(failed)]+=1
    entries.append({'attempt':i,'failed_gates':failed,'status':d['d2']})
    if ('D2_FAIL' if failed else 'D2_PASS')!=d['d2']:raise ValueError('D2 gate mismatch attempt '+str(i))
summary=json.loads((out/'d4_l2_summary.json').read_text())['stability'];distributions={}
for n in ('cv','m5a'):
    indices=np.array(summary[n+'_thresholds']);values=indices/200
    distributions[n]={'denominator':len(indices),'min':float(values.min()),'median':float(np.median(values)),'max':float(values.max()),'percentiles_2_5_25_75_97_5':np.percentile(values,[2.5,25,75,97.5]).tolist(),'frequency':{str(int(k)):int(v) for k,v in zip(*np.unique(indices,return_counts=True))},'full_validation_index':87 if n=='cv' else 84}
result={'attempts':5000,'both_feasible':summary['both_feasible'],'d2_evaluable':summary['d2_comparable'],'d2_counts':summary['d2_counts'],'gate_failure_counts':dict(reasons),'failure_combinations':dict(combos),'threshold_distributions':distributions,'paired_plan_sha256':__import__('hashlib').sha256((out/'d4_resample_plan.npz').read_bytes()).hexdigest()}
(out/'d4_l2_stability_details.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
with gzip.open(out/'d4_l2_gate_results.jsonl.gz','wt',encoding='utf8') as f:
 for d in entries:f.write(json.dumps(d)+'\n')
l3=json.loads((out/'d4_l3_sensitivity.json').read_text());ids=np.asarray(data.ids);allgroups=np.asarray(data.groups)
for name,item in l3['subsets'].items():
    index=np.flatnonzero(np.isin(ids,item['encounter_ids']));y=np.asarray(data.labels)[index];src=np.asarray(data.source)[index];close=np.asarray(data.close)[index]
    item['classification']={}
    for model,k in [('cv',87),('m5a',84)]:
        pred=np.asarray(getattr(data,model+'_score'))[index]>=k/200
        item['classification'][model]={}
        for group,mask in [('overall',np.ones(len(y),dtype=bool)),('REAL_AIS',src=='REAL_AIS'),('SYNTHETIC_AIS',src=='SYNTHETIC_AIS'),('YANG_LEI',src=='YANG_LEI'),('close_positive',close)]:
            item['classification'][model][group]=conditional_metrics(y[mask],pred[mask])
    item['overall_ade_ratio']=item['m5a']['ade'][1]/item['cv']['ade'][1]
(out/'d4_l3_sensitivity_enriched.json').write_text(json.dumps(l3,indent=2,allow_nan=False)+'\n',encoding='utf8')
print(json.dumps(result),flush=True)
