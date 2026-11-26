import json

import pytest

from scripts.run_s4_t15_benchmark import access_state
from src.evaluation.t15_source_registry import canonical_test_source
from src.evaluation import t15_metadata_audit as m
from src.evaluation import t15_authorization as a


@pytest.mark.parametrize(('raw', 'expected'), [
    ('yang_lei', 'YANG_LEI'),
    ('real_ais_denmark_oct2025', 'REAL_AIS'),
    ('synthetic_ais_denmark_oct2025', 'SYNTHETIC_AIS'),
])
def test_exact_mapping(raw, expected):
    assert canonical_test_source(raw) == expected


@pytest.mark.parametrize('raw', ['yanglei', 'real_ais_kattegat_v3',
    'augmented_real_ais_kattegat_v3', ' Yang_lei', 'yang_lei ', None])
def test_reject_unapproved_sources(raw):
    with pytest.raises(ValueError):
        canonical_test_source(raw)


def test_exception_access_status_from_durable_events(tmp_path):
    path = tmp_path / 'audit.jsonl'
    assert access_state(path) == 'NOT_ACCESSED'
    path.write_text(json.dumps({'state': 'SEMANTIC_ACCESS_ATTEMPTED'}) + '\n', encoding='utf8')
    assert access_state(path) == 'SEMANTIC_ACCESS_ATTEMPTED'
    with path.open('a', encoding='utf8') as f:
        f.write(json.dumps({'state': 'SEMANTIC_ACCESS_OBSERVED'}) + '\n')
    assert access_state(path) == 'AUTHORIZED_ACCESS_FAILED_DURING_LOAD'
    assert access_state(path, completed=True) == 'AUTHORIZED_ACCESS_COMPLETED'


def metadata_record():
    scope={'schema_version':1,'scope':'TEST_HISTORY_METADATA_AUDIT_ONLY','approval':'T15-R2-R3','lock_id':a.LOCK_ID,'lock_manifest_sha256':a.LOCK_SHA,'package_sha256':a.PAYLOAD_SHA,'dataset_lock_sha256':a.DATASET_LOCK,'dataset_manifest_sha256':a.DATASET_MANIFEST,'source_sha256':'a'*64,'fields':list(m.FIELDS),'split':'test','inference_authorized':False,'benchmark_authorized':False}
    return {**scope,'authorization_id':'synthetic-metadata','scope_sha256':'b'*64},scope


def test_metadata_audit_scope_is_distinct_from_benchmark():
    record,scope=metadata_record();m.validate_record(record,scope,'a'*64)
    lock={'lock_id':a.LOCK_ID,'package_identity':a.PAYLOAD_SHA,'model_lock':True,'lock_scope':'OFFLINE_PROTOTYPE','test_benchmark_authorized':False,'production_approved':False,'model':{'checkpoint_sha256':a.CHECKPOINT},'operating_points':{'CV':{'grid_index':87,'threshold':.435},'M5a':{'grid_index':84,'threshold':.42},'comparator':'>='}}
    with pytest.raises(a.AuthorizationError):a._validate_record(record,scope,'b'*64,lock)


@pytest.mark.parametrize('field,value',[('source_sha256','b'*64),('benchmark_authorized',True),('inference_authorized',True),('scope','ALL'),('split','validation'),('fields',['LAT','LON'])])
def test_metadata_scope_rejects_unauthorized_change(field,value):
    record,scope=metadata_record();record[field]=value
    with pytest.raises(a.AuthorizationError):m.validate_record(record,scope,'a'*64)


@pytest.mark.parametrize('read_ok',[False,True])
def test_loader_exception_records_only_observed_reads(tmp_path,monkeypatch,read_ok):
    import numpy as np
    from types import SimpleNamespace
    from src.evaluation import t15_trusted_test as t
    dataset=tmp_path/'dataset';package=tmp_path/'package';dataset.mkdir();package.mkdir()
    target=dataset/'test'/'tensors'/'X_unscaled.npy';target.parent.mkdir(parents=True)
    if read_ok:np.save(target,np.array([1],dtype='float32'))
    class Loader:
        def __init__(self,root):pass
        def load_split(self,split):
            np.load(target)
            raise RuntimeError('validation failed after read')
    monkeypatch.setattr(t,'DatasetLoader',Loader);monkeypatch.setattr(t,'verify_context',lambda ctx:ctx)
    ctx=SimpleNamespace(dataset_root=dataset,package_root=package);log=tmp_path/'events.jsonl'
    with pytest.raises((RuntimeError,FileNotFoundError)):t.load_authorized_test(ctx,log)
    states=[json.loads(line)['state'] for line in log.read_text().splitlines()]
    assert states==(['SEMANTIC_ACCESS_ATTEMPTED','SEMANTIC_ACCESS_OBSERVED'] if read_ok else ['SEMANTIC_ACCESS_ATTEMPTED'])
    assert access_state(log)==('AUTHORIZED_ACCESS_FAILED_DURING_LOAD' if read_ok else 'SEMANTIC_ACCESS_ATTEMPTED')


def test_missing_categorical_metadata_is_reported_without_mixed_types():
    import pandas as pd
    from src.evaluation.t15_benchmark import _category_values
    values=_category_values(pd.Series(['easy',None,pd.NA,'hard']))
    assert sorted(set(values))==['MISSING','easy','hard']
