"""Compare verified Batch 03 CPU/CUDA offline artifacts without Test or inference."""
import json,sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_s4_t14_step03_batch01 import verify_output,require,digest
B=Path(r'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2')
P=B/'s4_t14_batch01_runs/s4_t14_batch01_20261125T025749Z_fbf7f18e'
C=B/'s4_t14_batch03_runs/device_cpu/s4_t14_batch01_20261125T033609Z_0ff080dc'
G=B/'s4_t14_batch03_runs/device_cuda/s4_t14_batch01_20261125T033609Z_913ecdaf'
O=B/'s4_t14_batch03_runs/d5_comparison_20261125T033609Z'

def read(p):
    require(verify_output(p)==8,'device artifact checksum mismatch')
    m=json.loads((p/'run_manifest.json').read_text(encoding='utf8'));status=json.loads((p/'run_status.json').read_text(encoding='utf8'))
    require(status['status']=='PASS' and status['qc']['CV']['severe_vessels']==status['qc']['M5a']['severe_vessels']==0,'device QC failure')
    for n,h in m['source_sha256'].items():require(digest(ROOT/n)==h,'source mismatch '+n)
    with np.load(p/'m5a_predictions.npz',allow_pickle=False) as z:forecast={k:z[k] for k in z.files}
    with np.load(p/'cv_predictions.npz',allow_pickle=False) as z:cv={k:z[k] for k in z.files}
    return m,status,forecast,cv,pd.read_parquet(p/'risk_scores.parquet'),pd.read_parquet(p/'evaluation_metadata.parquet')

def summarize(a):
    return {'max':float(np.max(a)),'mean':float(np.mean(a)),'median':float(np.median(a)),'p95':float(np.percentile(a,95)),'p99':float(np.percentile(a,99)),'count':int(a.size)}

def gates_ok(coordinate,ade,fde,risk,vessels,mismatches,cv_equal,ref_forecast,ref_score,ref_decision):
    return bool(coordinate<=5e-5 and vessels==0 and ade<=1e-6 and fde<=1e-6 and risk<=5e-5 and mismatches==0 and cv_equal and ref_forecast and ref_score and ref_decision)

