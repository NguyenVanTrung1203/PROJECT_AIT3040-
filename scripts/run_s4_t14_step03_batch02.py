"""Validation-only D1/D2 evaluation from the verified Batch 01 handoff."""
import argparse, hashlib, json, os, platform, subprocess, sys, traceback, uuid
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score
from src.protocol.calibration_primitives import CountMetrics, select_candidate, subgroup_recall, metric_support, comparison_gates, ade_gate, close_positive_comparison, evaluate_d2
from src.protocol.calibration_protocol import load_protocol,semantic_sha256
from scripts.run_s4_t14_step03_batch01 import verify_reuse,verify_output,digest,require

PARENT='s4_t14_batch01_20261125T025749Z_fbf7f18e'
SOURCE={'yanglei':'YANG_LEI','real_ais_kattegat_v3':'REAL_AIS','augmented_real_ais_kattegat_v3':'SYNTHETIC_AIS'}

def json_write(path,obj):path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')
def frac(x):return {'numerator':x.numerator,'denominator':x.denominator,'value':float(x)} if x is not None else None

def validate_input(meta,risk,strict=True):
    require(meta.encounter_id.notna().all() and meta.encounter_id.is_unique and risk.encounter_id.notna().all(),'duplicate/missing encounter')
    require(not risk.duplicated(['encounter_id','model_id']).any() and set(risk.model_id)=={'CV','M5a'},'duplicate/missing model score')
    require(meta.source.isin(SOURCE).all() and meta.label.isin([0,1]).all() and meta.dependency_group_id.notna().all() and meta.dependency_group_id.astype(str).str.strip().ne('').all(),'invalid metadata')
    require(((meta.source!='real_ais_kattegat_v3')|(meta.label==0)).all() and ((meta.source!='augmented_real_ais_kattegat_v3')|(meta.label==1)).all(),'source/label mismatch')
    require(meta.close_positive.isin([True,False]).all() and (~meta.close_positive | ((meta.label==1)&(meta.source=='augmented_real_ais_kattegat_v3'))).all(),'close-positive mismatch')
    frames={};ids=set(meta.encounter_id.astype(str))
    for model in ('CV','M5a'):
        r=risk[risk.model_id==model]
        require(len(r)==len(meta) and set(r.encounter_id.astype(str))==ids,'score encounter mismatch')
        joined=meta.merge(r[['encounter_id','source','cc_dri','scoring_implementation','qc_status']],on='encounter_id',how='left',validate='one_to_one',suffixes=('','_risk'))
        require(joined.source.eq(joined.source_risk).all(),'score/source mismatch')
        require(joined.qc_status.eq('PASS').all() and joined.scoring_implementation.eq('original_and_packaged_exact').all(),'QC or score provenance mismatch')
        require(joined.cc_dri.dtype==np.float64 and np.isfinite(joined.cc_dri).all() and joined.cc_dri.between(0,1).all(),'score invalid')
        for col in ('CV_ade_nm','CV_fde_nm','M5a_ade_nm','M5a_fde_nm'):
            require(joined[col].dtype==np.float64 and np.isfinite(joined[col]).all() and joined[col].ge(0).all(),'trajectory metric invalid')
        frames[model]=joined
    if strict:
        require(len(meta)==835 and int((meta.label==1).sum())==425 and int((meta.label==0).sum())==410 and int(meta.close_positive.sum())==60,'unexpected support')
        require(meta.source.value_counts().to_dict()=={'augmented_real_ais_kattegat_v3':300,'real_ais_kattegat_v3':295,'yanglei':240},'source count mismatch')
        sizes=meta.dependency_group_id.value_counts();require(len(sizes)==260 and sizes.iloc[0]==556,'group mismatch')
    return frames

def counts(y,p):return CountMetrics(int(np.sum((y==1)&p)),int(np.sum((y==0)&p)),int(np.sum((y==1)&~p)),int(np.sum((y==0)&~p)))
def candidate(y,src,close,score,k,severe=0):
    p=score>=k/200; c=counts(y,p);real=counts(y[src=='REAL_AIS'],p[src=='REAL_AIS']);syn=counts(y[src=='SYNTHETIC_AIS'],p[src=='SYNTHETIC_AIS']);cc=counts(y[close],p[close])
    return {'k':k,'overall':c,'real':real,'synthetic_tp_fn':(syn.tp,syn.fn),'close_tp_fn':(cc.tp,cc.fn),'severe_qc':severe}

