"""Kiểm thử fixture tĩnh; không chạy backend hoặc mô hình."""
from datetime import datetime,timedelta
import hashlib
import json
import math
import unicodedata
from pathlib import Path

from jsonschema import Draft202012Validator,FormatChecker
from referencing import Registry,Resource
from openapi_spec_validator import validate as validate_openapi
import pytest
import yaml

ROOT=Path(__file__).resolve().parents[2]
MOCK=ROOT/'contracts/mock'
MANIFEST=json.loads((MOCK/'manifest.json').read_text(encoding='utf-8'))
ITEMS=MANIFEST['fixtures']
BASE='https://schemas.ait3040.invalid/contracts/'
TOL=1e-9


def strict_load(path):
    def bad(value):raise ValueError('Non-standard JSON constant: '+value)
    return json.loads(path.read_text(encoding='utf-8'),parse_constant=bad)


def time(s):return datetime.fromisoformat(s.replace('Z','+00:00'))


@pytest.fixture(scope='module')
def validators():
    names=('common','track_snapshot','encounter','risk_request','risk_response','alert','model_status','forecast','error','replay','encounter_v1','risk_request_v1','risk_response_v1','alert_v1')
    docs={};reg=Registry()
    for name in names:
        raw=strict_load(ROOT/'contracts'/f'{name}.schema.json');Draft202012Validator.check_schema(raw);raw['$id']=BASE+name+'.schema.json';docs[name]=raw
    for name,doc in docs.items():reg=reg.with_resource(BASE+name+'.schema.json',Resource.from_contents(doc))
    result={name:Draft202012Validator(doc,registry=reg,format_checker=FormatChecker()) for name,doc in docs.items()}
    result['model_status#/$defs/global_status']=Draft202012Validator({'$ref':BASE+'model_status.schema.json#/$defs/global_status'},registry=reg,format_checker=FormatChecker())
    return result


