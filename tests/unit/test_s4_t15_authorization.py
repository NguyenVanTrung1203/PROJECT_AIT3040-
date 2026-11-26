import json
from pathlib import Path
import pytest
from src.evaluation import t15_authorization as a
from src.evaluation import t15_trusted_test as t


def fixture(tmp_path,monkeypatch):
    ds=tmp_path/'dataset';ds.mkdir();(ds/'DATASET_LOCK_MANIFEST.json').write_text('synthetic-lock');dh=a.digest(ds/'DATASET_LOCK_MANIFEST.json');monkeypatch.setattr(a,'DATASET_LOCK',dh)
    events=[]
    class Loader:
        def __init__(self,root):events.append('dataset_metadata');self.root=Path(root);self.lock={}
    def checksum(root,lock):events.append('dataset_hash');return {'files_verified':93,'manifest_sha256':a.DATASET_MANIFEST}
    lock={'lock_id':a.LOCK_ID,'package_identity':a.PAYLOAD_SHA,'model_lock':True,'lock_scope':'OFFLINE_PROTOTYPE','test_benchmark_authorized':False,'production_approved':False,'model':{'checkpoint_sha256':a.CHECKPOINT},'operating_points':{'CV':{'grid_index':87,'threshold':.435},'M5a':{'grid_index':84,'threshold':.42},'comparator':'>='}}
    def verify(package,pin):events.append('verify_lock');assert pin==a.LOCK_SHA;return lock
    monkeypatch.setattr(a,'DatasetLoader',Loader);monkeypatch.setattr(a,'checksum_dataset',checksum);monkeypatch.setattr(a,'verify_active',verify)
    proto={'protocol_status':'FROZEN_PRE_TEST_ACCESS','task_id':a.TASK,'allowed_split':'test','lock_id':a.LOCK_ID,'lock_manifest_sha256':a.LOCK_SHA,'package_sha256':a.PAYLOAD_SHA,'dataset_lock_sha256':dh,'dataset_manifest_sha256':a.DATASET_MANIFEST,'checkpoint_sha256':a.CHECKPOINT,'thresholds':a.POINTS}
    pp=tmp_path/'protocol.json';pp.write_text(json.dumps(proto));ps=a.digest(pp)
    record={'schema_version':1,'task_id':a.TASK,'approval':'GRANTED','scope':'ONE_OFFLINE_FIXED_MODEL_TEST_BENCHMARK','split':'test','benchmark_classification':'REUSED_DEVELOPMENT_BENCHMARK','lock_id':a.LOCK_ID,'lock_manifest_sha256':a.LOCK_SHA,'package_sha256':a.PAYLOAD_SHA,'dataset_version':'final_dataset_1.0','dataset_lock_sha256':dh,'dataset_manifest_sha256':a.DATASET_MANIFEST,'protocol_sha256':ps,'checkpoint_sha256':a.CHECKPOINT,'models':['CV','M5a'],'thresholds':a.POINTS,'production_approved':False,'retraining_authorized':False,'recalibration_authorized':False,'model_selection_authorized':False,'authorization_id':'synthetic','approval_reference':'synthetic explicit approval'}
    ap=tmp_path/'authorization.json';ap.write_text(json.dumps(record));dummy=tmp_path/'source.py';dummy.write_text('synthetic');proof=tmp_path/'test.log';proof.write_text('synthetic pass');monkeypatch.setattr(a,'SOURCE_ROOT',tmp_path);contents={k:True for k in ('authorization_negative_tests','authorization_positive_test','trusted_test_adapter_tests','metric_boundary_tests','release_integrity_tests','full_regression','q1_no_test_deserialization')};contents.update(source_hashes={'source.py':a.digest(dummy)},test_evidence_files={str(proof):a.digest(proof)});evidence=tmp_path/'evidence.json';evidence.write_text(json.dumps(contents));args={'authorization_path':ap,'expected_authorization_sha256':a.digest(ap),'protocol_path':pp,'expected_protocol_sha256':ps,'package_root':tmp_path/'package','expected_lock_sha256':a.LOCK_SHA,'dataset_root':ds,'task_id':a.TASK,'split':'test','pre_access_evidence_path':evidence,'expected_pre_access_evidence_sha256':a.digest(evidence)}
    return args,record,lock,events


