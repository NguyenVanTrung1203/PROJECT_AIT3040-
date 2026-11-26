"""Add descriptive paired/rounding summaries to an existing diagnostic directory."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(directory,dataset_root,old_prediction=None):
    p=Path(directory).resolve(); root=Path(__file__).resolve().parents[1]
    if not p.is_relative_to((root/'artifacts/checkpoints').resolve()) or not p.name.startswith('s3_post_t10_risk_comparison_'):
        raise ValueError('invalid diagnostic directory')
    for line in (p/'checksums.sha256').read_text(encoding='utf8').splitlines():
        h,n=line.split('  ',1)
        if Path(n).name!=n or digest(p/n)!=h:raise ValueError('diagnostic hash mismatch')
    additions=['alert_transitions.csv','score_distributions.csv','rounding_sensitivity.csv','near_threshold_cases.csv','dependency_audit.json']
    if any((p/n).exists() for n in additions):raise ValueError('supplement already exists; refusing overwrite')
    data=pd.read_csv(p/'risk_scores_by_encounter.csv'); meta=json.loads((p/'risk_comparison_metrics.json').read_text(encoding='utf8'))['summary'];tc=meta['cv']['threshold'];tm=meta['m5a']['threshold']
    transition=data.groupby(['source','label','cv_pred','m5a_pred'],dropna=False).size().rename('count').reset_index();transition.to_csv(p/'alert_transitions.csv',index=False)
    dist=[]
    for source,g in [('Overall',data)]+list(data.groupby('source')):
        for label,group in g.groupby('label'):
            for method,col in [('CV','cv_score'),('M5a','m5a_score')]:
                x=group[col];q=x.quantile([.1,.25,.5,.75,.9]);dist.append({'source':source,'label':int(label),'method':method,'n':len(x),'mean':x.mean(),'std':x.std(ddof=1) if len(x)>1 else None,'min':x.min(),'p10':q.loc[.1],'p25':q.loc[.25],'median':q.loc[.5],'p75':q.loc[.75],'p90':q.loc[.9],'max':x.max()})
    pd.DataFrame(dist).to_csv(p/'score_distributions.csv',index=False)
    rounds=[]
    for method,col,t in [('CV','cv_score',tc),('M5a','m5a_score',tm)]:
        for digits in (3,4,5,6):rounds.append({'method':method,'threshold':t,'round_digits':digits,'decision_changes':int(((data[col]>=t)!=(data[col].round(digits)>=t)).sum())})
    pd.DataFrame(rounds).to_csv(p/'rounding_sensitivity.csv',index=False)
    near=data[(data.cv_threshold_margin.abs()<=.005)|(data.m5a_threshold_margin.abs()<=.005)].copy();near['nearest_abs_margin']=np.minimum(near.cv_threshold_margin.abs(),near.m5a_threshold_margin.abs());near.sort_values('nearest_abs_margin').to_csv(p/'near_threshold_cases.csv',index=False)
    f=pd.read_parquet(Path(dataset_root)/'validation/data/validation_835.parquet',columns=['encounter_id','vessel','MMSI','data_source','parent_encounter_id','relative_minute'],filters=[('relative_minute','=',0)])
    real=f[(f.data_source=='real_ais_kattegat_v3')&f.MMSI.notna()];by=real.groupby('MMSI').encounter_id.nunique();parents=f[['encounter_id','parent_encounter_id']].drop_duplicates().dropna().groupby('parent_encounter_id').encounter_id.nunique()
    dep={'validation_dependency_groups':meta['groups'],'largest_group_encounters':meta['largest_group_encounters'],'largest_group_share':meta['largest_group_encounters']/len(data),'real_ais_mmsi_nonmissing_rows':len(real),'real_ais_unique_mmsi':len(by),'real_ais_mmsi_in_multiple_encounters':int((by>1).sum()),'max_real_encounters_per_mmsi':int(by.max()) if len(by) else None,'nonmissing_parent_links':int(parents.sum()),'parent_ids':len(parents),'parent_ids_multiple_encounters':int((parents>1).sum()),'limitations':'Dependency groups are connected components; the very large component yields unstable clustered resamples. Missing source identifiers may hide additional dependencies.'}
    if old_prediction:
        from src.data.dataset_loader import DatasetLoader
        loader=DatasetLoader(dataset_root);s=loader.load_split('validation')
        old=np.load(old_prediction,allow_pickle=False); saved=np.load(root/'artifacts/checkpoints/s3_t10_20261124_seed20261110_run01/validation_predictions.npz',allow_pickle=False)['prediction_common_EN_nm'][s.pairs]
        if not np.array_equal(s.pairs,np.arange(len(s.X)).reshape(-1,2)) or old.shape!=saved.shape:raise ValueError('historical prediction mapping not independently aligned')
        dep['historical_v3_validation_prediction_sha256']=digest(old_prediction);dep['historical_prediction_hash_authenticated']=False
        dep['historical_vs_t10_max_abs_forecast_difference_nm']=float(np.max(np.abs(old-saved)));dep['historical_vs_t10_mean_abs_forecast_difference_nm']=float(np.mean(np.abs(old-saved)))
    (p/'dependency_audit.json').write_text(json.dumps(dep,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
    allfiles=sorted(q for q in p.iterdir() if q.is_file() and q.name!='checksums.sha256');(p/'checksums.sha256').write_text(''.join(digest(q)+'  '+q.name+'\n' for q in allfiles),encoding='utf8')
    print(json.dumps(dep,indent=2,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--directory',required=True);a.add_argument('--dataset-root',required=True);a.add_argument('--old-prediction');b=a.parse_args();run(b.directory,b.dataset_root,b.old_prediction)