def describe_candidate(c):
    overall=c['overall'];real=c['real'];syn=c['synthetic_tp_fn'];close=c['close_tp_fn']
    states={'overall_recall':overall.support('recall'),'f1':overall.support('f1'),'real_fpr':real.support('fpr'),'synthetic_recall':subgroup_recall(*syn,30),'close_recall':subgroup_recall(*close,10)}
    gates={'overall_recall':states['overall_recall'][0]=='VALID_SUPPORT' and states['overall_recall'][1]>=Fraction(9,10),
       'real_fpr':states['real_fpr'][0]=='VALID_SUPPORT' and states['real_fpr'][1]<=Fraction(3,25),
       'synthetic_recall':states['synthetic_recall'][0]=='VALID_SUPPORT' and states['synthetic_recall'][1]>=Fraction(9,10),
       'close_recall':states['close_recall'][0]=='VALID_SUPPORT' and states['close_recall'][1]>=Fraction(19,20),
       'f1_support':states['f1'][0]=='VALID_SUPPORT','severe_qc':c['severe_qc']==0}
    row={'grid_index':c['k'],'threshold':c['k']/200,'tp':overall.tp,'fp':overall.fp,'fn':overall.fn,'tn':overall.tn,'real_fp':real.fp,'real_tn':real.tn,'synthetic_tp':syn[0],'synthetic_fn':syn[1],'close_tp':close[0],'close_fn':close[1],'predicted_positive':overall.tp+overall.fp,'severe_qc':c['severe_qc'],'feasible':all(gates.values()),'violated_gates':','.join(k for k,v in gates.items() if not v)}
    for metric in ('recall','fpr','precision','f1'):
        state,value=overall.support(metric);row[metric]=float(value) if value is not None else None;row[metric+'_support']=state;row[metric+'_fraction']=str(value) if value is not None else None
    for name,sv in states.items():
        row[name]=float(sv[1]) if sv[1] is not None else None;row[name+'_support']=sv[0];row[name+'_fraction']=str(sv[1]) if sv[1] is not None else None
    for gate,passed in gates.items():row['gate_'+gate]=passed
    return row

def grid(y,src,close,score,severe=0):
    candidates=[candidate(y,src,close,score,k,severe) for k in range(201)]
    selected=select_candidate(candidates);rows=[describe_candidate(x) for x in candidates]
    require(select_candidate(list(reversed(candidates)))==selected,'selection order dependent')
    feasible=[r for r in rows if r['feasible']];require((selected is None)==(not feasible),'feasibility/selection mismatch')
    return candidates,rows,selected

def infeasibility_diagnostics(rows):
    # Descriptive Pareto front only; never selects an operating point.
    keys=('overall_recall','synthetic_recall','close_recall','f1')
    valid=[r for r in rows if all(r[k] is not None for k in (*keys,'real_fpr'))]
    vectors={r['grid_index']:tuple(Fraction(r[k+'_fraction']) for k in keys)+(-Fraction(r['real_fpr_fraction']),) for r in valid}
    front=[]
    for r in valid:
        v=vectors[r['grid_index']]
        if not any(all(a>=b for a,b in zip(w,v)) and any(a>b for a,b in zip(w,v)) for w in vectors.values()):front.append(r['grid_index'])
    minimum=min((len(r['violated_gates'].split(',')) for r in rows if r['violated_gates']),default=None)
    return {'pareto_grid_indices':front,'minimum_violated_gate_count':minimum,'diagnostic_only':True}

def score_metric(y,score,name):
    pos=int((y==1).sum());neg=int((y==0).sum());defined=(pos>0 and (neg>0 or name=='average_precision'))
    support=metric_support(name,positive=pos,negative=neg,mathematical_defined=defined)
    value=(roc_auc_score(y,score) if name=='roc_auc' else average_precision_score(y,score)) if defined else None
    return {'value':float(value) if value is not None else None,'support':support,'positive':pos,'negative':neg,'implementation':'sklearn.metrics.'+('roc_auc_score' if name=='roc_auc' else 'average_precision_score')}

def conditional_metrics(y,p):
    c=counts(y,p);out={}
    for name in ('recall','fpr','precision','f1'):
        st,val=c.support(name);out[name]={'value':float(val) if val is not None else None,'support':st,'fraction':str(val) if val is not None else None}
    out.update({'tp':c.tp,'fp':c.fp,'fn':c.fn,'tn':c.tn,'accuracy':(c.tp+c.tn)/len(y) if len(y) else None,'specificity':c.tn/(c.fp+c.tn) if c.fp+c.tn else None})
    return out

