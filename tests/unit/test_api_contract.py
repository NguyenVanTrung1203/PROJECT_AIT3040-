"""Schema and illustrative semantic tests; no runtime API is implemented."""
import copy
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
import pytest
import yaml
from openapi_spec_validator import validate as validate_openapi

ROOT=Path(__file__).resolve().parents[2]
CONTRACTS=ROOT/'contracts'
SCHEMAS=['common','track_snapshot','encounter','risk_request','risk_response','alert','model_status','forecast','error']
BASE='https://schemas.ait3040.invalid/contracts/'


@pytest.fixture(scope='module')
def validators():
    documents={}
    for name in SCHEMAS:
        raw=json.loads((CONTRACTS/f'{name}.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(raw)
        raw['$id']=BASE+name+'.schema.json'
        documents[name]=raw
    registry=Registry()
    for name,doc in documents.items():registry=registry.with_resource(BASE+name+'.schema.json',Resource.from_contents(doc))
    return {name:Draft202012Validator(doc,registry=registry,format_checker=FormatChecker()) for name,doc in documents.items()}


def time(i=0):
    return (datetime(2026,1,1,12,tzinfo=timezone.utc)+timedelta(minutes=i)).isoformat().replace('+00:00','Z')


def track(vessel='physical_mmsi:123456789',mmsi='123456789'):
    points=[{'nominal_timestamp':time(i),'source_timestamp':time(i),'original_source_timestamp':time(i),'latitude':57.0,'longitude':11.0,'sog_kn':10.0,'cog_deg':90.0,'source_age_seconds':0} for i in range(-9,1)]
    return {'schema_version':'1.0.0','vessel_id':vessel,'mmsi':mmsi,'source_type':'REAL_AIS','is_simulated':False,'anchor_timestamp':time(),'current_state':copy.deepcopy(points[-1]),'history':points,'data_status':'VALID'}


def origin():
    return {'origin_latitude':57.0,'origin_longitude':11.0,'origin_timestamp':time(-9),'origin_vessel_id':'physical_mmsi:123456789','coordinate_method':'LOCAL_DEGREES_COS_LAT0','coordinate_unit':'nautical_mile','coordinate_dtype':'float64','geographic_mapping_status':'VERIFIED_REAL'}


def encounter():
    from scripts.verify_feature_contract import proposed_pair_id
    a=track();b=track('physical_mmsi:987654321','987654321')
    return {'schema_version':'1.0.0','encounter_id':'session1:e1','pair_id':proposed_pair_id(a['vessel_id'],b['vessel_id']),'replay_session_id':'session1','anchor_timestamp':time(),'vessel_a':a,'vessel_b':b,'current_distance_nm':1.0,'coordinate_origin':origin(),'encounter_status':'READY'}


def forecast():
    points=[[[0.0,0.0] for _ in range(15)] for _ in range(2)]
    return {'schema_version':'1.0.0','forecast_timestamps':[time(i) for i in range(1,16)],'forecast_displacement_en_nm':points,'forecast_common_en_nm':copy.deepcopy(points),'forecast_lat_lon':None,'geographic_availability':'UNAVAILABLE','coordinate_origin':origin(),'anchor_positions_en_nm':[[0.,0.],[1.,0.]]}


def model_status():
    return {'schema_version':'1.0.0','requested_model':'M5A','active_model':'M5A','model_version':'v1','artifact_version':'a1','inference_status':'SUCCESS','data_status':'VALID','fallback_used':False,'fallback_reason':None,'calibration_status':'NOT_CALIBRATED'}


def response():
    e=encounter()
    return {'schema_version':'1.0.0','request_id':'r1','encounter_id':e['encounter_id'],'pair_id':e['pair_id'],'replay_session_id':'session1','vessel_ids':[e['vessel_a']['vessel_id'],e['vessel_b']['vessel_id']],'vessel_roles':['A','B'],'anchor_timestamp':time(),'evaluated_at':None,'current_dcpa_nm':0.8,'current_tcpa_minutes':-2.0,'current_tcpa_clipped_minutes':0.0,'current_cpa_status':'AVAILABLE','predicted_min_distance_nm':0.5,'predicted_closest_time_minutes':2,'predicted_closest_timestamp':time(2),'predicted_cpa_status':'AVAILABLE','predicted_cpa_score':0.5,'current_cpa_score':0.4,'rule_score':0.5,'risk_score':0.488,'threshold':None,'threshold_version':None,'calibration_status':'NOT_CALIBRATED','threshold_model':None,'alert_triggered':None,'decision_status':'NOT_CALIBRATED','decision_reason':'not calibrated','forecast':forecast(),'forecast_status':'AVAILABLE','projection_status':'APPLIED','model_status':model_status()}


def alert():
    e=encounter()
    return {'schema_version':'1.0.0','alert_id':'alert-1','replay_session_id':'session1','pair_id':e['pair_id'],'opened_encounter_id':'session1:e1','latest_encounter_id':'session1:e1','vessel_ids':[e['vessel_a']['vessel_id'],e['vessel_b']['vessel_id']],'opened_at':time(),'updated_at':time(),'closed_at':None,'latest_evaluation_timestamp':time(),'risk_score':0.5,'threshold':0.4,'predicted_min_distance_nm':0.5,'predicted_closest_time_minutes':2,'current_dcpa_nm':0.8,'current_tcpa_minutes':-2.,'active_model':'M5A','alert_status':'ACTIVE','status_reason':'threshold exceeded','values_as_of':time(),'values_are_last_valid':False}


def semantic_encounter(e, replay=True):
    from scripts.verify_feature_contract import proposed_pair_id
    a,b=e['vessel_a'],e['vessel_b']
    if a['vessel_id']==b['vessel_id'] or a['anchor_timestamp']!=e['anchor_timestamp'] or b['anchor_timestamp']!=e['anchor_timestamp']: return False
    if replay and (a['vessel_id']>=b['vessel_id'] or e['pair_id']!=proposed_pair_id(a['vessel_id'],b['vessel_id'])):return False
    if e['encounter_status']=='READY':
        for t in (a,b):
            if t['current_state']!=t['history'][-1] or [p['nominal_timestamp'] for p in t['history']] != [time(i) for i in range(-9,1)]:return False
            for p in t['history']:
                if p['source_timestamp'] is not None:
                    nominal=datetime.fromisoformat(p['nominal_timestamp'].replace('Z','+00:00')); source=datetime.fromisoformat(p['source_timestamp'].replace('Z','+00:00'))
                    if not 0<=(nominal-source).total_seconds()<=60:return False
        o=e['coordinate_origin']; first=a['history'][0]
        if (o['origin_vessel_id'],o['origin_timestamp'],o['origin_latitude'],o['origin_longitude']) != (a['vessel_id'],first['nominal_timestamp'],first['latitude'],first['longitude']):return False
    return True


def semantic_response(r):
    try: json.dumps(r,allow_nan=False)
    except (ValueError,TypeError):return False
    components=[r[k] for k in ('predicted_cpa_score','current_cpa_score','rule_score')]
    if any(v is None for v in components):
        if r['risk_score'] is not None:return False
    elif r['risk_score'] is None or not math.isclose(r['risk_score'],sum(a*b for a,b in zip(components,[.68,.12,.20])),abs_tol=1e-9):return False
    if r['calibration_status']=='NOT_CALIBRATED':return r['threshold'] is None and r['alert_triggered'] is None
    if r['decision_status']=='DECIDED':
        return r['threshold_model']==r['model_status']['active_model'] and r['alert_triggered']==(r['risk_score']>=r['threshold'])
    return r['alert_triggered'] is None


def test_meta_schemas_and_refs(validators):
    for validator in validators.values():
        def walk(node):
            if isinstance(node,dict):
                if '$ref' in node: validator._resolver.lookup(node['$ref'])
                for item in node.values():walk(item)
            elif isinstance(node,list):
                for item in node:walk(item)
        walk(validator.schema)


def test_track_valid_and_partial(validators):
    v=validators['track_snapshot'];t=track();v.validate(t)
    stale=track();stale['history'][-1]['source_age_seconds']=61;stale['data_status']='STALE';v.validate(stale)
    stale['data_status']='VALID';assert not v.is_valid(stale)
    sim=track();sim.update(source_type='YANG_LEI',is_simulated=True,mmsi=None,vessel_id='simulated:123')
    for point in sim['history']:point.update(source_timestamp=None,original_source_timestamp=None,source_age_seconds=None)
    sim['current_state']=copy.deepcopy(sim['history'][-1]);v.validate(sim)
    t.update(data_status='INSUFFICIENT_DATA',history=[],current_state=None);v.validate(t)
    t.update(source_type='YANG_LEI',is_simulated=True,mmsi=None,vessel_id='simulated:123');v.validate(t)
    t.update(data_status='VALID');assert not v.is_valid(t)


@pytest.mark.parametrize('field,value',[('latitude',91),('longitude',-181),('sog_kn',-1),('sog_kn',51),('cog_deg',360),('cog_deg',-1)])
def test_track_invalid_ranges(validators,field,value):
    t=track();t['history'][0][field]=value;assert not validators['track_snapshot'].is_valid(t)


def test_track_utc_and_mmsi(validators):
    t=track();t['anchor_timestamp']='2026-01-01T12:00:00+07:00';assert not validators['track_snapshot'].is_valid(t)
    t=track();t['mmsi']='123';assert not validators['track_snapshot'].is_valid(t)
    t=track();t['anchor_timestamp']='2026-01-01T12:00:00+00:00';validators['track_snapshot'].validate(t)


def test_encounter_structure_and_semantics(validators):
    e=encounter();validators['encounter'].validate(e);assert semantic_encounter(e)
    x=copy.deepcopy(e);x['vessel_b']=copy.deepcopy(x['vessel_a']);assert not semantic_encounter(x)
    x=copy.deepcopy(e);x['vessel_b']['anchor_timestamp']=time(1);assert not semantic_encounter(x)
    x=copy.deepcopy(e);x['vessel_a']['history'][0]['source_timestamp']=time(-8);assert not semantic_encounter(x)
    x=copy.deepcopy(e);x['current_distance_nm']='one';assert not validators['encounter'].is_valid(x)


def test_request_rejects_leakage_and_override(validators):
    r={'schema_version':'1.0.0','request_id':'r1','encounter':encounter(),'replay_session_id':'session1','requested_model':'M5A'}
    v=validators['risk_request'];v.validate(r)
    for field in ('label','future_trajectory','threshold','weights'):
        x=copy.deepcopy(r);x[field]=0;assert not v.is_valid(x)
    x=copy.deepcopy(r);x['encounter']['vessel_a']['history'][0]['rule_violation_true']=1;assert not v.is_valid(x)


def test_response_uncalibrated_negative_tcpa_and_undefined(validators):
    r=response();validators['risk_response'].validate(r);assert semantic_response(r)
    assert r['current_tcpa_minutes']<0 and r['forecast'] is not None and r['alert_triggered'] is None
    r.update(current_tcpa_minutes=None,current_tcpa_clipped_minutes=None,current_cpa_status='UNDEFINED_LOW_RELATIVE_VELOCITY')
    validators['risk_response'].validate(r);assert semantic_response(r)
    r['current_cpa_score']=None;assert not validators['risk_response'].is_valid(r)


def test_near_zero_cpa_calibration_and_invalid_input(validators):
    r=response();v=validators['risk_response']
    r.update(current_tcpa_minutes=None,current_tcpa_clipped_minutes=None,current_cpa_status='UNDEFINED_LOW_RELATIVE_VELOCITY')
    v.validate(r);assert semantic_response(r) and r['alert_triggered'] is None
    assert r['model_status']['fallback_used'] is False
    r.update(calibration_status='CALIBRATED',threshold=.45,threshold_version='new-calibration',threshold_model='M5A',decision_status='DECIDED',alert_triggered=True)
    r['model_status']['calibration_status']='CALIBRATED'
    v.validate(r);assert semantic_response(r)
    r['model_status']['data_status']='INVALID_DATA';assert not v.is_valid(r)
    r=response();r.update(current_cpa_status='UNAVAILABLE',current_dcpa_nm=None,current_tcpa_minutes=None,current_tcpa_clipped_minutes=None,current_cpa_score=None,risk_score=None,alert_triggered=None,decision_status='INSUFFICIENT_DATA')
    r['model_status'].update(data_status='INSUFFICIENT_DATA',inference_status='NOT_RUN',active_model=None)
    v.validate(r);assert semantic_response(r)
    r['risk_score']=0.0;assert not v.is_valid(r)


def test_response_decision_and_model_specific_threshold(validators):
    r=response();r.update(calibration_status='CALIBRATED',threshold=.45,threshold_version='v1',threshold_model='M5A',decision_status='DECIDED',alert_triggered=True)
    r['model_status']['calibration_status']='CALIBRATED';validators['risk_response'].validate(r);assert semantic_response(r)
    r['threshold_model']='CV';assert not semantic_response(r)
    r['threshold_model']='M5A';r['alert_triggered']=False;assert not semantic_response(r)
    r['alert_triggered']=True;r['risk_score']=float('nan');assert not semantic_response(r)


def test_forecast_shapes_and_geographic_availability(validators):
    f=forecast();validators['forecast'].validate(f)
    f['forecast_common_en_nm'][0].pop();assert not validators['forecast'].is_valid(f)
    f=forecast();f['geographic_availability']='AVAILABLE';assert not validators['forecast'].is_valid(f)


def test_status_m5a_direct_cv_fallback_invalid(validators):
    v=validators['model_status'];s=model_status();v.validate(s)
    s.update(requested_model='CV',active_model='CV');v.validate(s)
    s.update(requested_model='M5A',fallback_used=True,fallback_reason='load failure');v.validate(s)
    s['data_status']='INVALID_DATA';assert not v.is_valid(s)
    s=model_status();s.update(active_model=None,inference_status='NOT_RUN',data_status='INSUFFICIENT_DATA');v.validate(s)


def test_global_model_status_without_artifact(validators):
    raw=validators['model_status'].schema
    global_schema=copy.deepcopy(raw);global_schema['$ref']='#/$defs/global_status'
    for key in ('type','properties','required','additionalProperties','allOf'):global_schema.pop(key,None)
    validator=Draft202012Validator(global_schema,registry=validators['model_status']._registry,format_checker=FormatChecker())
    status={'schema_version':'1.0.0','m5a_artifact_available':False,'m5a_ready':False,'m5a_version':None,'cv_available':True,'cv_version':None,'m5a_calibration_status':'NOT_CALIBRATED','cv_calibration_status':'NOT_CALIBRATED','m5a_threshold':None,'cv_threshold':None,'status_reason':'M5a not trained'}
    validator.validate(status)
    status['m5a_ready']=True;assert not validator.is_valid(status)
    status['m5a_ready']=False;status['m5a_threshold']=0.42;assert not validator.is_valid(status)


def test_alert_states_and_timestamps(validators):
    a=alert();v=validators['alert'];v.validate(a)
    a.update(alert_status='DATA_UNAVAILABLE',status_reason='missing data',values_are_last_valid=True);v.validate(a)
    a.update(alert_status='RESOLVED',closed_at=time(1));v.validate(a)
    a['closed_at']=None;assert not v.is_valid(a)


def test_openapi_document_and_local_references():
    file=CONTRACTS/'api_contract.yaml';api=yaml.safe_load(file.read_text(encoding='utf-8'))
    validate_openapi(api,base_uri=file.as_uri())
    expected={'/api/v1/model/status':'get','/api/v1/risk/evaluate':'post','/api/v1/risk/encounters':'get','/api/v1/risk/encounters/{id}':'get','/api/v1/alerts':'get','/api/v1/alerts/{id}':'get'}
    assert api['openapi'].startswith('3.1.') and set(api['paths'])==set(expected)
    for path,method in expected.items():
        operation=api['paths'][path][method];assert {'200','400','422','500','503'} <= set(operation['responses'])
        if '{id}' in path:assert any(p['name']=='id' and p['in']=='path' and p['required'] for p in operation['parameters']) and '404' in operation['responses']
    assert '409' in api['paths']['/api/v1/risk/evaluate']['post']['responses']
    assert {'replay_session_id','pair_id','limit','offset'} <= {p['name'] for p in api['paths']['/api/v1/risk/encounters']['get']['parameters']}
