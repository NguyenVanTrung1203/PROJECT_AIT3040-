"""V1 production/legacy schema and reference examples; no Replay runtime."""
import copy
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource
import pytest
import yaml

from scripts.contract_identity_reference import encounter_id

ROOT = Path(__file__).resolve().parents[2]
C = ROOT/'contracts'
BASE = 'https://schemas.ait3040.invalid/contracts/'
SESSION = '123e4567-e89b-12d3-a456-426614174000'
SNAPSHOT = '123e4567-e89b-12d3-a456-426614174002'


@pytest.fixture(scope='module')
def validators():
    docs = {}
    reg = Registry()
    for name in ('common', 'track_snapshot', 'encounter', 'replay', 'encounter_v1', 'risk_request', 'risk_request_v1', 'risk_response', 'risk_response_v1', 'alert', 'alert_v1', 'model_status', 'forecast', 'error'):
        doc = json.loads((C/(name+'.schema.json')).read_text(encoding='utf8'))
        Draft202012Validator.check_schema(doc)
        doc['$id'] = BASE+name+'.schema.json'
        docs[name] = doc
        reg = reg.with_resource(doc['$id'], Resource.from_contents(doc))
    def validator(ref):
        return Draft202012Validator({'$ref': BASE+ref}, registry=reg, format_checker=FormatChecker())
    return validator


def test_create_session_and_response_fields(validators):
    create = validators('replay.schema.json#/$defs/create_request')
    assert create.is_valid({'source_id':'demo'})
    assert create.is_valid({'source_id':'demo', 'start_time':'2025-10-01T12:00:00Z'})
    assert not create.is_valid({}) and not create.is_valid({'source_id':''})
    assert not create.is_valid({'source_id':'demo', 'start_time':'not-a-time'})
    response = validators('replay.schema.json#/$defs/session_response')
    value = {'session_id':SESSION,'source_id':'demo','simulation_time':'2025-10-01T12:00:00Z','status':'READY','version':0}
    assert response.is_valid(value)
    for field in value:
        assert not response.is_valid({k:v for k,v in value.items() if k != field})
    assert not response.is_valid(dict(value, version=-1))
    assert not response.is_valid(dict(value, session_id=SESSION.upper()))
    api = yaml.safe_load((C/'api_contract.yaml').read_text(encoding='utf8'))
    create_op = api['paths']['/api/v1/replay/sessions']['post']
    control_op = api['paths']['/api/v1/replay/sessions/{session_id}/control']['post']
    assert create.is_valid(create_op['requestBody']['content']['application/json']['example'])
    assert response.is_valid(create_op['responses']['201']['content']['application/json']['example'])
    assert response.is_valid(control_op['responses']['200']['content']['application/json']['example'])


def test_control_request_field_rules(validators):
    v = validators('replay.schema.json#/$defs/control_request')
    assert v.is_valid({'action':'PLAY','expected_version':0})
    assert not v.is_valid({'action':'PLAY','expected_version':-1})
    assert not v.is_valid({'action':'PLAY','expected_version':0,'target_time':None})
    assert not v.is_valid({'action':'SEEK','expected_version':0})
    assert v.is_valid({'action':'SEEK','expected_version':0,'target_time':'2025-10-01T12:00:00Z'})


def test_uuid_pagination_and_openapi_defaults(validators):
    v = validators('replay.schema.json#/$defs/track_list')
    page = {'items':[],'total':0,'limit':50,'offset':0,'snapshot_id':SNAPSHOT,'simulation_time':'2025-10-01T12:00:00Z'}
    assert v.is_valid(page)
    for key, bad in [('limit',0),('limit',101),('offset',-1),('snapshot_id','old-token')]:
        assert not v.is_valid(dict(page, **{key:bad}))
    api = yaml.safe_load((C/'api_contract.yaml').read_text(encoding='utf8'))
    op = api['paths']['/api/v1/replay/sessions/{session_id}/tracks']['get']
    params = {p['name']:p for p in op['parameters']}
    assert params['limit']['schema']['default'] == 50
    assert params['offset']['schema']['default'] == 0
    assert '410' in op['responses']
    header = next(p for p in api['paths']['/api/v1/replay/sessions/{session_id}/control']['post']['parameters'] if p['name']=='Idempotency-Key')
    hv = Draft202012Validator(header['schema'])
    assert hv.is_valid('x') and hv.is_valid('x'*128)
    assert not hv.is_valid('') and not hv.is_valid('x'*129)


def test_legacy_and_production_encounter_profiles(validators):
    legacy = json.loads((C/'mock/encounters/encounter_valid.json').read_text(encoding='utf8'))
    assert validators('encounter.schema.json').is_valid(legacy)
    v = validators('encounter_v1.schema.json')
    assert not v.is_valid(legacy)
    production = copy.deepcopy(legacy)
    production['replay_session_id'] = SESSION
    production['encounter_id'] = encounter_id(SESSION, production['pair_id'], production['anchor_timestamp'])
    assert v.is_valid(production)
    production['vessel_a']['vessel_id'] = 'mock-vessel-001'
    assert not v.is_valid(production)


def test_legacy_synthetic_flag_constraint_is_explicit(validators):
    track = json.loads((C/'mock/tracks/track_valid.json').read_text(encoding='utf8'))
    track['source_type'] = 'SYNTHETIC_AIS'
    track['is_simulated'] = False
    assert track['vessel_id'].startswith('physical_mmsi:')
    # This documents the inherited constraint, not a decision on what the flag means.
    assert not validators('replay.schema.json#/$defs/production_track').is_valid(track)


