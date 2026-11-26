"""Narrow, separately pinned Test history metadata audit; never returns data."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.dataset_loader import DatasetLoader
from src.data.tensor_verification import checksum_dataset
from src.evaluation.t15_authorization import (DATASET_LOCK, DATASET_MANIFEST, LOCK_ID,
    LOCK_SHA, PAYLOAD_SHA, AuthorizationError, _pre_gate_test_guard, _read_pinned_json)
from src.evaluation.t15_source_registry import TEST_SOURCES
from src.release.offline_lock import digest, verify_active

FIELDS = ('encounter_id','vessel','vessel_id','timestamp_utc','anchor_timestamp',
          'relative_minute','is_history','is_future','data_source','split','coordinate_type',
          'original_source_timestamp_utc','simulated_source_timestamp_utc',
          'source_track_id','parent_encounter_id','parameters')
SOURCE_PATH = Path(__file__).resolve()


def _write_exclusive(path, obj):
    with Path(path).open('x',encoding='utf8') as f:
        json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())


def validate_record(record, scope, source_sha):
    expected={'schema_version':1,'scope':'TEST_HISTORY_METADATA_AUDIT_ONLY',
        'approval':'T15-R2-R3','lock_id':LOCK_ID,'lock_manifest_sha256':LOCK_SHA,
        'package_sha256':PAYLOAD_SHA,'dataset_lock_sha256':DATASET_LOCK,
        'dataset_manifest_sha256':DATASET_MANIFEST,'source_sha256':source_sha,
        'fields':list(FIELDS),'split':'test','inference_authorized':False,
        'benchmark_authorized':False}
    if any(record.get(k)!=v for k,v in expected.items()) or scope != expected:
        raise AuthorizationError('metadata audit authorization or scope mismatch')
    if not record.get('authorization_id') or not record.get('scope_sha256'):
        raise AuthorizationError('missing metadata audit identity')


def inspect_history(h):
    """Inspect metadata only; report aggregate failures, never export rows."""
    problems=[]
    def check(ok,reason):
        if not bool(ok):problems.append(reason)
    check(len(h)==26400,'history row count')
    required=['encounter_id','vessel','vessel_id','timestamp_utc','anchor_timestamp','relative_minute','data_source','split','coordinate_type']
    check(h[required].notna().all().all(),'missing identity or temporal metadata')
    check(h.data_source.isin(TEST_SOURCES).all(),'unknown raw source')
    check(h['split'].eq('test').all() and h.is_history.eq(True).all() and h.is_future.eq(False).all(),'split/history mismatch')
    for col in ('timestamp_utc','anchor_timestamp','original_source_timestamp_utc','simulated_source_timestamp_utc'):
        check(isinstance(h[col].dtype,pd.DatetimeTZDtype) and str(h[col].dt.tz)=='UTC','timezone '+col)
    check((h.timestamp_utc == h.anchor_timestamp + pd.to_timedelta(h.relative_minute,unit='min')).all(),'timestamp/anchor mismatch')
    check((h.timestamp_utc <= h.anchor_timestamp).all(),'future observation')
    check(not h.duplicated(['encounter_id','vessel','relative_minute']).any(),'duplicate history')
    check(h.groupby('encounter_id').anchor_timestamp.nunique().eq(1).all(),'anchor inconsistency')
    check(h.groupby('encounter_id').data_source.nunique().eq(1).all(),'source inconsistency')
    check(h.groupby(['encounter_id','vessel']).vessel_id.nunique().eq(1).all(),'vessel identity inconsistency')
    check(h.groupby('encounter_id').vessel_id.nunique().eq(2).all(),'A/B identities')
    grouped=h.groupby(['encounter_id','vessel']).relative_minute.agg(lambda x:sorted(x.tolist()))
    check(grouped.map(lambda x:x==list(range(-9,1))).all(),'history order/coverage')
    vessels=h.groupby('encounter_id').vessel.agg(lambda x:set(x))
    check(vessels.map(lambda x:x=={'A','B'}).all(),'A/B slots')
    out={}
    expected={'yang_lei':720,'real_ais_denmark_oct2025':300,'synthetic_ais_denmark_oct2025':300}
    for source,canonical in TEST_SOURCES.items():
        g=h[h.data_source.eq(source)];count=int(g.encounter_id.nunique())
        check(count==expected[source] and len(g)==20*count,'source scope '+source)
        frame={'yang_lei':'simulated_LAT_LON','real_ais_denmark_oct2025':'geographical_WGS84','synthetic_ais_denmark_oct2025':'synthetic_geographical_WGS84'}[source]
        check(g.coordinate_type.eq(frame).all(),'coordinate frame '+source)
        item={'canonical_source_type':canonical,'encounters':count,'history_rows':len(g),'source_age_seconds':'NOT_APPLICABLE'}
        if canonical=='YANG_LEI':
            check(g.original_source_timestamp_utc.isna().all() and g.simulated_source_timestamp_utc.isna().all(),'Yang Lei invented AIS provenance')
        else:
            col='original_source_timestamp_utc' if canonical=='REAL_AIS' else 'simulated_source_timestamp_utc'
            check(g[col].notna().all() and g.source_track_id.notna().all(),'missing source metadata '+source)
            age=(g.timestamp_utc-g[col]).dt.total_seconds()
            check(age.between(0,60).all(),'source age '+source)
            item['source_age_seconds']={'min':float(age.min()) if age.notna().any() else None,'max':float(age.max()) if age.notna().any() else None,'violations':int((~age.between(0,60)).sum())}
            if canonical=='SYNTHETIC_AIS':
                check(g.original_source_timestamp_utc.notna().all() and g.parent_encounter_id.notna().all() and g.parameters.notna().all(),'missing synthetic parent provenance')
                shifts=[]
                for row in g[['parameters','vessel']].itertuples(index=False):
                    try:shifts.append(int(json.loads(row.parameters).get('shift',0)) if row.vessel=='B' else 0)
                    except (TypeError,ValueError,AttributeError,json.JSONDecodeError):shifts.append(None)
                check(all(x is not None for x in shifts),'invalid synthetic shift parameters')
                if all(x is not None for x in shifts):
                    expected_sim=g.original_source_timestamp_utc-pd.to_timedelta(shifts,unit='min')
                    check(expected_sim.eq(g.simulated_source_timestamp_utc).all(),'synthetic parent/simulated timeline relationship')
        out[source]=item
    return {'status':'PASS' if not problems else 'FAIL','failures':problems,'sources':out,'encounters':int(h.encounter_id.nunique()),'history_rows':len(h)}


def run(*,authorization_path,authorization_sha,scope_path,scope_sha,package_root,dataset_root,output_dir):
    out=Path(output_dir).resolve();root=Path(dataset_root).resolve();package=Path(package_root).resolve()
    if not out.is_dir() or out.is_relative_to(root) or out.is_relative_to(package):raise AuthorizationError('unsafe audit output')
    record=_read_pinned_json(authorization_path,authorization_sha);scope=_read_pinned_json(scope_path,scope_sha)
    if record.get('scope_sha256')!=scope_sha:raise AuthorizationError('scope pin mismatch')
    validate_record(record,scope,digest(SOURCE_PATH))
    lock=verify_active(package,LOCK_SHA)
    if lock['lock_id']!=LOCK_ID or lock['package_identity']!=PAYLOAD_SHA:raise AuthorizationError('lock mismatch')
    with _pre_gate_test_guard(root) as guard:
        loader=DatasetLoader(root)
        if digest(root/'DATASET_LOCK_MANIFEST.json')!=DATASET_LOCK:raise AuthorizationError('dataset lock mismatch')
        checksum=checksum_dataset(loader.root,loader.lock)
    if checksum.get('files_verified')!=93 or checksum.get('manifest_sha256')!=DATASET_MANIFEST or guard['blocked_deserialization'] or guard['blocked_other_opens']:raise AuthorizationError('dataset check failed')
    report={'status':'PASS','scope':'TEST_HISTORY_METADATA_AUDIT_ONLY','authorization_sha256':authorization_sha,'scope_sha256':scope_sha,'source_sha256':digest(SOURCE_PATH),'dataset_checksum':checksum,'guard':guard,'inference_authorized':False,'benchmark_authorized':False}
    gate=out/'metadata_pre_access_gate_report.json';_write_exclusive(gate,report);_write_exclusive(out/'metadata_gate_pin.json',{'sha256':digest(gate)})
    events=out/'metadata_access_events.jsonl';path=root/'test'/'data'/loader.config['splits']['test']['data']
    def log(state):
        with events.open('a',encoding='utf8') as f:
            f.write(json.dumps({'state':state,'path':'test/data/test_1320.parquet','columns':FIELDS,'filter':'is_history == true','timestamp_utc':datetime.now(timezone.utc).isoformat()})+'\n');f.flush();os.fsync(f.fileno())
    log('ATTEMPTED');h=pd.read_parquet(path,columns=list(FIELDS),filters=[('is_history','==',True)]);log('OBSERVED')
    result=inspect_history(h);_write_exclusive(out/'timestamp_provenance_matrix_v2.json',result)
    return result