def pair_id(a,b):
    ids=[unicodedata.normalize('NFC', value) for value in (a,b)]
    return 'pair:v1:'+hashlib.sha256(json.dumps(sorted(ids,key=lambda value:value.encode('utf-8')),ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()


def check_track(t):
    h=t['history'];state=t['data_status']
    if h and t['current_state']!=h[-1]:return False
    if state=='VALID':
        if len(h)!=10 or [time(x['nominal_timestamp']) for x in h]!=[time(t['anchor_timestamp'])+timedelta(minutes=k) for k in range(-9,1)]:return False
        if t['source_type'] in ('REAL_AIS','SYNTHETIC_AIS'):
            for x in h:
                if x['source_timestamp'] is None:return False
                age=(time(x['nominal_timestamp'])-time(x['source_timestamp'])).total_seconds()
                if not 0<=age<=60 or not math.isclose(age,x['source_age_seconds'],abs_tol=TOL):return False
    if state=='STALE':
        if not any(x['source_age_seconds'] is not None and x['source_age_seconds']>60 for x in h):return False
    return True


def check_encounter(e):
    a,b=e['vessel_a'],e['vessel_b'];o=e['coordinate_origin']
    if not check_track(a) or not check_track(b):return False
    if a['vessel_id']==b['vessel_id'] or a['vessel_id'].encode('utf-8')>=b['vessel_id'].encode('utf-8'):return False
    if e['pair_id']!=pair_id(a['vessel_id'],b['vessel_id']) or e['encounter_id']==e['pair_id']:return False
    if a['anchor_timestamp']!=e['anchor_timestamp'] or b['anchor_timestamp']!=e['anchor_timestamp']:return False
    if e['encounter_status']=='READY':
        if a['data_status']!='VALID' or b['data_status']!='VALID' or o is None:return False
        h=a['history'][0]
        if (o['origin_vessel_id'],o['origin_timestamp'],o['origin_latitude'],o['origin_longitude'])!=(a['vessel_id'],h['nominal_timestamp'],h['latitude'],h['longitude']):return False
        ca,cb=a['current_state'],b['current_state'];dx=(cb['longitude']-ca['longitude'])*60*math.cos(math.radians(o['origin_latitude']));dy=(cb['latitude']-ca['latitude'])*60
        if not math.isclose(math.hypot(dx,dy),e['current_distance_nm'],abs_tol=TOL):return False
    if e['encounter_status']=='INSUFFICIENT_DATA' and all(t['data_status']=='VALID' for t in (a,b)):return False
    return True


def angle(a,b):return (a-b+180)%360-180


def rule_score(enc):
    tracks=[enc['vessel_a'],enc['vessel_b']];o=enc['coordinate_origin'];lat0,lon0=o['origin_latitude'],o['origin_longitude'];p=[];v=[]
    for track in tracks:
        first=track['history'][:3]
        p.append([sum((x['longitude']-lon0)*60*math.cos(math.radians(lat0)) for x in first)/3,sum((x['latitude']-lat0)*60 for x in first)/3])
        v.append([sum(x['sog_kn']*math.sin(math.radians(x['cog_deg'])) for x in first)/3,sum(x['sog_kn']*math.cos(math.radians(x['cog_deg'])) for x in first)/3])
    cog=[math.degrees(math.atan2(x[0],x[1]))%360 for x in v];speed=[math.hypot(*x) for x in v];bearing=math.degrees(math.atan2(p[1][0]-p[0][0],p[1][1]-p[0][1]))%360;ba=(bearing-cog[0])%360;bb=(bearing+180-cog[1])%360;delta=abs(angle(cog[0],cog[1]));role=None
    if abs(delta-180)<=25 and abs(angle(ba,0))<=20 and abs(angle(bb,0))<=20:role='both'
    elif delta<=30 and 112.5<ba<247.5 and speed[1]>speed[0]:role='B'
    elif delta<=30 and 112.5<bb<247.5 and speed[0]>speed[1]:role='A'
    elif 30<=delta<=150 and 15<=ba<=165:role='A'
    elif 30<=delta<=150 and 195<=ba<=345:role='B'
    values=[]
    for track in tracks:
        first,last=track['history'][0],track['history'][-1];dc=angle(last['cog_deg'],first['cog_deg']);ds=last['sog_kn']-first['sog_kn'];values.append(float(not(dc>=10 or (dc>=5 and ds<=-.6)) or dc<=-4))
    return .5 if role is None else ((values[0]+values[1])/2 if role=='both' else values[0 if role=='A' else 1])


def component(d,t,scale):return 1/(1+math.exp(max(-100,min(100,(d-.65)/scale))))*(1-.25*min(t,15)/15)


def check_response(r):
    try:json.dumps(r,allow_nan=False)
    except ValueError:return False
    status=r['model_status'];fc=r['forecast'];components=[r[k] for k in ('predicted_cpa_score','current_cpa_score','rule_score')]
    if status['data_status']!='VALID' and (r['risk_score'] is not None or r['alert_triggered'] is not None or status['fallback_used']):return False
    if status['fallback_used'] and not(status['data_status']=='VALID' and status['requested_model']=='M5A' and status['active_model']=='CV' and status['fallback_reason']):return False
    if any(x is None for x in components):
        if r['risk_score'] is not None:return False
    elif r['risk_score'] is None or not math.isclose(r['risk_score'],.68*components[0]+.12*components[1]+.2*components[2],abs_tol=TOL):return False
    if r['calibration_status']=='NOT_CALIBRATED' and (r['threshold'] is not None or r['alert_triggered'] is not None):return False
    if r['decision_status']=='DECIDED':
        if r['threshold_model']!=status['active_model'] or r['alert_triggered']!=(r['risk_score']>=r['threshold']):return False
    elif r['alert_triggered'] is not None:return False
    if fc is None:return r['risk_score'] is None
    name={'mock-encounter-01':'encounter_valid','mock-encounter-near':'encounter_near_zero','mock-encounter-far':'encounter_far'}.get(r['encounter_id'])
    if name is None:return False
    e=strict_load(MOCK/'encounters'/f'{name}.json')
    if not check_encounter(e) or (r['pair_id'],r['replay_session_id'],r['anchor_timestamp'])!=(e['pair_id'],e['replay_session_id'],e['anchor_timestamp']):return False
    if r['vessel_ids']!=[e['vessel_a']['vessel_id'],e['vessel_b']['vessel_id']]:return False
    if [time(x) for x in fc['forecast_timestamps']]!=[time(r['anchor_timestamp'])+timedelta(minutes=k) for k in range(1,16)]:return False
    origin=fc['coordinate_origin'];lat0,lon0=origin['origin_latitude'],origin['origin_longitude'];factor=60*math.cos(math.radians(lat0))
    if origin!=e['coordinate_origin']:return False
    for i,track in enumerate((e['vessel_a'],e['vessel_b'])):
        state=track['current_state'];anchor=[(state['longitude']-lon0)*factor,(state['latitude']-lat0)*60]
        if any(not math.isclose(anchor[j],fc['anchor_positions_en_nm'][i][j],abs_tol=TOL) for j in range(2)):return False
        for k in range(15):
            xy=fc['forecast_common_en_nm'][i][k];dp=fc['forecast_displacement_en_nm'][i][k]
            if any(not math.isclose(xy[j],dp[j]+anchor[j],abs_tol=TOL) for j in range(2)):return False
            if fc['forecast_lat_lon'] is not None:
                lat,lon=fc['forecast_lat_lon'][i][k]
                if not(math.isclose((lon-lon0)*factor,xy[0],abs_tol=TOL) and math.isclose((lat-lat0)*60,xy[1],abs_tol=TOL)):return False
    distances=[math.dist(fc['forecast_common_en_nm'][0][k],fc['forecast_common_en_nm'][1][k]) for k in range(15)];index=min(range(15),key=distances.__getitem__)
    if not math.isclose(distances[index],r['predicted_min_distance_nm'],abs_tol=TOL) or index+1!=r['predicted_closest_time_minutes'] or time(r['predicted_closest_timestamp'])!=time(r['anchor_timestamp'])+timedelta(minutes=index+1):return False
    if not math.isclose(component(distances[index],index+1,.14),r['predicted_cpa_score'],abs_tol=TOL):return False
    a,b=e['vessel_a']['current_state'],e['vessel_b']['current_state'];p=fc['anchor_positions_en_nm'];rel=[p[1][j]-p[0][j] for j in range(2)];va=[a['sog_kn']*math.sin(math.radians(a['cog_deg'])),a['sog_kn']*math.cos(math.radians(a['cog_deg']))];vb=[b['sog_kn']*math.sin(math.radians(b['cog_deg'])),b['sog_kn']*math.cos(math.radians(b['cog_deg']))];dv=[vb[j]-va[j] for j in range(2)];den=sum(x*x for x in dv)
    raw=-60*sum(rel[j]*dv[j] for j in range(2))/den if den>1e-9 else 0;clip=max(0,min(15,raw));d=math.hypot(*(rel[j]+dv[j]*clip/60 for j in range(2)))
    if den<=1e-9:
        if r['current_cpa_status']!='UNDEFINED_LOW_RELATIVE_VELOCITY' or r['current_tcpa_minutes'] is not None or r['current_tcpa_clipped_minutes'] is not None:return False
    elif r['current_cpa_status']!='AVAILABLE' or not(math.isclose(raw,r['current_tcpa_minutes'],abs_tol=TOL) and math.isclose(clip,r['current_tcpa_clipped_minutes'],abs_tol=TOL)):return False
    return math.isclose(d,r['current_dcpa_nm'],abs_tol=TOL) and math.isclose(component(d,clip,.16),r['current_cpa_score'],abs_tol=TOL) and math.isclose(rule_score(e),r['rule_score'],abs_tol=TOL)


def semantic(data,schema):
    if schema=='track_snapshot':return check_track(data)
    if schema=='encounter':return check_encounter(data)
    if schema=='risk_request':return check_encounter(data['encounter']) and data['replay_session_id']==data['encounter']['replay_session_id']
    if schema=='risk_response':return check_response(data)
    return True


def status_matches(data,schema,expected):
    if schema=='track_snapshot':return data['data_status']==expected
    if schema=='encounter':return data['encounter_status']==expected
    if schema=='risk_request':return data['encounter']['encounter_status']==('READY' if expected=='VALID' else expected)
    if schema=='risk_response':return (data['model_status']['data_status']=='VALID' if expected=='VALID' else data['decision_status']==expected)
    if schema=='alert':return data['alert_status']==expected
    if schema=='model_status':return data['calibration_status']=='NOT_CALIBRATED' if expected=='NOT_CALIBRATED' else data['inference_status']==expected
    if schema=='model_status#/$defs/global_status':return expected=='NOT_READY' and not data['m5a_ready']
    return False


@pytest.mark.parametrize('item',ITEMS,ids=[x['fixture_id'] for x in ITEMS])
def test_manifest_fixture_validation(item,validators):
    path=(MOCK/item['relative_path']).resolve();assert path.is_relative_to(MOCK.resolve()) and item['mock_data_marker'] is True
    layer=item['expected_validation_layer']
    if layer=='JSON_PARSE_ERROR':
        with pytest.raises((json.JSONDecodeError,ValueError)):strict_load(path)
        return
    data=strict_load(path);v=validators[item['target_schema']];errors=list(v.iter_errors(data))
    if layer=='SCHEMA_VALIDATION_ERROR':assert errors;return
    assert not errors, [e.message for e in errors]
    ok=semantic(data,item['target_schema'])
    if layer=='SEMANTIC_VALIDATION_ERROR':assert not ok
    else:assert item['expected_validity'] and ok and status_matches(data,item['target_schema'],item['expected_status'])


def test_openapi_and_all_references(validators):
    file=ROOT/'contracts/api_contract.yaml';api=yaml.safe_load(file.read_text(encoding='utf-8'));validate_openapi(api,base_uri=file.as_uri())
    assert {'/api/v1/model/status','/api/v1/risk/evaluate','/api/v1/risk/encounters','/api/v1/risk/encounters/{id}','/api/v1/alerts','/api/v1/alerts/{id}'} <= set(api['paths'])


def test_alert_lifecycle_duplicate_and_session_isolation():
    def read(n):return strict_load(MOCK/'alerts'/f'{n}.json')
    a,lost,closed,repeat,reset=[read(n) for n in ('alert_active','alert_data_unavailable','alert_resolved','alert_repeated_evaluation','alert_after_replay_reset')]
    assert a==repeat and a['alert_status']=='ACTIVE' and lost['alert_status']=='DATA_UNAVAILABLE' and closed['alert_status']=='RESOLVED'
    assert a['alert_id']==lost['alert_id']==closed['alert_id'] and a['pair_id']==lost['pair_id']==closed['pair_id']
    assert a['replay_session_id']==lost['replay_session_id']==closed['replay_session_id']!=reset['replay_session_id'] and reset['alert_id']!=a['alert_id'] and reset['pair_id']==a['pair_id']
    assert lost['values_are_last_valid'] and lost['values_as_of']==a['values_as_of'] and lost['closed_at'] is None
    under=strict_load(MOCK/'responses/risk_response_no_alert.json');assert under['alert_triggered'] is False and closed['risk_score']==under['risk_score'] and closed['threshold']==under['threshold'] and closed['latest_encounter_id']==under['encounter_id']
    assert time(a['opened_at'])<=time(lost['updated_at'])<=time(closed['closed_at'])


def test_replay_encounter_requires_online_canonical_order():
    e = strict_load(MOCK/'encounters/encounter_valid.json')
    e['vessel_a'], e['vessel_b'] = e['vessel_b'], e['vessel_a']
    a, b = e['vessel_a'], e['vessel_b']
    first = a['history'][0]
    e['coordinate_origin'].update(origin_vessel_id=a['vessel_id'], origin_timestamp=first['nominal_timestamp'],
                                   origin_latitude=first['latitude'], origin_longitude=first['longitude'])
    ca, cb = a['current_state'], b['current_state']
    dx = (cb['longitude']-ca['longitude'])*60*math.cos(math.radians(first['latitude']))
    dy = (cb['latitude']-ca['latitude'])*60
    e['current_distance_nm'] = math.hypot(dx, dy)
    assert a['vessel_id'] > b['vessel_id']
    assert not check_encounter(e)


def test_scenario_coverage_and_unique_paths():
    assert len({x['fixture_id'] for x in ITEMS})==len(ITEMS)==len({x['relative_path'] for x in ITEMS})
    assert {x['expected_validation_layer'] for x in ITEMS}=={'VALID','JSON_PARSE_ERROR','SCHEMA_VALIDATION_ERROR','SEMANTIC_VALIDATION_ERROR'}
    assert {x['target_schema'] for x in ITEMS if x['expected_validity']} >= {'track_snapshot','encounter','risk_request','risk_response','alert','model_status','model_status#/$defs/global_status'}
