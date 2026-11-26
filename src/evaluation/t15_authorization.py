"""T15-only fail-closed authorization before any Test semantic loader call.

Hashes are externally pinned and are not cryptographic signatures. Python-level
control is not an operating-system sandbox; only supported orchestration is in scope.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import secrets
import inspect
from contextlib import contextmanager
from src.release.offline_lock import verify_active,digest,LockError
from src.data.dataset_loader import DatasetLoader
from src.data.tensor_verification import checksum_dataset

TASK='AIT3040_S4_T15_TEST_DEVELOPMENT_BENCHMARK'
LOCK_ID='offline-t14-15980ed4f7255ddbdb943979'
LOCK_SHA='257e77a3a5ae2b2175926145cc0d3c483ccacdaf80f3479d9c352d69f8f6dcdc'
PAYLOAD_SHA='15980ed4f7255ddbdb943979df7dda320ac4ae448e24feb357fa51f3dd38dd79'
DATASET_LOCK='036d9c0e3652e526613238b91151002cbca35615552eba687b588da01b0fe764'
DATASET_MANIFEST='21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441'
CHECKPOINT='e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc'
POINTS={'CV':0.435,'M5a':0.42,'comparator':'>='}
_ISSUED={}
SOURCE_ROOT=Path(__file__).resolve().parents[2]

class AuthorizationError(ValueError):pass


@contextmanager
def _pre_gate_test_guard(dataset_root):
    """Hash-only guard around dataset verification; restores any outer Q1 guard."""
    import numpy as np
    import pandas as pd
    test=(Path(dataset_root).resolve()/'test').resolve();counts={'hash_opens':0,'blocked_deserialization':0,'blocked_other_opens':0}
    old_open=Path.open;old_load=np.load;old_csv=pd.read_csv;old_parquet=pd.read_parquet
    def is_test(value):
        if not isinstance(value,(str,Path)):return False
        try:return Path(value).resolve().is_relative_to(test)
        except (OSError,ValueError):return False
    def guarded_open(path,*args,**kwargs):
        if is_test(path):
            frame=inspect.currentframe();allowed=False
            while frame:
                if frame.f_code is checksum_dataset.__code__:allowed=True;break
                frame=frame.f_back
            if not allowed:counts['blocked_other_opens']+=1;raise AuthorizationError('pre-gate Test open denied')
            counts['hash_opens']+=1
        return old_open(path,*args,**kwargs)
    def checked(fn):
        def call(path,*args,**kwargs):
            if is_test(path):counts['blocked_deserialization']+=1;raise AuthorizationError('pre-gate Test deserialize denied')
            return fn(path,*args,**kwargs)
        return call
    try:
        Path.open=guarded_open;np.load=checked(old_load);pd.read_csv=checked(old_csv);pd.read_parquet=checked(old_parquet)
        yield counts
    finally:
        Path.open=old_open;np.load=old_load;pd.read_csv=old_csv;pd.read_parquet=old_parquet

@dataclass(frozen=True)
class VerifiedContext:
    token:str
    dataset_root:Path
    package_root:Path
    authorization_sha256:str
    protocol_sha256:str
    lock_sha256:str


def _require(condition,message):
    if not condition:raise AuthorizationError(message)


def _read_pinned_json(path,expected):
    _require(isinstance(expected,str) and len(expected)==64,'external identity pin required')
    path=Path(path)
    try:
        _require(digest(path)==expected,'pinned file identity mismatch')
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        _require(isinstance(value,dict),'expected JSON object')
        return value
    except (OSError,ValueError) as exc:raise AuthorizationError(str(exc)) from exc


def _validate_record(record,protocol,protocol_sha,lock):
    revision=protocol.get('protocol_status')=='FROZEN_TECHNICAL_REVISION'
    exact={'schema_version':2 if revision else 1,'task_id':TASK,'approval':'GRANTED','scope':'ONE_OFFLINE_FIXED_MODEL_TEST_BENCHMARK','split':'test','benchmark_classification':'REUSED_DEVELOPMENT_BENCHMARK','lock_id':LOCK_ID,'lock_manifest_sha256':LOCK_SHA,'package_sha256':PAYLOAD_SHA,'dataset_version':'final_dataset_1.0','dataset_lock_sha256':DATASET_LOCK,'dataset_manifest_sha256':DATASET_MANIFEST,'protocol_sha256':protocol_sha,'checkpoint_sha256':CHECKPOINT,'models':['CV','M5a'],'thresholds':POINTS,'production_approved':False,'retraining_authorized':False,'recalibration_authorized':False,'model_selection_authorized':False}
    _require(all(record.get(k)==v and (not isinstance(v,bool) or record.get(k) is v) for k,v in exact.items()),'authorization scope or identity mismatch')
    _require(isinstance(record.get('authorization_id'),str) and bool(record['authorization_id']) and isinstance(record.get('approval_reference'),str) and bool(record['approval_reference']),'missing explicit approval evidence')
    _require(protocol.get('protocol_status') in ('FROZEN_PRE_TEST_ACCESS','FROZEN_TECHNICAL_REVISION') and protocol.get('task_id')==TASK and protocol.get('allowed_split')=='test' and protocol.get('lock_id')==LOCK_ID and protocol.get('lock_manifest_sha256')==LOCK_SHA and protocol.get('package_sha256')==PAYLOAD_SHA and protocol.get('dataset_lock_sha256')==DATASET_LOCK and protocol.get('dataset_manifest_sha256')==DATASET_MANIFEST and protocol.get('checkpoint_sha256')==CHECKPOINT and protocol.get('thresholds')==POINTS,'protocol identity mismatch')
    if revision:
        _require(record.get('revision_approval')=='T15-R1-R5' and record.get('parent_run_id')=='s4_t15_20261125T141930Z_d5db93d9' and record.get('adapter_source_hashes')==protocol.get('adapter_source_hashes') and isinstance(record.get('adapter_source_hashes'),dict) and bool(record['adapter_source_hashes']),'revision authorization mismatch')
        for name,sha in record['adapter_source_hashes'].items():
            path=(SOURCE_ROOT/name).resolve();_require(path.is_relative_to(SOURCE_ROOT.resolve()) and digest(path)==sha,'adapter source identity mismatch')
    _require(lock['lock_id']==LOCK_ID and lock['package_identity']==PAYLOAD_SHA and lock['model_lock'] is True and lock['lock_scope']=='OFFLINE_PROTOTYPE' and lock['test_benchmark_authorized'] is False and lock['production_approved'] is False and lock['model']['checkpoint_sha256']==CHECKPOINT,'active lock identity mismatch')
    _require(lock['operating_points']=={'CV':{'grid_index':87,'threshold':0.435},'M5a':{'grid_index':84,'threshold':0.42},'comparator':'>='},'lock thresholds mismatch')


def establish(*,authorization_path,expected_authorization_sha256,protocol_path,expected_protocol_sha256,package_root,expected_lock_sha256,dataset_root,task_id,split,pre_access_evidence_path,expected_pre_access_evidence_sha256):
    """Hash-only Test access; returns context only after all checks pass."""
    _require(task_id==TASK and split=='test','unauthorized task or split')
    _require(expected_lock_sha256==LOCK_SHA,'external lock pin mismatch')
    record=_read_pinned_json(authorization_path,expected_authorization_sha256)
    protocol=_read_pinned_json(protocol_path,expected_protocol_sha256)
    evidence=_read_pinned_json(pre_access_evidence_path,expected_pre_access_evidence_sha256)
    required=('authorization_negative_tests','authorization_positive_test','trusted_test_adapter_tests','metric_boundary_tests','release_integrity_tests','full_regression','q1_no_test_deserialization')
    _require(all(evidence.get(key) is True for key in required),'pre-access test evidence incomplete')
    hashes=evidence.get('source_hashes');proof=evidence.get('test_evidence_files')
    _require(isinstance(hashes,dict) and bool(hashes) and isinstance(proof,dict) and bool(proof),'missing pinned source/test evidence')
    for rel,sha in hashes.items():
        path=(SOURCE_ROOT/rel).resolve();_require(path.is_relative_to(SOURCE_ROOT.resolve()) and digest(path)==sha,'T15 source changed after pre-access tests')
    for name,sha in proof.items():_require(digest(Path(name))==sha,'test evidence changed after verification')
    if protocol.get('protocol_status')=='FROZEN_TECHNICAL_REVISION':
        audit=evidence.get('metadata_audit')
        _require(isinstance(audit,dict) and isinstance(audit.get('path'),str) and isinstance(audit.get('sha256'),str),'missing metadata provenance evidence')
        provenance=_read_pinned_json(audit['path'],audit['sha256'])
        _require(provenance.get('status')=='PASS' and provenance.get('encounters')==1320 and provenance.get('history_rows')==26400,'metadata provenance verification failed')
    try:lock=verify_active(package_root,expected_lock_sha256)
    except (LockError,OSError,ValueError) as exc:raise AuthorizationError('active lock verification failed: '+str(exc)) from exc
    _validate_record(record,protocol,expected_protocol_sha256,lock)
    try:
        with _pre_gate_test_guard(dataset_root) as access:
            loader=DatasetLoader(dataset_root)
            _require(digest(loader.root/'DATASET_LOCK_MANIFEST.json')==DATASET_LOCK,'dataset lock mismatch')
            checksum=checksum_dataset(loader.root,loader.lock)
            _require(checksum['files_verified']==93 and checksum['manifest_sha256']==DATASET_MANIFEST,'dataset checksum mismatch')
        _require(access['blocked_deserialization']==0 and access['blocked_other_opens']==0,'pre-gate Test access violation')
    except (OSError,ValueError) as exc:raise AuthorizationError('dataset verification failed: '+str(exc)) from exc
    token=secrets.token_hex(32);ctx=VerifiedContext(token,Path(loader.root).resolve(),Path(package_root).resolve(),expected_authorization_sha256,expected_protocol_sha256,expected_lock_sha256)
    return ctx,{'status':'PASS','task_id':TASK,'split':'test','authorization_id':record['authorization_id'],'authorization_sha256':expected_authorization_sha256,'protocol_sha256':expected_protocol_sha256,'pre_access_evidence_sha256':expected_pre_access_evidence_sha256,'lock_sha256':expected_lock_sha256,'package_sha256':PAYLOAD_SHA,'dataset_checksum':checksum,'pre_access_guard':access,'pre_access_test_content_deserialized':False,'test_semantic_access_authorized_after_report':True,'production_approved':False,'guard_limit':'Python-level control is not an OS sandbox'}


def verify_context(ctx):
    _require(isinstance(ctx,VerifiedContext) and _ISSUED.get(ctx.token) is ctx,'cached, forged or unverified context')
    return ctx


def run_gated(*,report_path,loader,**authorization):
    """Write gate report durably before calling the single supported loader."""
    ctx,report=establish(**authorization)
    path=Path(report_path);_require(not path.exists(),'pre-access report already exists')
    raw=(json.dumps(report,indent=2,ensure_ascii=False)+'\n').encode('utf8')
    with path.open('xb') as f:
        f.write(raw);f.flush()
        import os
        os.fsync(f.fileno())
    sha=hashlib.sha256(raw).hexdigest();pin=path.with_suffix(path.suffix+'.sha256')
    with pin.open('x',encoding='ascii') as f:
        f.write(sha+'\n');f.flush()
        import os
        os.fsync(f.fileno())
    _ISSUED[ctx.token]=ctx
    verify_context(ctx)
    return loader(ctx),report,sha
