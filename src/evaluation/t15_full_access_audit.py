"""Durable application-level observations for the T15 full technical rerun.

An mmap event describes mapping only.  Materialization explicitly copies the
whole logical array; it does not claim visibility of individual OS page faults.
"""
import json
import os
import uuid
import builtins
import inspect
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


class AuditError(ValueError):
    pass


@contextmanager
def supported_path_guard(dataset_root):
    """Deny uninstrumented Python Test paths; not a native/OS sandbox."""
    from src.data.tensor_verification import checksum_dataset
    test=(Path(dataset_root).resolve()/'test').resolve()
    old_open=builtins.open;old_path_open=Path.open;old_load=np.load;old_csv=pd.read_csv;old_parquet=pd.read_parquet;old_pq=pq.ParquetFile
    counts={'denied':0}
    def check(path):
        if not isinstance(path,(str,Path,os.PathLike)):return
        try:inside=Path(path).resolve().is_relative_to(test)
        except (OSError,ValueError):inside=False
        if not inside:return
        frame=inspect.currentframe();allowed=False
        while frame:
            if frame.f_code in (Audit.read.__code__,Audit.materialize_npy.__code__,checksum_dataset.__code__):allowed=True;break
            frame=frame.f_back
        if not allowed:counts['denied']+=1;raise AuditError('uninstrumented Test path access denied')
    def wrap(fn):
        def guarded(path,*args,**kwargs):check(path);return fn(path,*args,**kwargs)
        return guarded
    try:
        builtins.open=wrap(old_open);Path.open=wrap(old_path_open);np.load=wrap(old_load);pd.read_csv=wrap(old_csv);pd.read_parquet=wrap(old_parquet);pq.ParquetFile=wrap(old_pq)
        yield counts
    finally:
        builtins.open=old_open;Path.open=old_path_open;np.load=old_load;pd.read_csv=old_csv;pd.read_parquet=old_parquet;pq.ParquetFile=old_pq


