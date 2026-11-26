import json
import numpy as np
import pytest
from src.evaluation.t15_full_access_audit import Audit,AuditError,verify_events,supported_path_guard


def events(path):return [json.loads(line) for line in path.read_text().splitlines()]


def test_mapping_distinct_from_value_copy_and_exact_values(tmp_path):
    source=np.arange(24,dtype=np.float32).reshape(2,3,4);p=tmp_path/'x.npy';np.save(p,source)
    log=tmp_path/'events.jsonl';audit=Audit(log,'run','auth','protocol');out=audit.materialize_npy(p,'input','X',expected_shape=source.shape,expected_dtype='float32')
    assert np.array_equal(out,source) and out.dtype==source.dtype and out.flags.owndata and not isinstance(out,np.memmap)
    ev=events(log);assert [x['event_type'] for x in ev]==['FILE_OPEN_ATTEMPTED','MEMORY_MAP_CREATED','SEMANTIC_READ_ATTEMPTED','MATERIALIZATION_COMPLETED','SEMANTIC_VALUE_ACCESS_OBSERVED']
    coverage={'shape':[2,3,4],'dtype':'float32','logical_values':24,'selection':'all'}
    assert verify_events(ev,{'X':coverage},audit.identity)['status']=='PASS'


def test_failure_is_durable_without_observed(tmp_path):
    log=tmp_path/'e.jsonl';a=Audit(log,'run','auth','protocol')
    with pytest.raises(FileNotFoundError):a.materialize_npy(tmp_path/'none.npy','input','X',expected_shape=(1,),expected_dtype='float32')
    assert [x['event_type'] for x in events(log)]==['FILE_OPEN_ATTEMPTED','READ_FAILED']


@pytest.mark.parametrize('mutation',['missing','map_only','observed_before_attempt','wrong_identity','duplicate','partial','unexpected','contradictory'])
def test_completeness_rejects_invalid_evidence(tmp_path,mutation):
    p=tmp_path/'x.npy';np.save(p,np.arange(4,dtype=np.float32));log=tmp_path/'e.jsonl';a=Audit(log,'run','auth','protocol');a.materialize_npy(p,'input','X',expected_shape=(4,),expected_dtype='float32');ev=events(log)
    if mutation=='missing':ev=ev[:-1]
    elif mutation=='map_only':ev=ev[:2]
    elif mutation=='observed_before_attempt':ev[-1],ev[-2]=ev[-2],ev[-1]
    elif mutation=='wrong_identity':ev[-1]['authorization_id']='other'
    elif mutation=='duplicate':ev.append(dict(ev[-1]))
    elif mutation=='partial':ev[-1]['coverage']['logical_values']=3
    elif mutation=='unexpected':ev[-1]['category']='other'
    else:ev.append({**ev[-1],'event_id':'unique','event_type':'READ_FAILED'})
    requirement={'X':{'shape':[4],'dtype':'float32','logical_values':4,'selection':'all'}}
    assert verify_events(ev,requirement,a.identity)['status']=='FAIL'


def test_read_success_survives_downstream_error(tmp_path):
    log=tmp_path/'e.jsonl';a=Audit(log,'run','auth','protocol')
    assert a.read('eval','future',lambda:[1],coverage={'rows':1},operation='decode')==[1]
    with pytest.raises(RuntimeError):raise RuntimeError('later validation failed')
    assert verify_events(events(log),{'future':{'rows':1}},a.identity)['status']=='PASS'


def test_materialization_failure_does_not_emit_success(tmp_path,monkeypatch):
    import src.evaluation.t15_full_access_audit as m
    p=tmp_path/'x.npy';np.save(p,np.arange(4,dtype=np.float32));log=tmp_path/'e.jsonl';a=Audit(log,'run','auth','protocol')
    def fail(*args,**kwargs):raise RuntimeError('copy failure')
    monkeypatch.setattr(m.np,'array',fail)
    with pytest.raises(RuntimeError):a.materialize_npy(p,'input','X',expected_shape=(4,),expected_dtype='float32')
    types=[e['event_type'] for e in events(log)];assert types[-1]=='READ_FAILED' and 'SEMANTIC_VALUE_ACCESS_OBSERVED' not in types


def test_observed_write_failure_stops_before_consumption(tmp_path,monkeypatch):
    a=Audit(tmp_path/'log','run','auth','protocol');original=a.emit;read=[]
    def emit(phase,category,event_type,*args,**kwargs):
        if event_type=='SEMANTIC_VALUE_ACCESS_OBSERVED':raise OSError('audit persistence failed')
        return original(phase,category,event_type,*args,**kwargs)
    monkeypatch.setattr(a,'emit',emit)
    with pytest.raises(OSError):a.read('evaluation','future',lambda:read.append(1) or [1],coverage={'rows':1},operation='decode')
    assert read==[1] and [e['event_type'] for e in events(a.path)]==['SEMANTIC_READ_ATTEMPTED','MATERIALIZATION_COMPLETED']


