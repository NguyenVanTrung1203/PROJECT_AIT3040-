import json
from pathlib import Path
import pytest

from src.evaluation import t15_evaluation_replay as r
from src.evaluation.t15_authorization import AuthorizationError, _validate_record


def identity():
    return {'run_id':'synthetic','authorization_id':'synthetic-auth','protocol_sha256':'a'*64}


def test_read_order_and_observed_event_survives_evaluator_exception(tmp_path):
    path=tmp_path/'events.jsonl';calls=[]
    def read():
        events=[json.loads(x) for x in path.read_text().splitlines()]
        assert [e['state'] for e in events]==['ATTEMPTED'];calls.append('read');return 'decoded'
    assert r.audited_read(path,identity(),'future','synthetic',read)=='decoded'
    try:raise RuntimeError('evaluation fails after read')
    except RuntimeError:pass
    events=[json.loads(x) for x in path.read_text().splitlines()]
    assert [e['state'] for e in events]==['ATTEMPTED','OBSERVED'] and calls==['read']
    assert events[0]['timestamp_utc']<=events[1]['timestamp_utc'] and events[0]['event_id']!=events[1]['event_id']
    assert r.event_summary(path)['future']==['ATTEMPTED','OBSERVED']


def test_failed_read_never_emits_observed(tmp_path):
    log=tmp_path/'events.jsonl'
    def fail():raise FileNotFoundError('missing synthetic file')
    with pytest.raises(FileNotFoundError):r.audited_read(log,identity(),'future','synthetic',fail)
    assert r.event_summary(log)['future']==['ATTEMPTED','FAILED']


def replay_record():
    source={'src/evaluation/t15_evaluation_replay.py':r.digest(Path(r.__file__))}
    scope={'scope':'R2_EVALUATION_REPLAY_ONLY','parent_run_id':r.PARENT,'parent_manifest_sha256':r.PARENT_MANIFEST,'lock_id':r.LOCK_ID,'lock_manifest_sha256':r.LOCK_SHA,'package_sha256':r.PAYLOAD_SHA,'dataset_lock_sha256':r.DATASET_LOCK,'dataset_manifest_sha256':r.DATASET_MANIFEST,'r2_protocol_sha256':r.PROTOCOL,'thresholds':r.POINTS,'cv_inference':False,'m5a_inference':False,'risk_scoring':False,'training':False,'threshold_selection':False,'allowed_reads':r.READS,'source_hashes':source}
    return {**scope,'authorization_id':'synthetic','approval':'TRUNG_EVALUATION_ONLY_REPLAY','spec_sha256':'a'*64},scope


def test_valid_replay_authorization():
    record,spec=replay_record();r.validate_authorization(record,spec,'a'*64)


@pytest.mark.parametrize('field,value',[('approval',None),('parent_run_id','other'),('parent_manifest_sha256','b'*64),('lock_id','wrong'),('dataset_lock_sha256','b'*64),('r2_protocol_sha256','b'*64),('cv_inference',True),('m5a_inference',True),('risk_scoring',True),('training',True),('threshold_selection',True),('thresholds',{'CV':0.4})])
def test_invalid_replay_authorization_rejected(field,value):
    record,spec=replay_record();record[field]=value
    with pytest.raises(AuthorizationError):r.validate_authorization(record,spec,'a'*64)


def test_replay_record_cannot_authorize_benchmark():
    record,spec=replay_record()
    with pytest.raises(AuthorizationError):_validate_record(record,spec,'a'*64,{})


def test_missing_parent_or_wrong_manifest_rejected_before_read(tmp_path):
    with pytest.raises((AuthorizationError,FileNotFoundError)):r.verify_parent(tmp_path)
