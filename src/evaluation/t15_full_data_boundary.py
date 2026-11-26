"""T15-only phase-separated boundary; no Test access at import.

This adapter is a work in progress and must not be used to authorize real Test
until the full synthetic preflight and full regression are passed.
"""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from src.data.dataset_loader import DatasetLoader,SplitData
from src.evaluation.t15_authorization import verify_context,AuthorizationError
from src.evaluation.t15_trusted_test import _adapt_history_validator,LoadedTest
from src.inference.offline_validation import COLUMNS


def input_requirements(n):
    v=2*n
    def rule(coverage):return {'phase':'input','coverage':coverage}
    return {'X':rule({'shape':[v,10,4],'dtype':'float32','logical_values':v*40,'selection':'all'}),
            'anchors':rule({'shape':[n,2,2],'dtype':'float64','logical_values':n*4,'selection':'all'}),
            'encounter_metadata':rule({'rows':n,'columns':['encounter_id','data_source','anchor_timestamp']}),
            'encounter_index':rule({'rows':n,'columns':['encounter_id','encounter_index']}),
            'vessel_index':rule({'rows':v,'columns':['encounter_id','encounter_index','vessel','vessel_id','X_row','data_source']}),
            'parquet_footer':rule({'records':n*50}),
            'history':rule({'rows':v*10,'columns':COLUMNS,'filter':'history'})}


def evaluation_requirements(n):
    def rule(coverage):return {'phase':'evaluation','coverage':coverage}
    return {'labels':rule({'shape':[n],'dtype':'int8','logical_values':n,'selection':'all'}),
            'target':rule({'shape':[n,2,15,2],'dtype':'float32','logical_values':n*60,'selection':'all'}),
            'label_index':rule({'rows':n,'columns':['encounter_id','high_risk_label']}),
            'evaluation_metadata':rule({'rows':n,'columns':['encounter_id','difficulty','scenario']}),
            'future':rule({'rows':n*30,'columns':['encounter_id','vessel','relative_minute','is_future','LAT','LON','timestamp_utc','anchor_timestamp'],'filter':'future'})}


@dataclass(frozen=True)
class PhasedInput(LoadedTest):
    audit:object


def _require(ok,msg):
    if not bool(ok):raise AuthorizationError(msg)


def read_inputs(ctx,audit):
    return _read_inputs(ctx,audit,1320,2640)


def _read_inputs(ctx,audit,expected_n,expected_v):
    verify_context(ctx);loader=DatasetLoader(ctx.dataset_root);root=Path(loader.root)/'test';cfg=loader.config['splits']['test']
    n,v=cfg['encounters'],cfg['vessels'];_require((n,v)==(expected_n,expected_v),'wrong split scope')
    X=audit.materialize_npy(root/'tensors/X_unscaled.npy','input','X',expected_shape=(v,10,4),expected_dtype='float32')
    anchors=audit.materialize_npy(root/'tensors/anchor_positions_EN_nm.npy','input','anchors',expected_shape=(n,2,2),expected_dtype='float64')
    meta=audit.read('input','encounter_metadata',lambda:pd.read_parquet(root/'data/encounter_metadata.parquet',columns=['encounter_id','data_source','anchor_timestamp']),coverage={'rows':n,'columns':['encounter_id','data_source','anchor_timestamp']},operation='parquet projected columns')
    ei=audit.read('input','encounter_index',lambda:pd.read_csv(root/'tensors/encounter_tensor_index.csv',dtype={'encounter_id':str},usecols=['encounter_id','encounter_index']),coverage={'rows':n,'columns':['encounter_id','encounter_index']},operation='csv projected columns')
    vi=audit.read('input','vessel_index',lambda:pd.read_csv(root/'tensors/vessel_tensor_index.csv',dtype={'encounter_id':str,'vessel_id':str},usecols=['encounter_id','encounter_index','vessel','vessel_id','X_row','data_source']),coverage={'rows':v,'columns':['encounter_id','encounter_index','vessel','vessel_id','X_row','data_source']},operation='csv projected columns')
    records=audit.read('input','parquet_footer',lambda:pq.ParquetFile(root/'data'/cfg['data']).metadata.num_rows,coverage={'records':cfg['records']},operation='parquet footer only')
    _require(records==cfg['records'] and len(meta)==n and len(ei)==n and len(vi)==v,'dataset counts mismatch')
    _require(np.array_equal(ei.encounter_index.to_numpy(),np.arange(n)) and not ei.encounter_id.duplicated().any() and meta.encounter_id.astype(str).tolist()==ei.encounter_id.tolist(),'encounter index mismatch')
    _require(not vi.X_row.duplicated().any() and set(vi.X_row)==set(range(v)),'vessel index mismatch')
    pairs=np.full((n,2),-1,dtype=np.int64)
    for row in vi.itertuples(index=False):
        e,x=int(row.encounter_index),int(row.X_row)
        _require(0<=e<n and row.vessel in ('A','B') and row.encounter_id==ei.iloc[e].encounter_id,'invalid A/B index')
        slot=0 if row.vessel=='A' else 1;_require(pairs[e,slot]==-1,'duplicate A/B index');pairs[e,slot]=x
    _require((pairs>=0).all(),'missing A/B index');vi=vi.set_index('X_row',drop=False).loc[np.arange(v)].reset_index(drop=True)
    h=audit.read('input','history',lambda:pd.read_parquet(root/'data'/cfg['data'],columns=COLUMNS,filters=[('is_history','==',True)]),coverage={'rows':v*10,'columns':COLUMNS,'filter':'history'},operation='parquet history projected columns')
    s=SplitData('test',X,None,None,anchors,None,meta,ei,vi,pairs,records)
    h=_adapt_history_validator(n,v)(s,h)
    verify_context(ctx)
    return PhasedInput(ctx,s,h,(),audit)


def read_evaluation(loaded):
    """Call only after CV/M5a prediction and risk scoring have completed."""
    verify_context(loaded.context);root=Path(loaded.context.dataset_root)/'test';a=loaded.audit;s=loaded.split;n=len(s.encounters)
    a.require_phase('risk_scoring')
    labels=a.materialize_npy(root/'tensors/labels.npy','evaluation','labels',expected_shape=(n,),expected_dtype='int8')
    target=a.materialize_npy(root/'tensors/target_EN_nm.npy','evaluation','target',expected_shape=(n,2,15,2),expected_dtype='float32')
    idx=a.read('evaluation','label_index',lambda:pd.read_csv(root/'tensors/encounter_tensor_index.csv',dtype={'encounter_id':str},usecols=['encounter_id','high_risk_label']),coverage={'rows':n,'columns':['encounter_id','high_risk_label']},operation='csv label columns')
    _require(np.array_equal(idx.encounter_id.to_numpy(),s.encounters.encounter_id.to_numpy()) and np.array_equal(idx.high_risk_label.to_numpy(),labels),'labels/index mismatch')
    em=a.read('evaluation','evaluation_metadata',lambda:pd.read_parquet(root/'data/encounter_metadata.parquet',columns=['encounter_id','difficulty','scenario']),coverage={'rows':n,'columns':['encounter_id','difficulty','scenario']},operation='parquet evaluation columns')
    _require(em.encounter_id.astype(str).tolist()==s.encounters.encounter_id.tolist(),'evaluation metadata mismatch')
    s.labels=labels;s.common=target;s.metadata=s.metadata.merge(em,on='encounter_id',validate='one_to_one',sort=False)
    return s