class Audit:
    def __init__(self, path, run_id, authorization_id, protocol_sha256):
        self.path=Path(path)
        self.identity={'run_id':run_id,'authorization_id':authorization_id,'protocol_sha256':protocol_sha256}
        self.stats={'logging_seconds':0.0,'materialization_seconds':0.0,'materialized_bytes':0}
        if not all(self.identity.values()):raise AuditError('missing audit identity')

    def emit(self, phase, category, event_type, operation_id, *, coverage=None, detail=None):
        item={**self.identity,'event_id':uuid.uuid4().hex,'operation_id':operation_id,
              'timestamp_utc':datetime.now(timezone.utc).isoformat(),'phase':phase,
              'category':category,'event_type':event_type,'coverage':coverage,'detail':detail}
        start=time.perf_counter()
        with self.path.open('a',encoding='utf8') as f:
            f.write(json.dumps(item,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
        self.stats['logging_seconds']+=time.perf_counter()-start
        return item

    def read(self, phase, category, fn, *, coverage, operation):
        op=uuid.uuid4().hex
        attempt='METADATA_READ_ATTEMPTED' if category=='parquet_footer' else 'SEMANTIC_READ_ATTEMPTED'
        completion='METADATA_READ_COMPLETED' if category=='parquet_footer' else 'MATERIALIZATION_COMPLETED'
        observed='METADATA_ACCESS_OBSERVED' if category=='parquet_footer' else 'SEMANTIC_VALUE_ACCESS_OBSERVED'
        self.emit(phase,category,attempt,op,coverage=coverage,detail=operation)
        try:
            value=fn()
            if isinstance(coverage,dict) and 'rows' in coverage and len(value)!=coverage['rows']:raise AuditError('actual row coverage mismatch')
            if isinstance(coverage,dict) and 'records' in coverage and value!=coverage['records']:raise AuditError('actual record coverage mismatch')
        except Exception as exc:
            self.emit(phase,category,'READ_FAILED',op,coverage=coverage,detail=type(exc).__name__)
            raise
        self.emit(phase,category,completion,op,coverage=coverage,detail=operation)
        self.emit(phase,category,observed,op,coverage=coverage,detail=operation)
        return value

    def materialize_npy(self, path, phase, category, *, expected_shape, expected_dtype):
        path=Path(path);op=uuid.uuid4().hex
        self.emit(phase,category,'FILE_OPEN_ATTEMPTED',op,detail=str(path))
        try:arr=np.load(path,mmap_mode='r',allow_pickle=False)
        except Exception as exc:
            self.emit(phase,category,'READ_FAILED',op,detail=type(exc).__name__);raise
        if not isinstance(arr,np.memmap):raise AuditError('expected memory map')
        self.emit(phase,category,'MEMORY_MAP_CREATED',op,coverage={'shape':list(arr.shape),'dtype':str(arr.dtype)})
        if arr.shape!=tuple(expected_shape) or arr.dtype!=np.dtype(expected_dtype):raise AuditError('array identity mismatch')
        coverage={'shape':list(arr.shape),'dtype':str(arr.dtype),'logical_values':int(arr.size),'selection':'all'}
        self.emit(phase,category,'SEMANTIC_READ_ATTEMPTED',op,coverage=coverage,detail='numpy owned C-order copy')
        start=time.perf_counter()
        try:owned=np.array(arr,copy=True,order='C',subok=False)
        except Exception as exc:
            self.emit(phase,category,'READ_FAILED',op,coverage=coverage,detail=type(exc).__name__);raise
        if isinstance(owned,np.memmap) or not owned.flags.owndata or owned.shape!=arr.shape or owned.dtype!=arr.dtype:raise AuditError('materialization failed')
        self.stats['materialization_seconds']+=time.perf_counter()-start
        self.stats['materialized_bytes']+=owned.nbytes
        self.emit(phase,category,'MATERIALIZATION_COMPLETED',op,coverage=coverage,detail='owned array copy completed')
        self.emit(phase,category,'SEMANTIC_VALUE_ACCESS_OBSERVED',op,coverage=coverage,detail='owned array copy completed')
        return owned

    def complete_phase(self,phase):
        return self.emit(phase,'phase:'+phase,'PHASE_COMPLETED',uuid.uuid4().hex,detail='phase completed successfully')

    def require_phase(self,phase):
        entries=[json.loads(x) for x in self.path.read_text(encoding='utf8').splitlines()] if self.path.exists() else []
        if not any(e.get('phase')==phase and e.get('category')=='phase:'+phase and e.get('event_type')=='PHASE_COMPLETED' and all(e.get(k)==v for k,v in self.identity.items()) for e in entries):raise AuditError('required phase not complete: '+phase)


def verify_events(events, requirements, identity, *, require_authorization=False):
    """Require one ordered attempt/observed operation per complete category."""
    failures=[];seen=set()
    for event in events:
        if any(event.get(k)!=v for k,v in identity.items()):failures.append('identity')
        if not event.get('event_id') or event['event_id'] in seen:failures.append('duplicate event')
        seen.add(event.get('event_id'))
        phase=event.get('phase')
        valid_phase=event.get('event_type')=='PHASE_COMPLETED' and phase in ('trusted_input','inference','risk_scoring','evaluation') and event.get('category')=='phase:'+phase
        valid_auth=phase=='authorization' and event.get('category')=='authorization' and event.get('event_type')=='AUTHORIZATION_VERIFIED'
        if event.get('category') not in requirements and not valid_phase and not valid_auth:failures.append('unexpected category')
    if require_authorization:
        positions=[i for i,e in enumerate(events) if e.get('event_type')=='AUTHORIZATION_VERIFIED' and e.get('phase')=='authorization' and e.get('category')=='authorization']
        if len(positions)!=1 or positions[0]!=0:failures.append('missing, duplicate or late authorization event')
    for category,rule in requirements.items():
        required=rule.get('coverage') if isinstance(rule,dict) and 'coverage' in rule and 'phase' in rule else rule
        required_phase=rule.get('phase') if isinstance(rule,dict) and 'coverage' in rule and 'phase' in rule else None
        group=[e for e in events if e.get('category')==category]
        types=('METADATA_READ_ATTEMPTED','METADATA_READ_COMPLETED','METADATA_ACCESS_OBSERVED') if category=='parquet_footer' else ('SEMANTIC_READ_ATTEMPTED','MATERIALIZATION_COMPLETED','SEMANTIC_VALUE_ACCESS_OBSERVED')
        attempts=[(i,e) for i,e in enumerate(group) if e.get('event_type')==types[0]]
        completed=[(i,e) for i,e in enumerate(group) if e.get('event_type')==types[1]]
        observed=[(i,e) for i,e in enumerate(group) if e.get('event_type')==types[2]]
        if len(attempts)!=1 or len(completed)!=1 or len(observed)!=1:failures.append(category+': missing or duplicate coverage');continue
        ai,a=attempts[0];ci,c=completed[0];oi,o=observed[0]
        if not (ai<ci<oi) or len({a.get('operation_id'),c.get('operation_id'),o.get('operation_id')})!=1:failures.append(category+': invalid order/operation')
        if a.get('coverage')!=required or c.get('coverage')!=required or o.get('coverage')!=required:failures.append(category+': coverage')
        if required_phase is not None and any(e.get('phase')!=required_phase for e in (a,c,o)):failures.append(category+': wrong phase')
        if not (a.get('timestamp_utc','')<=c.get('timestamp_utc','')<=o.get('timestamp_utc','')):failures.append(category+': timestamp order')
        if any(e.get('event_type')=='READ_FAILED' and e.get('operation_id')==a.get('operation_id') for e in group):failures.append(category+': contradictory failure')
    if any(isinstance(r,dict) and r.get('phase')=='evaluation' for r in requirements.values()):
        phase_positions={}
        for phase in ('trusted_input','inference','risk_scoring','evaluation'):
            positions=[i for i,e in enumerate(events) if e.get('phase')==phase and e.get('category')=='phase:'+phase and e.get('event_type')=='PHASE_COMPLETED']
            if len(positions)!=1:failures.append(phase+': missing or duplicate completion')
            else:phase_positions[phase]=positions[0]
        if len(phase_positions)==4:
            if not (phase_positions['trusted_input']<phase_positions['inference']<phase_positions['risk_scoring']<phase_positions['evaluation']):failures.append('phase order')
            for i,e in enumerate(events):
                if e.get('event_type')=='SEMANTIC_VALUE_ACCESS_OBSERVED' and e.get('phase')=='input' and i>=phase_positions['trusted_input']:failures.append('input observed after consumption')
                if e.get('event_type')=='SEMANTIC_READ_ATTEMPTED' and e.get('phase')=='evaluation' and not (phase_positions['risk_scoring']<i<phase_positions['evaluation']):failures.append('evaluation access outside phase')
    return {'status':'FAIL' if failures else 'PASS','failures':failures,'required_categories':sorted(requirements)}