def test_write_failure_stops_before_read(tmp_path,monkeypatch):
    a=Audit(tmp_path/'missing'/'log','run','auth','protocol');calls=[]
    with pytest.raises(FileNotFoundError):a.read('eval','future',lambda:calls.append(1),coverage={},operation='decode')
    assert not calls


def test_full_authorization_and_old_scopes_rejected():
    from src.evaluation.t15_full_authorization import validate_full_scope
    from src.evaluation.t15_authorization import AuthorizationError
    r={'full_approval':'C1-C5','full_scope':'AUDITED_FULL_TECHNICAL_RERUN','parent_r2_run':'s4_t15_r2_20261125T152141Z_2cd800cd','audit_inventory_sha256':'a'*64}
    p={'revision_classification':'TECHNICAL_ACCESS_AUDIT_CORRECTION','audit_inventory_sha256':'a'*64}
    keys=('synthetic_end_to_end','synthetic_negative_audit_tests','audit_completeness_verifier','materialization_semantics','q1_no_test_deserialization','full_regression');e={k:True for k in keys}
    validate_full_scope(r,p,e,'a'*64)
    for changed in ({},{**r,'full_scope':'R2_EVALUATION_REPLAY_ONLY'},{**r,'full_scope':'TEST_HISTORY_METADATA_AUDIT_ONLY'},{**r,'full_approval':'R1-R5'}):
        with pytest.raises(AuthorizationError):validate_full_scope(changed,p,e,'a'*64)
    with pytest.raises(AuthorizationError):validate_full_scope(r,p,{**e,'synthetic_end_to_end':False},'a'*64)


@pytest.mark.parametrize('category',['X','anchors','future'])
def test_missing_specific_required_value_observation_rejected(tmp_path,category):
    log=tmp_path/'events.jsonl';a=Audit(log,'run','auth','protocol')
    for name in ('X','anchors','future'):a.read('input' if name!='future' else 'evaluation',name,lambda:[1],coverage={'rows':1},operation='synthetic')
    ev=[e for e in events(log) if not (e['category']==category and e['event_type']=='SEMANTIC_VALUE_ACCESS_OBSERVED')]
    assert verify_events(ev,{k:{'rows':1} for k in ('X','anchors','future')},a.identity)['status']=='FAIL'


def test_observed_before_completed_operation_rejected(tmp_path):
    log=tmp_path/'events.jsonl';a=Audit(log,'run','auth','protocol');a.read('input','X',lambda:[1],coverage={'rows':1},operation='synthetic')
    ev=events(log);ev[1],ev[2]=ev[2],ev[1]
    assert verify_events(ev,{'X':{'rows':1}},a.identity)['status']=='FAIL'