def test_positive_gate_report_durable_before_loader(tmp_path,monkeypatch):
    args,record,lock,events=fixture(tmp_path,monkeypatch);report=tmp_path/'pre_access.json'
    def loader(ctx):
        assert report.is_file() and report.with_suffix('.json.sha256').is_file();a.verify_context(ctx);events.append('semantic_loader');return 'loaded'
    output,evidence,sha=a.run_gated(report_path=report,loader=loader,**args)
    assert output=='loaded' and evidence['status']=='PASS' and sha==a.digest(report)
    assert events==['verify_lock','dataset_metadata','dataset_hash','semantic_loader']


@pytest.mark.parametrize('field,value',[('approval','MISSING'),('lock_id','bad'),('lock_manifest_sha256','0'*64),('package_sha256','0'*64),('dataset_version','wrong'),('dataset_manifest_sha256','0'*64),('protocol_sha256','0'*64),('checkpoint_sha256','0'*64),('split','validation'),('scope','ALL'),('production_approved',True),('recalibration_authorized',True),('thresholds',{'CV':.435,'M5a':.421,'comparator':'>='}),('thresholds',{'CV':.435,'M5a':.42,'comparator':'>'})])
def test_invalid_record_never_calls_test_loader(tmp_path,monkeypatch,field,value):
    args,record,lock,events=fixture(tmp_path,monkeypatch);record[field]=value;args['authorization_path'].write_text(json.dumps(record));args['expected_authorization_sha256']=a.digest(args['authorization_path']);calls=[]
    with pytest.raises(a.AuthorizationError):a.run_gated(report_path=tmp_path/'r.json',loader=lambda c:calls.append(c),**args)
    assert not calls and not (tmp_path/'r.json').exists()


@pytest.mark.parametrize('mutation',['missing','tampered','external_pin','wrong_split','wrong_task','protocol_hash','unlocked','dataset_lock'])
def test_gate_rejects_before_loader(tmp_path,monkeypatch,mutation):
    args,record,lock,events=fixture(tmp_path,monkeypatch);calls=[]
    if mutation=='missing':args['authorization_path'].unlink()
    elif mutation=='tampered':args['authorization_path'].write_text('{}')
    elif mutation=='external_pin':args['expected_lock_sha256']='0'*64
    elif mutation=='wrong_split':args['split']='validation'
    elif mutation=='wrong_task':args['task_id']='wrong'
    elif mutation=='protocol_hash':args['expected_protocol_sha256']='0'*64
    elif mutation=='unlocked':lock['model_lock']=False
    else:(args['dataset_root']/'DATASET_LOCK_MANIFEST.json').write_text('changed')
    with pytest.raises(a.AuthorizationError):a.run_gated(report_path=tmp_path/'r.json',loader=lambda c:calls.append(c),**args)
    assert not calls and not (tmp_path/'r.json').exists()


def test_direct_loader_rejects_forged_context(tmp_path):
    forged=a.VerifiedContext('forged',tmp_path,tmp_path,'0'*64,'0'*64,'0'*64)
    with pytest.raises(a.AuthorizationError):t.load_authorized_test(forged)
    with pytest.raises(a.AuthorizationError):t.make_authorized_batch(object(),0,1)


