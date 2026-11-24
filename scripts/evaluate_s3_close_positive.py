"""Validation-only outcome subgroup; future is never passed to risk scoring."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data.dataset_loader import DatasetLoader


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(directory,dataset_root):
    p=Path(directory).resolve()
    if not p.is_relative_to((ROOT/'artifacts/checkpoints').resolve()) or not p.name.startswith('s3_post_t10_risk_comparison_'):raise ValueError('invalid diagnostic directory')
    for line in (p/'checksums.sha256').read_text(encoding='utf8').splitlines():
        h,n=line.split('  ',1)
        if Path(n).name!=n or digest(p/n)!=h:raise ValueError('diagnostic checksum mismatch')
    if (p/'close_positive_metrics.json').exists() or (p/'close_positive_cases.csv').exists():raise ValueError('refusing overwrite')
    l=DatasetLoader(dataset_root);s=l.load_split('validation'); src=l.root/'validation/data'/l.config['splits']['validation']['data']
    cols=['encounter_id','vessel','relative_minute','is_future','LAT','LON']
    df=pd.read_parquet(src,columns=cols,filters=[('is_future','=',True)])
    if not df.is_future.all() or not df.relative_minute.between(1,15).all():raise ValueError('invalid future-only outcome rows')
    df=df.merge(s.vessels[['encounter_id','vessel','X_row']],on=['encounter_id','vessel'],validate='many_to_one').sort_values(['X_row','relative_minute'])
    if len(df)!=1670*15 or not np.array_equal(df.X_row,np.repeat(np.arange(1670),15)) or not np.array_equal(df.relative_minute,np.tile(np.arange(1,16),1670)):raise ValueError('future evaluation mapping mismatch')
    coords=df[['LAT','LON']].to_numpy(dtype=np.float64).reshape(1670,15,2)[s.pairs]
    if not np.isfinite(coords).all():raise ValueError('invalid future coordinates')
    lat=np.deg2rad(coords[:,:,:,0]);lon=np.deg2rad(coords[:,:,:,1]);h=np.sin((lat[:,0]-lat[:,1])/2)**2+np.cos(lat[:,0])*np.cos(lat[:,1])*np.sin((lon[:,0]-lon[:,1])/2)**2
    d=(6880.13*np.arcsin(np.sqrt(np.clip(h,0,1)))).min(axis=1)
    score=pd.read_csv(p/'risk_scores_by_encounter.csv')
    if not np.array_equal(score.encounter_id.astype(str),s.encounters.encounter_id.astype(str)):raise ValueError('score outcome mapping mismatch')
    mask=(score.source=='augmented_real_ais_kattegat_v3')&(d<.1)
    if not (score.loc[mask,'label']==1).all() or mask.sum()==0:raise ValueError('invalid close-positive subgroup')
    cases=score.loc[mask,['encounter_id','source','label','cv_pred','m5a_pred']].copy();cases['minimum_future_haversine_nm']=d[mask]
    result={'definition':'Synthetic AIS Validation with ground-truth future minimum haversine separation <0.1 nautical mile, evaluated only after scores were frozen','count':int(mask.sum()),'cv_recall':float(cases.cv_pred.mean()),'m5a_recall':float(cases.m5a_pred.mean()),'cv_false_negatives':int((~cases.cv_pred).sum()),'m5a_false_negatives':int((~cases.m5a_pred).sum()),'used_for_scoring_or_threshold_selection':False,'evaluation_split':'validation'}
    cases.to_csv(p/'close_positive_cases.csv',index=False);(p/'close_positive_metrics.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
    allfiles=sorted(q for q in p.iterdir() if q.is_file() and q.name!='checksums.sha256');(p/'checksums.sha256').write_text(''.join(digest(q)+'  '+q.name+'\n' for q in allfiles),encoding='utf8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--directory',required=True);a.add_argument('--dataset-root',required=True);b=a.parse_args();run(b.directory,b.dataset_root)