def test_synthetic_three_source_phase_separated_input_boundary(tmp_path,monkeypatch,request):
    import pandas as pd
    from types import SimpleNamespace
    from scripts.verify_feature_contract import common_en,velocity_en
    from src.evaluation import t15_full_data_boundary as b
    root=tmp_path/'synthetic_data';d=root/'test'/'data';t=root/'test'/'tensors';d.mkdir(parents=True);t.mkdir(parents=True)
    anchor=pd.Timestamp('2026-01-01T00:00:00Z');sources=['yang_lei','real_ais_denmark_oct2025','synthetic_ais_denmark_oct2025'];rows=[];vessels=[];meta=[];encounters=[];X=np.zeros((6,10,4),dtype=np.float32);anchors=np.empty((3,2,2),dtype=np.float64)
    for i,src in enumerate(sources):
        eid=f'e{i}';meta.append({'encounter_id':eid,'data_source':src,'anchor_timestamp':anchor,'difficulty':None if i==0 else 'easy','scenario':'other'});encounters.append({'encounter_id':eid,'encounter_index':i,'high_risk_label':i%2})
        for j,slot in enumerate(('A','B')):
            lat=55.0+j*.001;vid=f'{eid}-{slot}';vessels.append({'encounter_id':eid,'encounter_index':i,'vessel':slot,'vessel_id':vid,'X_row':2*i+j,'data_source':src})
            anchors[i,j]=common_en(lat,10.,55.,10.)
            X[2*i+j,:,2:]=velocity_en(np.full(10,5.),np.zeros(10))
            for minute in range(-9,16):
                timestamp=anchor+pd.Timedelta(minutes=minute);original=pd.NaT if i==0 else timestamp-pd.Timedelta(seconds=20)+(pd.Timedelta(days=1) if i==2 and j==1 else pd.Timedelta(0));simulated=pd.NaT if i==0 else timestamp-pd.Timedelta(seconds=20)
                rows.append({'encounter_id':eid,'vessel':slot,'vessel_id':vid,'timestamp_utc':timestamp,'anchor_timestamp':anchor,'relative_minute':minute,'is_history':minute<=0,'is_future':minute>0,'SOG':5.,'COG':0.,'LAT':lat,'LON':10.,'data_source':src,'split':'test','original_source_timestamp_utc':original,'simulated_source_timestamp_utc':simulated,'source_track_id':None if i==0 else f'track-{vid}'})
    np.save(t/'X_unscaled.npy',X);np.save(t/'anchor_positions_EN_nm.npy',anchors);np.save(t/'labels.npy',np.array([0,1,0],dtype=np.int8));np.save(t/'target_EN_nm.npy',np.zeros((3,2,15,2),dtype=np.float32))
    pd.DataFrame(meta).to_parquet(d/'encounter_metadata.parquet');pd.DataFrame(rows).to_parquet(d/'test_1320.parquet');pd.DataFrame(encounters).to_csv(t/'encounter_tensor_index.csv',index=False);pd.DataFrame(vessels).to_csv(t/'vessel_tensor_index.csv',index=False)
    class Loader:
        def __init__(self,_):self.root=root;self.config={'splits':{'test':{'encounters':3,'vessels':6,'records':150,'data':'test_1320.parquet'}}}
    monkeypatch.setattr(b,'DatasetLoader',Loader)
    from test_s4_t15_authorization import fixture as auth_fixture
    from src.evaluation import t15_authorization as auth
    from src.evaluation.t15_full_authorization import validate_full_scope
    args,_,_,_=auth_fixture(tmp_path,monkeypatch);(root/'DATASET_LOCK_MANIFEST.json').write_text('synthetic-lock');args['dataset_root']=root
    full_record={'full_approval':'C1-C5','full_scope':'AUDITED_FULL_TECHNICAL_RERUN','parent_r2_run':'s4_t15_r2_20261125T152141Z_2cd800cd','audit_inventory_sha256':'a'*64}
    full_protocol={'revision_classification':'TECHNICAL_ACCESS_AUDIT_CORRECTION','audit_inventory_sha256':'a'*64}
    full_evidence={k:True for k in ('synthetic_end_to_end','synthetic_negative_audit_tests','audit_completeness_verifier','materialization_semantics','q1_no_test_deserialization','full_regression')}
    validate_full_scope(full_record,full_protocol,full_evidence,'a'*64)
    audit=Audit(tmp_path/'events.jsonl','run','auth','protocol')
    with supported_path_guard(root) as counts:
        with pytest.raises(AuditError):np.load(t/'X_unscaled.npy')
    assert counts['denied']==1
    guard=supported_path_guard(root);counts=guard.__enter__();request.addfinalizer(lambda:guard.__exit__(None,None,None))
    def authorized_loader(ctx):
        assert (tmp_path/'pre_access.json').exists() and (tmp_path/'pre_access.json.sha256').exists()
        audit.emit('authorization','authorization','AUTHORIZATION_VERIFIED','synthetic-gate')
        return b._read_inputs(ctx,audit,3,6)
    loaded,_,_=auth.run_gated(report_path=tmp_path/'pre_access.json',loader=authorized_loader,**args)
    assert np.array_equal(loaded.split.X,X) and np.array_equal(loaded.split.anchors,anchors) and loaded.split.labels is None and loaded.split.common is None
    assert not any(e['phase']=='evaluation' for e in events(audit.path))
    with pytest.raises(AuditError):b.read_evaluation(loaded)
    from src.evaluation import t15_full_benchmark as bench
    from src.models.m5a import ResidualGRU
    from src.models.scalers import TrainOnlyScaler
    import torch
    class SyntheticModel:
        def __init__(self,artifact,device):
            self.device=torch.device('cpu');self.model=ResidualGRU().eval()
            with torch.no_grad():
                for p in self.model.parameters():p.zero_()
            self.x_scaler=TrainOnlyScaler('input');self.residual_scaler=TrainOnlyScaler('residual')
            self.x_scaler.mean=np.zeros(4);self.x_scaler.scale=np.ones(4);self.residual_scaler.mean=np.zeros(2);self.residual_scaler.scale=np.ones(2)
    monkeypatch.setattr(bench,'M5aInference',SyntheticModel)
    out=tmp_path/'outputs';out.mkdir();result=bench.evaluate_loaded(loaded,out,tmp_path,synthetic_expected_sources={s:1 for s in sources},synthetic_skip_timing=True)
    assert counts['denied']==0
    assert result['forecast_shape']==[3,2,15,2] and loaded.split.labels.tolist()==[0,1,0] and loaded.split.common.shape==(3,2,15,2)
    assert json.loads((out/'final_full_run_access_audit.json').read_text())['status']=='PASS'
    assert {'labels','target','label_index','evaluation_metadata','future'} <= {e['category'] for e in events(audit.path) if e['event_type']=='SEMANTIC_VALUE_ACCESS_OBSERVED'}
    import hashlib
    checks={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    assert {'cv_predictions.npz','m5a_predictions.npz','risk_scores.parquet','benchmark_acceptance.json'}<=checks.keys()
    assert all(hashlib.sha256((out/name).read_bytes()).hexdigest()==sha for name,sha in checks.items())