def test_source_adaptation_changes_only_size_constants():
    import inspect
    import hashlib
    text=inspect.getsource(t.offline.validate_history)
    assert text.count('n == 835 and v == 1670')==1
    checker=t._adapt_history_validator(1320,2640)
    assert callable(checker) and checker.__code__.co_filename=='<T11-history-test-adaptation>'
    assert checker.__globals__['SOURCE_MAP']==t.TEST_SOURCES
    assert hashlib.sha256(Path(t.offline.__file__).read_bytes()).hexdigest()=='b4732d93f459a2c906308ef4d96e2f92d4474ef17007b9d08b2740f4710cc30f'
    assert inspect.getsource(t.offline.make_batch).count('SOURCE_MAP[x]')==1


def synthetic_history():
    import numpy as np
    import pandas as pd
    from types import SimpleNamespace
    from scripts.verify_feature_contract import common_en,velocity_en
    anchor=pd.Timestamp('2026-01-01T00:00:00Z');rows=[]
    for slot,vid,lat in [('A','a',55.0),('B','b',55.001)]:
        for minute in range(-9,1):
            ts=anchor+pd.Timedelta(minutes=minute)
            rows.append({'encounter_id':'e','vessel':slot,'vessel_id':vid,'timestamp_utc':ts,'anchor_timestamp':anchor,'relative_minute':minute,'is_history':True,'is_future':False,'SOG':5.,'COG':0.,'LAT':lat,'LON':10.,'data_source':'synthetic_ais_denmark_oct2025','split':'test','original_source_timestamp_utc':ts-pd.Timedelta(days=3,seconds=30),'simulated_source_timestamp_utc':ts-pd.Timedelta(seconds=30),'source_track_id':'track-'+vid})
    h=pd.DataFrame(rows);vals=h[['LAT','LON','SOG','COG']].to_numpy(dtype=np.float64).reshape(2,10,4);X=np.zeros((2,10,4),dtype=np.float32);X[:,:,2:]=velocity_en(vals[:,:,2],vals[:,:,3]);en=common_en(vals[:,9,0],vals[:,9,1],55.,10.);anchors=en.reshape(1,2,2).astype(np.float64)
    s=SimpleNamespace(X=X,anchors=anchors,pairs=np.array([[0,1]]),encounters=pd.DataFrame({'encounter_id':['e']}),vessels=pd.DataFrame({'encounter_id':['e','e'],'vessel':['A','B'],'vessel_id':['a','b'],'X_row':[0,1],'data_source':['synthetic_ais_denmark_oct2025']*2}),metadata=pd.DataFrame({'data_source':['synthetic_ais_denmark_oct2025'],'anchor_timestamp':[anchor]}))
    return s,h


def test_adapted_history_validates_synthetic_and_rejects_wrong_ab():
    import numpy as np
    from copy import copy
    from src.inference.m5a_wrapper import InferenceError
    s,h=synthetic_history();checker=t._adapt_history_validator(1,2);assert len(checker(s,h))==20
    bad=copy(s);bad.pairs=np.array([[1,0]])
    with pytest.raises(InferenceError):checker(bad,h)
    h.loc[0,'vessel_id']='tampered'
    with pytest.raises(InferenceError):checker(s,h)


def test_adapted_history_rejects_future_timestamp():
    import pandas as pd
    from src.inference.m5a_wrapper import InferenceError
    s,h=synthetic_history();h.loc[0,'timestamp_utc']=h.loc[0,'anchor_timestamp']+pd.Timedelta(minutes=1)
    with pytest.raises(InferenceError):t._adapt_history_validator(1,2)(s,h)


@pytest.mark.parametrize('invalid', ['missing_original','missing_simulated','future_source','stale_source','validation_source'])
def test_adapted_synthetic_rejects_invalid_provenance(invalid):
    import pandas as pd
    from src.inference.m5a_wrapper import InferenceError
    s,h=synthetic_history()
    if invalid=='missing_original':h.loc[0,'original_source_timestamp_utc']=pd.NaT
    elif invalid=='missing_simulated':h.loc[0,'simulated_source_timestamp_utc']=pd.NaT
    elif invalid=='future_source':h.loc[0,'simulated_source_timestamp_utc']=h.loc[0,'timestamp_utc']+pd.Timedelta(seconds=1)
    elif invalid=='stale_source':h.loc[0,'simulated_source_timestamp_utc']=h.loc[0,'timestamp_utc']-pd.Timedelta(seconds=61)
    else:h.loc[0,'data_source']='augmented_real_ais_kattegat_v3'
    with pytest.raises(InferenceError):t._adapt_history_validator(1,2)(s,h)