def d2_eval(cs,ms,ca,ma,cr,mr,close,cvdet,mdet,severe=0):
    if ms is None:return {'status':'D2_FAIL','reason':'M5a has no feasible D1 threshold','gates':{}}
    if cs is None:return {'status':'D2_CONDITIONAL','reason':'CV has no feasible D1 threshold','gates':{}}
    cm,mm=cs['overall'],ms['overall'];r_c,r_m=cs['real'],ms['real']
    delta={name: mm.ratio(name)-cm.ratio(name) for name in ('recall','f1')};delta['real_fpr']=r_m.ratio('fpr')-r_c.ratio('fpr')
    cp=close_positive_comparison(close,cvdet,mdet)
    gates={'m5a_d1':'PASS','recall_delta':'PASS' if delta['recall']>=Fraction(-1,100) else 'FAIL','real_fpr_delta':'PASS' if delta['real_fpr']<=Fraction(1,100) else 'FAIL','f1_delta':'PASS' if delta['f1']>=Fraction(-1,100) else 'FAIL','overall_ade':ade_gate(ma,ca),'real_ade':ade_gate(mr,cr),'new_close_misses':cp['status'],'severe_qc':'PASS' if severe==0 else 'FAIL'}
    status=evaluate_d2(m5a_d1='D1_PASS',cv_d1='D1_PASS',m5a_counts=mm,cv_counts=cm,m5a_real=r_m,cv_real=r_c,overall_ade_m5a=ma,overall_ade_cv=ca,real_ade_m5a=mr,real_ade_cv=cr,overall_encounters=cm.tp+cm.fp+cm.tn+cm.fn,real_encounters=r_c.fp+r_c.tn,close_ids=close,cv_detected=cvdet,m5a_detected=mdet,severe=severe)
    return {'status':status,'gates':gates,'deltas':{k:frac(v) for k,v in delta.items()},'overall_ade_cv':float(ca),'overall_ade_m5a':float(ma),'overall_ade_ratio':float(ma/ca) if ca else None,'real_ade_cv':float(cr),'real_ade_m5a':float(mr),'real_ade_ratio':float(mr/cr) if cr else None,'close':{k:sorted(v) if isinstance(v,set) else v for k,v in cp.items()}}