def compare():
    O.mkdir(parents=True,exist_ok=False)
    pm,ps,p,p_cv,pr,pe=read(P);cm,cs,c,c_cv,cr,ce=read(C);gm,gs,g,g_cv,gr,ge=read(G)
    require(cm['environment']['device']=='cpu' and gm['environment']['device']=='cuda','wrong device')
    for key in ('protocol_semantic_sha256','dataset_manifest_sha256','dataset_lock_sha256','artifact_manifest_sha256','risk_packaged_sha256','source_sha256'):
        require(pm[key]==cm[key]==gm[key],'source/config/model mismatch '+key)
    for key in ('encounter_id','source','vessel_ids','anchor_timestamp','forecast_timestamps','frame','qc_status'):
        require(np.array_equal(p[key],c[key]) and np.array_equal(p[key],g[key]),'semantic identity mismatch '+key)
    require(c['coordinates_nm'].shape==g['coordinates_nm'].shape==(835,2,15,2) and np.isfinite(c['coordinates_nm']).all() and np.isfinite(g['coordinates_nm']).all(),'forecast shape or finite failure')
    coords=np.abs(c['coordinates_nm']-g['coordinates_nm']);exceed=coords>5e-5;vessel=exceed.any(axis=(2,3)); ids=c['encounter_id'];affected=[{'encounter_id':str(ids[i]),'vessel_id':str(c['vessel_ids'][i,j])} for i,j in np.argwhere(vessel)]
    require(ce.encounter_id.astype(str).tolist()==ge.encounter_id.astype(str).tolist()==pe.encounter_id.astype(str).tolist()==ids.astype(str).tolist(),'evaluation pairing mismatch')
    ade={};fde={}
    for n,mask in [('overall',np.ones(len(ce),bool)),('YANG_LEI',ce.source=='yanglei'),('REAL_AIS',ce.source=='real_ais_kattegat_v3'),('SYNTHETIC_AIS',ce.source=='augmented_real_ais_kattegat_v3')]:
        ade[n]={'cpu':float(ce.loc[mask,'M5a_ade_nm'].mean()),'cuda':float(ge.loc[mask,'M5a_ade_nm'].mean())};ade[n]['absolute_difference']=abs(ade[n]['cpu']-ade[n]['cuda'])
        fde[n]={'cpu':float(ce.loc[mask,'M5a_fde_nm'].mean()),'cuda':float(ge.loc[mask,'M5a_fde_nm'].mean())};fde[n]['absolute_difference']=abs(fde[n]['cpu']-fde[n]['cuda'])
    scores={};riskframes={}
    for name,r in [('cpu',cr),('cuda',gr),('parent',pr)]:
        z=r[r.model_id=='M5a'].set_index('encounter_id').loc[ids.astype(str)];require(z.index.is_unique and z.qc_status.eq('PASS').all(),'risk pairing/QC failure');scores[name]=z.cc_dri.to_numpy(dtype=np.float64);riskframes[name]=z
    require(all(np.isfinite(v).all() for v in scores.values()),'nonfinite scores')
    delta=np.abs(scores['cpu']-scores['cuda']);d_cpu=scores['cpu']>=.42;d_gpu=scores['cuda']>=.42;bad=np.flatnonzero(d_cpu!=d_gpu);y=ce.label.to_numpy()
    def confusion(pred):return {'tp':int(((y==1)&pred).sum()),'fp':int(((y==0)&pred).sum()),'tn':int(((y==0)&~pred).sum()),'fn':int(((y==1)&~pred).sum())}
    near={}
    for name,v in scores.items():
        i=int(np.argmin(np.abs(v-.42)));near[name]={'encounter_id':str(ids[i]),'score':float(v[i]),'margin':float(v[i]-.42),'within_5e_5':int((np.abs(v-.42)<=5e-5).sum())}
    component={}
    for col in ('current_dcpa_nm','current_tcpa_min','predicted_dcpa_nm','predicted_tcpa_min','rule','current_cpa_risk','predicted_cpa_risk'):
        component[col]=summarize(np.abs(riskframes['cpu'][col].to_numpy()-riskframes['cuda'][col].to_numpy()))
    for col in ('role','scene','source','qc_status'):require(riskframes['cpu'][col].equals(riskframes['cuda'][col]),'risk semantic mismatch '+col)
    cv_scores=[]
    for r in (pr,cr,gr):cv_scores.append(r[r.model_id=='CV'].set_index('encounter_id').loc[ids.astype(str)].cc_dri.to_numpy())
    cv_equal=all(np.array_equal(cv_scores[0],x) for x in cv_scores[1:]) and np.array_equal(p_cv['coordinates_nm'],c_cv['coordinates_nm']) and np.array_equal(p_cv['coordinates_nm'],g_cv['coordinates_nm'])
    cv_i=int(np.argmin(np.abs(cv_scores[0]-.435)));near['cv']={'encounter_id':str(ids[cv_i]),'score':float(cv_scores[0][cv_i]),'margin':float(cv_scores[0][cv_i]-.435),'within_5e_5':int((np.abs(cv_scores[0]-.435)<=5e-5).sum())}
    ref_forecast=np.array_equal(p['coordinates_nm'],g['coordinates_nm']);ref_score=np.array_equal(scores['parent'],scores['cuda']);ref_decision=np.array_equal(scores['parent']>=.42,d_gpu)
    passed=gates_ok(coords.max(),ade['overall']['absolute_difference'],fde['overall']['absolute_difference'],delta.max(),int(vessel.sum()),len(bad),cv_equal,ref_forecast,ref_score,ref_decision)
    result={'status':'D5_PASS' if passed else 'D5_REVIEW_REQUIRED','device_runs':{'cpu':str(C),'cuda':str(G),'parent':str(P)},'environment_cpu':cm['environment'],'environment_cuda':gm['environment'],'semantic_parity':'PASS','coordinate_abs_nm':summarize(coords),'coordinate_values_above_tolerance':int(exceed.sum()),'vessels_above_tolerance':int(vessel.sum()),'affected_vessels':affected,'ade':ade,'fde':fde,'score_abs':summarize(delta),'score_nonfinite':0,'component_abs':component,'m5a_decisions':{'matched':int((d_cpu==d_gpu).sum()),'mismatched':int(len(bad)),'cpu_positive':int(d_cpu.sum()),'cuda_positive':int(d_gpu.sum()),'cpu_confusion':confusion(d_cpu),'cuda_confusion':confusion(d_gpu),'mismatches':[{'encounter_id':str(ids[i]),'cpu_score':float(scores['cpu'][i]),'cuda_score':float(scores['cuda'][i]),'difference':float(scores['cuda'][i]-scores['cpu'][i]),'cpu_margin':float(scores['cpu'][i]-.42),'cuda_margin':float(scores['cuda'][i]-.42)} for i in bad]},'near_threshold':near,'cv_reference_cpu_path_exact':cv_equal,'cuda_reference':{'forecast_exact':ref_forecast,'score_exact':ref_score,'decision_exact':ref_decision,'forecast_max_abs':float(np.max(np.abs(p['coordinates_nm']-g['coordinates_nm']))),'score_max_abs':float(np.max(np.abs(scores['parent']-scores['cuda'])))},'severe_qc':{'cpu':cs['qc'],'cuda':gs['qc']}}
    out=O/'d5_parity_results.json';out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf8');(O/'checksums.sha256').write_text(digest(out)+'  '+out.name+'\n',encoding='utf8');print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':compare()