def test_fixed_d2_policy_and_boundaries():
    from src.evaluation.t15_benchmark import fixed_d2_status
    assert fixed_d2_status('D1_FAIL','D1_PASS','D2_PASS')=='D2_CONDITIONAL'
    assert fixed_d2_status('D1_FAIL','D1_PASS','D2_FAIL')=='D2_FAIL'
    assert fixed_d2_status('D1_PASS','D1_FAIL','D2_PASS')=='D2_FAIL'
    assert fixed_d2_status('D1_INCONCLUSIVE','D1_PASS','D2_PASS')=='D2_BLOCKED'
    assert fixed_d2_status('D1_PASS','D1_PASS','D2_PASS')=='D2_PASS'


def test_established_context_not_usable_until_report_is_durable(tmp_path,monkeypatch):
    args,record,lock,events=fixture(tmp_path,monkeypatch);ctx,_=a.establish(**args)
    with pytest.raises(a.AuthorizationError):t.load_authorized_test(ctx)


def test_pre_gate_guard_rejects_test_deserialization_before_open(tmp_path):
    import numpy as np
    with a._pre_gate_test_guard(tmp_path) as events:
        with pytest.raises(a.AuthorizationError):np.load(tmp_path/'test'/'tensors'/'labels.npy')
    assert events['blocked_deserialization']==1 and events['hash_opens']==0


def test_pre_access_source_tamper_blocks_loader(tmp_path,monkeypatch):
    args,record,lock,events=fixture(tmp_path,monkeypatch);(tmp_path/'source.py').write_text('tampered');called=[]
    with pytest.raises(a.AuthorizationError,match='source changed'):a.run_gated(report_path=tmp_path/'r.json',loader=lambda c:called.append(c),**args)
    assert not called and not (tmp_path/'r.json').exists()


def test_pre_access_evidence_tamper_blocks_loader(tmp_path,monkeypatch):
    args,record,lock,events=fixture(tmp_path,monkeypatch);(tmp_path/'test.log').write_text('tampered');called=[]
    with pytest.raises(a.AuthorizationError,match='test evidence changed'):a.run_gated(report_path=tmp_path/'r.json',loader=lambda c:called.append(c),**args)
    assert not called


def test_revision_requires_new_authorization_and_exact_adapter(tmp_path,monkeypatch):
    args,record,lock,events=fixture(tmp_path,monkeypatch)
    protocol=json.loads(args['protocol_path'].read_text());protocol['protocol_status']='FROZEN_TECHNICAL_REVISION';protocol['adapter_source_hashes']={'source.py':a.digest(tmp_path/'source.py')}
    args['protocol_path'].write_text(json.dumps(protocol));args['expected_protocol_sha256']=a.digest(args['protocol_path'])
    with pytest.raises(a.AuthorizationError):a._validate_record(record,protocol,args['expected_protocol_sha256'],lock)
    record.update(schema_version=2,protocol_sha256=args['expected_protocol_sha256'],revision_approval='T15-R1-R5',parent_run_id='s4_t15_20261125T141930Z_d5db93d9',adapter_source_hashes=protocol['adapter_source_hashes'])
    a._validate_record(record,protocol,args['expected_protocol_sha256'],lock)
    (tmp_path/'source.py').write_text('different')
    with pytest.raises(a.AuthorizationError,match='adapter source identity mismatch'):a._validate_record(record,protocol,args['expected_protocol_sha256'],lock)