def main_run(parent,dataset,artifacts,original,outroot):
    parent=Path(parent).resolve();require(parent.name==PARENT,'unexpected parent run')
    os.environ['DATASET_ROOT']=str(Path(dataset).resolve());import scripts.q1_test_access_guard as guard;guard.pytest_sessionstart(None)
    require(verify_output(parent)==8 and verify_reuse(parent,dataset,artifacts,original),'BATCH01_ARTIFACT_REUSE_BLOCKED')
    pmanifest=json.loads((parent/'run_manifest.json').read_text(encoding='utf8'));status=json.loads((parent/'run_status.json').read_text(encoding='utf8'));parity=json.loads((parent/'parity.json').read_text(encoding='utf8'));qc=json.loads((parent/'qc_summary.json').read_text(encoding='utf8'))
    require(status['status']=='PASS' and all(v['severe_encounters']==v['severe_vessels']==0 for v in qc.values()),'parent QC failure')
    for fields in [parity['roles'],*parity['models'].values()]:require(all(v['mismatches']==0 for v in fields.values()),'parent parity failure')
    protocol=load_protocol(ROOT/'configs/s4_calibration_protocol.yaml');require(semantic_sha256(protocol)==pmanifest['protocol_semantic_sha256'],'protocol mismatch')
    meta=pd.read_parquet(parent/'evaluation_metadata.parquet');risk=pd.read_parquet(parent/'risk_scores.parquet');frames=validate_input(meta,risk)
    rid='s4_t14_batch02_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8];out=Path(outroot)/rid;out.mkdir(parents=True,exist_ok=False)
    try:
        y=meta.label.to_numpy();src=meta.source.map(SOURCE).to_numpy();close=meta.close_positive.to_numpy(); ids=meta.encounter_id.astype(str).to_numpy(); model={};grids={};metrics=[];pred={};d1={}
        for name in ('CV','M5a'):
            score=frames[name].cc_dri.to_numpy(dtype=np.float64);candidates,rows,k=grid(y,src,close,score);grids[name]=pd.DataFrame(rows);grids[name].insert(0,'model_id',name);grids[name].to_parquet(out/(name.lower()+'_threshold_grid.parquet'),index=False)
            selected=candidates[k] if k is not None else None;model[name]={'score':score,'candidates':candidates,'k':k,'selected':selected};pred[name]=score>=k/200 if k is not None else None
            feasible=[r for r in rows if r['feasible']];viol=Counter(v for r in rows for v in r['violated_gates'].split(',') if v);combinations=Counter(r['violated_gates'] for r in rows if r['violated_gates'])
            d1[name]={'status':'D1_PASS' if k is not None else 'NO_FEASIBLE_THRESHOLD','candidates':201,'feasible_candidates':len(feasible),'selected_grid_index':k,'selected_threshold':k/200 if k is not None else None,'selected':rows[k] if k is not None else None,'tie_break':'maximum exact F1, minimum exact Real AIS FPR, maximum exact recall, minimum grid index','iteration_order_invariant':True,'violations':dict(viol),'violation_combinations':dict(combinations),'infeasibility_diagnostics':infeasibility_diagnostics(rows) if k is None else None}
            for group,mask in [('overall',np.ones(len(y),dtype=bool)),('YANG_LEI',src=='YANG_LEI'),('REAL_AIS',src=='REAL_AIS'),('SYNTHETIC_AIS',src=='SYNTHETIC_AIS'),('close_positive',close)]:
                record={'model':name,'group':group,'count':int(mask.sum()),'positive':int((y[mask]==1).sum()),'negative':int((y[mask]==0).sum())}
                record['roc_auc']=score_metric(y[mask],score[mask],'roc_auc');record['average_precision']=score_metric(y[mask],score[mask],'average_precision')
                record['operating_point']=conditional_metrics(y[mask],pred[name][mask]) if k is not None else None
                for kind in ('ade','fde'):
                    values=meta[name+'_'+kind+'_nm'].to_numpy(dtype=np.float64)[mask];record[kind]={'value':float(values.mean(dtype=np.float64)) if len(values) else None,'support':metric_support('overall_'+kind if group=='overall' else 'source_'+kind,subset=len(values)),'unit':'nm'}
                metrics.append(record)
        if model['CV']['k'] is not None and model['M5a']['k'] is not None:
            cvdet=list(ids[close & pred['CV']]);mdet=list(ids[close & pred['M5a']]);real=src=='REAL_AIS'
            d2=d2_eval(model['CV']['selected'],model['M5a']['selected'],meta.CV_ade_nm.mean(),meta.M5a_ade_nm.mean(),meta.CV_ade_nm[real].mean(),meta.M5a_ade_nm[real].mean(),list(ids[close]),cvdet,mdet)
        else:d2=d2_eval(model['CV']['selected'],model['M5a']['selected'],None,None,None,None,[],[],[])
        paired=meta.copy();analysis={'paired':{},'real_false_alarm':{},'close':d2.get('close',{}),'score_distribution':{},'near_threshold':{}}
        for name in ('CV','M5a'):
            score=model[name]['score'];k=model[name]['k'];paired[name+'_score']=score;paired[name+'_decision']=pred[name];paired[name+'_margin']=score-k/200 if k is not None else np.nan
            analysis['score_distribution'][name]={}
            for label,mask in [('overall',np.ones(len(y),bool)),('positive',y==1),('negative',y==0),('yang',src=='YANG_LEI'),('real',src=='REAL_AIS'),('synthetic',src=='SYNTHETIC_AIS')]:
                x=score[mask];analysis['score_distribution'][name][label]={'n':len(x),'min':float(x.min()),'max':float(x.max()),'mean':float(x.mean()),'median':float(np.median(x)),'std_population':float(x.std()),'p05_p25_p75_p95':np.percentile(x,[5,25,75,95]).tolist()}
            if k is not None:
                order=np.argsort(np.abs(score-k/200),kind='stable');analysis['near_threshold'][name]={'within_5e_5_count':int((np.abs(score-k/200)<=5e-5).sum()),'nearest_20':[{'encounter_id':str(ids[i]),'score':float(score[i]),'margin':float(score[i]-k/200)} for i in order[:20]]}
        if all(pred[x] is not None for x in ('CV','M5a')):
            c=pred['CV'];m=pred['M5a'];cats=np.select([(y==1)&c&m,(y==1)&~c&~m,(y==1)&~c&m,(y==1)&c&~m,(y==0)&~c&~m,(y==0)&c&m,(y==0)&c&~m,(y==0)&~c&m],['positive_both_detected','positive_both_missed','positive_m5a_improved','positive_m5a_new_miss','negative_both_rejected','negative_both_false_alarm','negative_m5a_improved','negative_m5a_new_false_alarm'],default='INVALID');require(not np.any(cats=='INVALID'),'invalid paired category');paired['paired_outcome']=cats
            for cat in sorted(set(cats)):
                mask=cats==cat;analysis['paired'][cat]={'count':int(mask.sum()),'ids':ids[mask].tolist(),'source_counts':pd.Series(src[mask]).value_counts().to_dict()}
            real=src=='REAL_AIS'
            for label,mask in [('cv_false_positive',real&c),('m5a_false_positive',real&m),('shared',real&c&m),('eliminated_by_m5a',real&c&~m),('introduced_by_m5a',real&~c&m)]:
                analysis['real_false_alarm'][label]={'count':int(mask.sum()),'ids':ids[mask].tolist(),'score_deltas':{str(ids[i]):float(model['M5a']['score'][i]-model['CV']['score'][i]) for i in np.flatnonzero(mask)}}
        else:paired['paired_outcome']='NOT_COMPARABLE'
        paired.to_parquet(out/'paired_encounter_outcomes.parquet',index=False);json_write(out/'d1_calibration_results.json',d1);json_write(out/'d2_comparative_results.json',d2);json_write(out/'performance_metrics.json',metrics);json_write(out/'error_analysis.json',analysis)
        payload=['cv_threshold_grid.parquet','m5a_threshold_grid.parquet','d1_calibration_results.json','d2_comparative_results.json','performance_metrics.json','paired_encounter_outcomes.parquet','error_analysis.json']
        import torch,joblib,sklearn,pyarrow
        manifest={'run_id':rid,'created_utc':datetime.now(timezone.utc).isoformat(),'parent_run_id':PARENT,'parent_manifest_sha256':digest(parent/'run_manifest.json'),'parent_checksums_sha256':digest(parent/'checksums.sha256'),'parent_input_sha256':{name:digest(parent/name) for name in ['risk_scores.parquet','evaluation_metadata.parquet','cv_predictions.npz','m5a_predictions.npz','parity.json','qc_summary.json']},'protocol_semantic_sha256':semantic_sha256(protocol),'protocol_raw_sha256':digest(ROOT/'configs/s4_calibration_protocol.yaml'),'dataset_manifest_sha256':pmanifest['dataset_manifest_sha256'],'dataset_lock_sha256':pmanifest['dataset_lock_sha256'],'dependency_manifest_sha256':pmanifest['dependency_manifest_sha256'],'model_artifact_manifest_sha256':pmanifest['artifact_manifest_sha256'],'model_artifacts':pmanifest['artifacts'],'risk_reference_sha256':pmanifest['risk_original_sha256'],'source_sha256':{**pmanifest['source_sha256'],**{x:digest(ROOT/x) for x in ['scripts/run_s4_t14_step03_batch02.py','src/protocol/calibration_primitives.py','src/protocol/clustered_bootstrap.py']}},'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'environment':{'device':'cpu','python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'torch':torch.__version__,'joblib':joblib.__version__,'scikit_learn':sklearn.__version__,'pyarrow':pyarrow.__version__},'output_sha256':{p:digest(out/p) for p in payload},'limitations':['IN_SAMPLE_CALIBRATION','independent evaluation not performed','dependency provenance PARTIAL; grouping CONDITIONAL','MMSI ownership NOT_VERIFIED','clean environment NOT_VERIFIED','V1 baseline review required'],'test_access_guard':guard.counters}
        json_write(out/'run_manifest.json',manifest);json_write(out/'run_status.json',{'status':'PASS','scope':'validation','parent':PARENT,'d2_status':d2['status'],'model_lock':False,'test_benchmark':False})
        names=payload+['run_manifest.json','run_status.json'];(out/'checksums.sha256').write_text(''.join(digest(out/p)+'  '+p+'\n' for p in names),encoding='utf8');require(verify_output(out)==len(names),'output checksum failure')
        print(json.dumps({'directory':str(out),'d1':d1,'d2':d2,'test_guard':guard.counters},ensure_ascii=False),flush=True)
    except Exception as exc:
        json_write(out/'run_status.json',{'status':'FAILED','error':str(exc),'traceback':traceback.format_exc()});raise
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scope',required=True,choices=['validation']);p.add_argument('--parent',required=True);p.add_argument('--dataset-root',required=True);p.add_argument('--artifact-dir',required=True);p.add_argument('--original-v4',required=True);p.add_argument('--output-root',required=True);a=p.parse_args();main_run(a.parent,a.dataset_root,a.artifact_dir,a.original_v4,a.output_root)
if __name__=='__main__':main()
