"""Authorized, locked Test history adapter; no Test reads occur at import."""
import inspect
import json
import os
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from src.evaluation.t15_authorization import verify_context,AuthorizationError
from src.data.dataset_loader import DatasetLoader
from src.inference import offline_validation as offline
from src.evaluation.t15_source_registry import TEST_SOURCES

@dataclass(frozen=True)
class LoadedTest:
    context:object
    split:object
    history:object
    access_audit:tuple


def _adapt_history_validator(n,v):
    """Reuse T11 checks with exact, source-specific Test identifiers."""
    source=inspect.getsource(offline.validate_history)
    needle='n == 835 and v == 1670'
    split_check="h['split'].eq('validation')"
    if source.count(needle)!=1 or source.count(split_check)!=1:raise AuthorizationError('locked history validator unexpectedly changed')
    source=source.replace(needle,f'n == {int(n)} and v == {int(v)}').replace(split_check,"h['split'].eq('test')")
    for original, revised in [('yanglei','yang_lei'), ('real_ais_kattegat_v3','real_ais_denmark_oct2025'), ('augmented_real_ais_kattegat_v3','synthetic_ais_denmark_oct2025')]:
        if source.count("'"+original+"'") != 1:raise AuthorizationError('locked source validation unexpectedly changed')
        source=source.replace("'"+original+"'","'"+revised+"'")
    globals_=dict(offline.__dict__);globals_['SOURCE_MAP']=TEST_SOURCES
    namespace={};exec(compile(source,'<T11-history-test-adaptation>','exec'),globals_,namespace)
    return namespace['validate_history']


def append_audit(path,event):
    with Path(path).open('a',encoding='utf8') as f:
        f.write(json.dumps(event,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())


def load_authorized_test(ctx,audit_path=None):
    """Require an issued context; log semantic reads in the supported path."""
    verify_context(ctx);root=ctx.dataset_root;test=(root/'test').resolve();events=[]
    if audit_path is None:raise AuthorizationError('durable Test access audit required')
    audit_path=Path(audit_path).resolve()
    if audit_path.is_relative_to(root) or audit_path.is_relative_to(ctx.package_root):raise AuthorizationError('audit path outside authorized output area required')
    allowed={'tensors/X_unscaled.npy','tensors/target_GRU_displacement_nm.npy','tensors/target_EN_nm.npy','tensors/anchor_positions_EN_nm.npy','tensors/labels.npy','tensors/encounter_tensor_index.csv','tensors/vessel_tensor_index.csv','data/encounter_metadata.parquet','data/test_1320.parquet'}
    def audit(value,category,state):
        if not isinstance(value,(str,Path)):return
        p=Path(value).resolve()
        if p.is_relative_to(test):
            name=p.relative_to(test).as_posix()
            if name not in allowed:raise AuthorizationError('Test path not authorized: '+name)
            event={'phase':'AUTHORIZED_TEST_INPUT','category':category,'state':state,'path':'test/'+name,'timestamp_utc':datetime.now(timezone.utc).isoformat()};events.append(event);append_audit(audit_path,event)
    originals=(np.load,pd.read_csv,pd.read_parquet)
    def wrap(fn,kind):
        def called(path,*args,**kwargs):
            audit(path,kind,'SEMANTIC_ACCESS_ATTEMPTED')
            result=fn(path,*args,**kwargs)
            audit(path,kind,'SEMANTIC_ACCESS_OBSERVED')
            return result
        return called
    try:
        np.load=wrap(originals[0],'npy_deserialization');pd.read_csv=wrap(originals[1],'csv_deserialization');pd.read_parquet=wrap(originals[2],'parquet_deserialization')
        loader=DatasetLoader(root);s=loader.load_split('test')
        # DatasetLoader also reads Parquet file metadata through pyarrow.ParquetFile.
        event={'phase':'AUTHORIZED_TEST_INPUT','category':'parquet_metadata','path':'test/data/test_1320.parquet','timestamp_utc':datetime.now(timezone.utc).isoformat(),'note':'recorded after DatasetLoader metadata inspection'};events.append(event);append_audit(audit_path,event)
        h=pd.read_parquet(root/'test'/'data'/loader.config['splits']['test']['data'],columns=offline.COLUMNS,filters=[('is_history','==',True)])
        h=_adapt_history_validator(1320,2640)(s,h)
    finally:
        np.load,pd.read_csv,pd.read_parquet=originals
    verify_context(ctx)
    return LoadedTest(ctx,s,h,tuple(events))


def make_authorized_batch(loaded,start,stop):
    if not isinstance(loaded,LoadedTest):raise AuthorizationError('unverified Test data')
    verify_context(loaded.context)
    if not (isinstance(start,int) and isinstance(stop,int) and 0<=start<stop<=len(loaded.split.pairs)):raise AuthorizationError('invalid batch range')
    globals_=dict(offline.__dict__);globals_['SOURCE_MAP']=TEST_SOURCES
    namespace={};exec(compile(inspect.getsource(offline.make_batch),'<T11-test-batch-adaptation>','exec'),globals_,namespace)
    return namespace['make_batch'](loaded.split,loaded.history,start,stop)
