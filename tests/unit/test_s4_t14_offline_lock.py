import hashlib,json
from pathlib import Path
import pytest
from src.release.offline_lock import (LockError,canonical,digest,verify_payload,verify_staging,verify_active,validate_manifest_values,REQUIRED_GATES)


def stage(tmp_path):
    (tmp_path/'snapshot').mkdir();(tmp_path/'snapshot'/'model.pt').write_bytes(b'model');(tmp_path/'snapshot'/'scaler.json').write_bytes(b'scaler')
    payload={'version':1,'files':{'snapshot/model.pt':digest(tmp_path/'snapshot'/'model.pt'),'snapshot/scaler.json':digest(tmp_path/'snapshot'/'scaler.json')}}
    (tmp_path/'package_payload.json').write_bytes(canonical(payload));h=digest(tmp_path/'package_payload.json');gates={k:True for k in REQUIRED_GATES}
    return h,gates


def active(tmp_path):
    h,gates=stage(tmp_path);m={'document_type':'ACTUAL_OFFLINE_MODEL_LOCK','schema_version':1,'model_lock':True,'release_status':'CONDITIONAL_TECHNICAL_LOCK','lock_scope':'OFFLINE_PROTOTYPE','test_benchmark_authorized':False,'production_approved':False,'runtime_integration_approved':False,'final_approval':'GRANTED','approved_decisions':27,'operating_points':{'CV':{'grid_index':87,'threshold':.435},'M5a':{'grid_index':84,'threshold':.42},'comparator':'>='},'package_identity':h,'payload_sha256':h,'lock_id':'offline-t14-'+h[:24],'state_history':['CANDIDATE','CALIBRATED_CANDIDATE','CONDITIONAL_TECHNICAL_LOCK'],'validation_gates':gates}
    (tmp_path/'model_lock_manifest.json').write_bytes(canonical(m));mh=digest(tmp_path/'model_lock_manifest.json');(tmp_path/'model_lock_manifest.sha256').write_text(mh+'\n',encoding='ascii');return m,mh


def test_staging_not_active_and_requires_all_gates(tmp_path):
    h,gates=stage(tmp_path);assert verify_staging(tmp_path,h,gates)
    with pytest.raises(LockError):verify_active(tmp_path,'0'*64)
    gates['validation_parity']=False
    with pytest.raises(LockError):verify_staging(tmp_path,h,gates)


def test_lock_requires_external_pin_and_rechecks_all_files(tmp_path):
    _,mh=active(tmp_path);assert verify_active(tmp_path,mh)['model_lock']
    with pytest.raises(LockError):verify_active(tmp_path,'0'*64)
    (tmp_path/'snapshot'/'model.pt').write_bytes(b'tampered')
    with pytest.raises(LockError,match='payload hash'):verify_active(tmp_path,mh)


@pytest.mark.parametrize('field,value',[('final_approval','NOT_GRANTED'),('test_benchmark_authorized',True),('production_approved',True),('runtime_integration_approved',True),('release_status','CANDIDATE'),('lock_scope','PRODUCTION'),('document_type','REVIEW_ONLY_PROPOSED_INVENTORY'),('lock_id','bad'),('approved_decisions',26)])
def test_manifest_rejects_invalid_approval_identity_or_authorization(tmp_path,field,value):
    m,_=active(tmp_path);m[field]=value
    with pytest.raises(LockError):validate_manifest_values(m)


def test_manifest_rejects_threshold_override_and_illegal_history(tmp_path):
    m,_=active(tmp_path);m['operating_points']['M5a']['threshold']=.421
    with pytest.raises(LockError):validate_manifest_values(m)


def test_reject_missing_scaler_and_manifest_mutation(tmp_path):
    _,mh=active(tmp_path);(tmp_path/'snapshot'/'scaler.json').unlink()
    with pytest.raises(LockError):verify_active(tmp_path,mh)
    (tmp_path/'model_lock_manifest.json').write_text('{}')
    with pytest.raises(LockError):verify_active(tmp_path,mh)


def test_reject_traversal_and_symlink_payload(tmp_path):
    h,_=stage(tmp_path);p=tmp_path/'package_payload.json';p.write_bytes(canonical({'version':1,'files':{'../escape':'0'*64}}))
    with pytest.raises(LockError):verify_payload(tmp_path,digest(p))


def test_illegal_state_transition_rejected(tmp_path):
    m,_=active(tmp_path);m['state_history']=['CANDIDATE','CONDITIONAL_TECHNICAL_LOCK']
    with pytest.raises(LockError):validate_manifest_values(m)


def test_unlisted_file_invalidates_active_lock(tmp_path):
    _,mh=active(tmp_path);(tmp_path/'snapshot'/'unexpected.py').write_text('unexpected')
    with pytest.raises(LockError,match='inventory mismatch'):verify_active(tmp_path,mh)


@pytest.mark.parametrize('mutation',['missing','checkpoint','scaler','manifest'])
def test_full_t11_verifier_rejects_damaged_artifact_copy(tmp_path,mutation):
    import shutil
    from src.inference.m5a_wrapper import verify_artifacts,InferenceError
    source=Path(__file__).resolve().parents[2]/'artifacts/checkpoints/s3_t10_20261124_seed20261110_run01'
    destination=tmp_path/'artifacts';shutil.copytree(source,destination)
    assert len(verify_artifacts(destination))==12
    targets={'missing':'validation_metrics.json','checkpoint':'best_model.pt','scaler':'x_scaler.json','manifest':'checksums.sha256'}
    target=destination/targets[mutation]
    if mutation=='missing':target.unlink()
    else:target.write_bytes(target.read_bytes()+b'\x00')
    with pytest.raises(InferenceError):
        verify_artifacts(destination)
