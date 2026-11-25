"""Read-only contract verification helpers; not a production AIS adapter."""
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.data.dataset_loader import DatasetLoader
from src.data.tensor_verification import checksum_dataset

ROUNDTRIP_DEGREES = 1e-10
ANCHOR_TOLERANCE_NM = 1e-10
POSITION_TOLERANCE_NM = 1e-6
VELOCITY_TOLERANCE_KN = 1e-5
RECONSTRUCTION_TOLERANCE_NM = 1e-6


def velocity_en(sog, cog):
    angle = np.deg2rad(np.asarray(cog, dtype=np.float64))
    speed = np.asarray(sog, dtype=np.float64)
    return np.stack([speed*np.sin(angle), speed*np.cos(angle)], axis=-1)


def common_en(lat, lon, lat0, lon0):
    return np.stack([(np.asarray(lon)-lon0)*60*np.cos(np.deg2rad(lat0)), (np.asarray(lat)-lat0)*60], axis=-1)


def inverse_en(east, north, lat0, lon0):
    factor = np.cos(np.deg2rad(lat0))
    if np.any(~np.isfinite(factor)) or np.any(np.abs(factor) <= 1e-12):
        raise ValueError('Unstable inverse at reference latitude')
    return np.stack([np.asarray(north)/60+lat0, np.asarray(east)/(60*factor)+lon0], axis=-1)


def asof_valid(grid, source):
    grid, source = pd.Timestamp(grid), pd.Timestamp(source)
    if grid.tz is None or source.tz is None:
        raise ValueError('Timezone-aware timestamps required')
    age = (grid.tz_convert('UTC')-source.tz_convert('UTC')).total_seconds()
    return 0 <= age <= 60


