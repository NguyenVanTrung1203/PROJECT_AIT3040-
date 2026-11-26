"""Fail-closed integrity checks for the conditional offline release only.

Checksums are not signatures. The caller must independently pin the expected
manifest SHA-256. This module is not a runtime, T15 or production authorization.
"""
from pathlib import Path
import hashlib
import json
import os

STATUS='CONDITIONAL_TECHNICAL_LOCK'
MANIFEST='model_lock_manifest.json'
DETACHED='model_lock_manifest.sha256'
PAYLOAD='package_payload.json'
REQUIRED_GATES=('prelock_evidence','artifact_verifier','package_import','validation_parity','negative_integrity','regression','test_boundary','contract_integrity')

class LockError(ValueError):
    pass

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def canonical(data):return json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')

def safe_file(root,relative):
    if not isinstance(relative,str) or not relative or '\\' in relative:raise LockError('invalid payload path')
    p=Path(relative)
    if p.is_absolute() or any(part in ('..','.') for part in p.parts):raise LockError('path traversal')
    q=root/p
    for parent in (q,*q.parents):
        if parent==root.parent:break
        if parent.is_symlink():raise LockError('symlink forbidden')
    if not q.is_file() or not q.resolve().is_relative_to(root.resolve()):raise LockError('missing or escaping file: '+relative)
    return q

def verify_payload(root,expected_sha):
    root=Path(root).resolve();p=safe_file(root,PAYLOAD)
    if digest(p)!=expected_sha:raise LockError('payload index hash mismatch')
    d=json.loads(p.read_text(encoding='utf8'))
    if d.get('version')!=1 or not isinstance(d.get('files'),dict) or not d['files']:raise LockError('invalid payload index')
    actual=set()
    for item in root.rglob('*'):
        if item.is_symlink():raise LockError('symlink forbidden')
        if item.is_file():
            name=item.relative_to(root).as_posix()
            if name not in (PAYLOAD,MANIFEST,DETACHED):actual.add(name)
    if actual!=set(d['files']):raise LockError('payload inventory mismatch')
    for rel,expected in d['files'].items():
        if digest(safe_file(root,rel))!=expected:raise LockError('payload hash mismatch: '+rel)
    return d

def validate_manifest_values(m):
    if not isinstance(m,dict) or m.get('document_type')!='ACTUAL_OFFLINE_MODEL_LOCK' or m.get('schema_version')!=1:raise LockError('not an active lock manifest')
    required={'model_lock':True,'release_status':STATUS,'lock_scope':'OFFLINE_PROTOTYPE','test_benchmark_authorized':False,'production_approved':False,'runtime_integration_approved':False,'final_approval':'GRANTED'}
    if any(m.get(k)!=v for k,v in required.items()):raise LockError('invalid authorization state')
    if m.get('approved_decisions')!=27 or m.get('operating_points')!={'CV':{'grid_index':87,'threshold':0.435},'M5a':{'grid_index':84,'threshold':0.42},'comparator':'>='}:raise LockError('invalid decision or threshold identity')
    if m.get('package_identity')!=m.get('payload_sha256') or m.get('lock_id')!='offline-t14-'+str(m.get('payload_sha256',''))[:24]:raise LockError('invalid lock identity')
    if m.get('state_history')!=['CANDIDATE','CALIBRATED_CANDIDATE',STATUS]:raise LockError('invalid state transition')
    gates=m.get('validation_gates',{})
    if any(gates.get(k) is not True for k in REQUIRED_GATES):raise LockError('mandatory validation gate missing')
    return m

def verify_active(root,expected_manifest_sha256):
    root=Path(root).resolve()
    if not isinstance(expected_manifest_sha256,str) or len(expected_manifest_sha256)!=64:raise LockError('external manifest pin required')
    manifest=safe_file(root,MANIFEST);detached=safe_file(root,DETACHED)
    actual=digest(manifest)
    if actual!=expected_manifest_sha256 or detached.read_text(encoding='ascii').strip()!=actual:raise LockError('manifest identity mismatch')
    m=validate_manifest_values(json.loads(manifest.read_text(encoding='utf8')))
    verify_payload(root,m['payload_sha256'])
    return m

def verify_staging(root,payload_sha,gates):
    root=Path(root).resolve()
    if (root/MANIFEST).exists() or (root/DETACHED).exists():raise LockError('staging already active')
    if any(gates.get(k) is not True for k in REQUIRED_GATES):raise LockError('mandatory validation gate missing')
    verify_payload(root,payload_sha)
    return True