def test_production_identity_rejects_legacy_and_malformed_ids(validators):
    v = validators('replay.schema.json#/$defs/production_vessel_id')
    assert v.is_valid('physical_mmsi:000000001')
    assert v.is_valid('simulated:dataset:stable-id')
    assert not v.is_valid('mock-vessel-001')
    assert not v.is_valid('simulated:missing-dataset')
    assert not v.is_valid('physical_mmsi:000000001\n')


def test_replay_risk_request_legacy_and_production_profiles(validators):
    legacy = json.loads((C/'mock/requests/risk_request_valid.json').read_text(encoding='utf8'))
    assert validators('risk_request.schema.json').is_valid(legacy)
    v = validators('risk_request_v1.schema.json')
    assert not v.is_valid(legacy)
    production = copy.deepcopy(legacy)
    production['replay_session_id'] = SESSION
    production['encounter']['replay_session_id'] = SESSION
    e = production['encounter']
    e['encounter_id'] = encounter_id(SESSION, e['pair_id'], e['anchor_timestamp'])
    assert v.is_valid(production)
    production['replay_session_id'] = None
    assert not v.is_valid(production)


@pytest.mark.parametrize(('name', 'legacy_path'), [
    ('risk_response_v1', 'mock/responses/risk_response_alert.json'),
    ('alert_v1', 'mock/alerts/alert_active.json'),
])
def test_replay_response_legacy_is_not_production(validators, name, legacy_path):
    fixture = json.loads((C/legacy_path).read_text(encoding='utf8'))
    original = name.removesuffix('_v1')
    assert validators(original+'.schema.json').is_valid(fixture)
    v = validators(name+'.schema.json')
    assert not v.is_valid(fixture)
    fixture['replay_session_id'] = SESSION
    enc = encounter_id(SESSION, fixture['pair_id'], '2026-01-01T12:00:00Z')
    if name == 'risk_response_v1':
        fixture['encounter_id'] = enc
    else:
        fixture['opened_encounter_id'] = enc
        fixture['latest_encounter_id'] = enc
    assert v.is_valid(fixture)


def canonical_payload(data, validator):
    """Illustrative contract oracle; validates before comparison, not production code."""
    validator.validate(data)
    result = {'action':data['action']}
    if data['action'] == 'SEEK':
        match = re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?Z', data['target_time'])
        assert match  # Format validated above; V1 wire uses Z.
        datetime.fromisoformat(match.group(1))
        fractional = (match.group(2) or '').rstrip('0')
        result['target_time'] = match.group(1) + ('.'+fractional if fractional else '') + 'Z'
    result['expected_version'] = data['expected_version']
    return json.dumps(result, ensure_ascii=False, separators=(',', ':'))


def test_canonical_payload_order_and_equivalent_utc(validators):
    v = validators('replay.schema.json#/$defs/control_request')
    one = {'action':'SEEK','target_time':'2025-10-01T12:00:00Z','expected_version':0}
    two = {'expected_version':0,'target_time':'2025-10-01T12:00:00.000Z','action':'SEEK'}
    assert canonical_payload(one,v) == canonical_payload(two,v)
    precise = dict(one, target_time='2025-10-01T12:00:00.123456789Z')
    assert '.123456789Z' in canonical_payload(precise,v)
    with pytest.raises(ValidationError):
        canonical_payload({'action':'PLAY','target_time':None,'expected_version':0}, v)


def test_control_retry_version_and_retention_reference():
    """Contract-level scenario only; not a persistence/concurrency implementation."""
    results = {}
    current = {'session':SESSION,'version':0,'status':'READY'}
    sequence = [0]
    def control(source, key, payload, now):
        if not key or len(key)>128:
            return 422, None
        record=results.get((source,key))
        if record and now-record[2] <= timedelta(hours=24):
            return (200, record[1]) if record[0]==payload else (409, None)
        if source != current['session'] or payload[1] != current['version']:
            return 409, None
        action, version=payload
        if action in ('RESET','SEEK'):
            sequence[0] += 1
            current.update(session=f'123e4567-e89b-12d3-a456-{sequence[0]:012d}',version=0,status='READY' if action=='RESET' else 'PAUSED')
        else:
            current.update(version=version+1,status={'PLAY':'PLAYING','PAUSE':'PAUSED'}[action])
        value=copy.deepcopy(current)
        results[(source,key)]=(payload,value,now)
        return 200,value
    now=datetime(2025,1,1,tzinfo=timezone.utc)
    assert control(SESSION,'p',('PLAY',0),now)[1]['version']==1
    assert control(SESSION,'q',('PAUSE',1),now)[1]['version']==2
    assert control(SESSION,'bad',('RESET',1),now)[0]==409
    code, created=control(SESSION,'reset',('RESET',2),now)
    assert code==200 and created['version']==0 and created['status']=='READY' and created['session']!=SESSION
    assert control(SESSION,'reset',('RESET',2),now+timedelta(hours=24))==(200,created)
    assert control(SESSION,'reset',('SEEK',2),now)[0]==409
    assert control(SESSION,'old',('PLAY',2),now)[0]==409
    assert control(SESSION,'',('RESET',2),now)[0]==422
    assert control(SESSION,'x'*129,('RESET',2),now)[0]==422
    code, seek = control(created['session'], 'seek', ('SEEK',0), now)
    assert code==200 and seek['version']==0 and seek['status']=='PAUSED' and seek['session']!=created['session']