def proposed_pair_id(first, second):
    if not isinstance(first,str) or not isinstance(second,str) or not first or not second:
        raise ValueError('Two distinct namespaced IDs are required')
    first,second=(unicodedata.normalize('NFC', value) for value in (first,second))
    if first == second:
        raise ValueError('Two distinct IDs are required after NFC')
    payload=json.dumps(sorted([first,second],key=lambda value:value.encode('utf-8')), ensure_ascii=False, separators=(',',':')).encode('utf-8')
    return 'pair:v1:'+hashlib.sha256(payload).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def verify_split(loader, name):
    s=loader.load_split(name)
    cols=['encounter_id','vessel','vessel_id','timestamp_utc','anchor_timestamp','relative_minute','is_history','is_future','SOG','COG','LAT','LON','data_source','original_source_timestamp_utc','simulated_source_timestamp_utc']
    df=pd.read_parquet(loader.root/name/'data'/loader.config['splits'][name]['data'],columns=cols)
    h=df.loc[df.is_history].copy()
    check(not h.is_future.any() and h.relative_minute.le(0).all(), f'{name}: future in history')
    h=h.merge(s.vessels[['encounter_id','vessel','vessel_id','X_row']],on=['encounter_id','vessel'],how='left',validate='many_to_one',suffixes=('','_index'))
    check(not h.X_row.isna().any() and h.vessel_id.astype(str).eq(h.vessel_id_index.astype(str)).all(), f'{name}: vessel mapping mismatch')
    h=h.sort_values(['X_row','relative_minute'],kind='stable').reset_index(drop=True)
    n=len(s.encounters); v=len(s.vessels)
    check(len(h)==v*10 and np.array_equal(h.X_row.to_numpy(),np.repeat(np.arange(v),10)), f'{name}: vessel coverage')
    check(np.array_equal(h.relative_minute.to_numpy(),np.tile(np.arange(-9,1),v)), f'{name}: history offsets')
    check(not h.duplicated(['encounter_id','vessel','relative_minute']).any(), f'{name}: duplicate history')
    check(str(h.timestamp_utc.dt.tz)=='UTC' and str(h.anchor_timestamp.dt.tz)=='UTC',f'{name}: UTC')
    check((h.timestamp_utc==h.anchor_timestamp+pd.to_timedelta(h.relative_minute,unit='min')).all(), f'{name}: grid alignment')
    check(h.groupby('encounter_id').anchor_timestamp.nunique().eq(1).all(),f'{name}: A/B anchors differ')
    sogcog=h[['SOG','COG']].to_numpy(dtype=np.float64).reshape(v,10,2)
    check(np.isfinite(sogcog).all() and (sogcog[:,:,0]>=0).all() and (sogcog[:,:,0]<=50).all() and (sogcog[:,:,1]>=0).all() and (sogcog[:,:,1]<360).all(),f'{name}: SOG/COG invalid')
    vel_error=float(np.max(np.abs(velocity_en(sogcog[:,:,0],sogcog[:,:,1])-s.X[:,:,2:])))
    check(vel_error < VELOCITY_TOLERANCE_KN, f'{name}: velocity mismatch')
    coords=h[['LAT','LON']].to_numpy(dtype=np.float64).reshape(v,10,2)[s.pairs]
    lat0=coords[:,0,0,0][:,None,None];lon0=coords[:,0,0,1][:,None,None]
    check(np.isfinite(coords).all() and (np.abs(coords[:,:,:,0])<=90).all() and (np.abs(coords[:,:,:,1])<=180).all(), f'{name}: coordinate values')
    check((np.abs(coords[:,:,:,1]-lon0)<180).all(), f'{name}: unsupported longitude wrap')
    xy=common_en(coords[:,:,:,0],coords[:,:,:,1],lat0,lon0)
    anchor=xy[:,:,9,:];anchor_error=float(np.max(np.abs(anchor-s.anchors)))
    relative=xy-anchor[:,:,None,:];position_error=float(np.max(np.abs(relative-s.X[s.pairs][:,:,:,:2])))
    back=inverse_en(xy[:,:,:,0],xy[:,:,:,1],lat0,lon0)
    roundtrip_error=float(np.max(np.abs(back-coords)))
    common_back=relative+anchor[:,:,None,:]; en_roundtrip=float(np.max(np.abs(common_back-xy)))
    distance_error=float(np.max(np.abs(np.linalg.norm(common_back[:,0]-common_back[:,1],axis=-1)-np.linalg.norm(xy[:,0]-xy[:,1],axis=-1))))
    target_error=float(np.max(np.abs(s.displacement[s.pairs].astype(np.float64)+s.anchors[:,:,None,:]-s.common)))
    check(anchor_error<ANCHOR_TOLERANCE_NM and position_error<POSITION_TOLERANCE_NM and roundtrip_error<ROUNDTRIP_DEGREES and target_error<RECONSTRUCTION_TOLERANCE_NM, f'{name}: coordinate mismatch')
    check(en_roundtrip<1e-10 and distance_error<1e-10, f'{name}: EN roundtrip or distance mismatch')
    sources={}
    for source,g in h.groupby('data_source'):
        is_yang=str(source) in ('yang_lei','yanglei')
        col='simulated_source_timestamp_utc' if str(source).startswith('augmented') else 'original_source_timestamp_utc'
        if is_yang:
            check(g.original_source_timestamp_utc.isna().all(),f'{name}: unexpected Yang AIS provenance')
            sources[str(source)]={'history_rows':len(g),'asof':'not_applicable_simulated_nominal_time'}
        else:
            age=(g.timestamp_utc-g[col]).dt.total_seconds()
            check(age.notna().all() and age.between(0,60,inclusive='both').all(),f'{name}: asof age invalid')
            repeated=int((g[col].groupby([g.encounter_id,g.vessel]).diff().dt.total_seconds()==0).sum())
            sources[str(source)]={'history_rows':len(g),'source_timestamp_field':col,'age_min_seconds':float(age.min()),'age_max_seconds':float(age.max()),'invalid_age_count':int((~age.between(0,60,inclusive='both')).sum()),'consecutive_reuses':repeated}
            if str(source).startswith('augmented'):
                original=(g.timestamp_utc-g.original_source_timestamp_utc).dt.total_seconds()
                sources[str(source)]['original_provenance_age_min_seconds']=float(original.min())
                sources[str(source)]['original_provenance_age_max_seconds']=float(original.max())
                sources[str(source)]['original_provenance_outside_0_60']=int((~original.between(0,60,inclusive='both')).sum())
    return {'encounters_checked':n,'encounters_complete':n,'encounters_missing_or_bad_mapping':0,'vessels_checked':v,'history_rows':len(h),'rule_shape_per_encounter':[2,10,2],'history_alignment':'PASS','future_exclusion':'PASS','velocity_max_abs_error_kn':vel_error,'anchor_max_abs_error_nm':anchor_error,'relative_position_max_abs_error_nm':position_error,'geographic_roundtrip_max_abs_error_degrees':roundtrip_error,'common_en_roundtrip_max_abs_error_nm':en_roundtrip,'distance_max_abs_error_nm':distance_error,'target_reconstruction_max_abs_error_nm':target_error,'source_timestamp_observations':sources}


def verify():
    loader=DatasetLoader(); checksum=checksum_dataset(loader.root,loader.lock)
    results={name:verify_split(loader,name) for name in ('train','validation')}
    return {'dataset_version':loader.lock['dataset_version'],'dataset_checksum':checksum,'splits':results,'coordinate_method':'E=(lon-lon0)*60*cos(lat0); N=(lat-lat0)*60; lat0 in radians within cosine','coordinate_origin':'vessel A first history position t0-9','coordinate_source':'DATASET_FINAL/scripts/verify_dataset_final.py and schemas/coordinate_conventions.md','roundtrip_tolerance_degrees':ROUNDTRIP_DEGREES,'velocity_tolerance_kn':VELOCITY_TOLERANCE_KN,'asof_convention':'latest source <= grid and 0 <= age <= 60 seconds inclusive','rule_input_source':'locked Train/Validation Parquet history SOG and COG','rule_input_shape':[2,10,2],'status_scope':'verification of contracts and offline feasibility only; no production pipeline','team_review_required':['replay clock and freshness','pair ID and A/B order','coordinate origin and geographic availability','rule input adapter','forecast status and fallback semantics'],'unverified_items':['Replay Track Management integration and pair identity agreement with Toan','Geographic inverse accuracy beyond the checked local approximation/domain','Production adapter, forecast, fallback and alert implementation'], 'blockers':[], 'ready_for_step_03':True}


if __name__=='__main__':
    print(json.dumps(verify(),indent=2))
