"""Approved contract vectors and partial schemas; no production runtime implied."""
import json
import shutil
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
import pytest
import yaml

from scripts.contract_identity_reference import pair_and_online_roles, encounter_id

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / 'contracts'
NS = {'physical_mmsi', 'simulated'}  # Test registry only; production namespace registry is pending.
SESSION = '123e4567-e89b-12d3-a456-426614174000'
ANCHOR = '2025-10-01T12:00:00Z'
VECTORS = [
    ('physical_mmsi:000000001', 'physical_mmsi:000000002', '5edcd44d2d37a0ada2de37283483f76bbddc8bb9c5bb22b8992b7f7297cf5c18'),
    ('simulated:demo:a', 'simulated:demo:b', '4ca3f457062383c8d067fb89c9f86a50786bd3fe71dfb9447a25616ee0edc7ff'),
    ('simulated:demo:e\u0301', 'simulated:demo:z', 'f57e47b39cc80588b6c15944c4b7984a6ef771e7e69f55557a5f95c4125e7062'),
    ('simulated:demo:\ue000', 'simulated:demo:\U00010000', 'a4526e482e99b25de4d79d8bf925f6307f62f8102b33fed845be21b164b2bbb2'),
    ('simulated:demo:quote"\\\n', 'simulated:demo:x', '0f72689d24c015c483ca890c7225b93204c1b132ac977445da2bbaac02da61f3'),
]


@pytest.mark.parametrize(('a', 'b', 'digest'), VECTORS)
def test_pair_vectors_and_online_roles(a, b, digest):
    pair, roles = pair_and_online_roles(a, b, NS)
    assert pair == 'pair:v1:' + digest
    assert (pair, roles) == pair_and_online_roles(b, a, NS)
    assert roles[0].encode('utf-8') < roles[1].encode('utf-8')


@pytest.mark.parametrize(('a', 'b'), [
    ('simulated:demo:a', 'simulated:demo:a'), ('simulated:demo:e\u0301', 'simulated:demo:\u00e9'),
    ('invalid:x', 'simulated:demo:y'), ('physical_mmsi:123', 'simulated:demo:y'), ('', 'simulated:demo:y'), ('simulated:missing', 'simulated:demo:y'),
    ('simulated_mmsi:123', 'simulated:demo:y'),
])
def test_pair_rejects_invalid_or_duplicate(a, b):
    with pytest.raises(ValueError):
        pair_and_online_roles(a, b, NS)


def test_encounter_vector_precision_and_identity():
    pair, _ = pair_and_online_roles(VECTORS[0][0], VECTORS[0][1], NS)
    expected = 'enc:v1:044186cd64489fb72600d1aeb385509204ee6bee4d3a5b7b5c660d845d868529'
    assert encounter_id(SESSION, pair, ANCHOR) == expected
    assert encounter_id(SESSION, pair, '2025-10-01T12:00:00+00:00') == expected
    assert encounter_id('123e4567-e89b-12d3-a456-426614174001', pair, ANCHOR) != expected
    assert encounter_id(SESSION, 'pair:v1:' + '0'*64, ANCHOR) != expected
    assert encounter_id(SESSION, pair, '2025-10-01T12:00:01Z') != expected
    for session, p, anchor in [(SESSION, pair, '2025-10-01T12:00:00.001Z'), ('bad', pair, ANCHOR), (SESSION, 'bad', ANCHOR)]:
        with pytest.raises(ValueError):
            encounter_id(session, p, anchor)


def test_python_javascript_vectors():
    node = shutil.which('node')
    if not node:
        pytest.skip('node unavailable; cross-language compatibility unverified')
    program = r'''const crypto=require('crypto'); const data=JSON.parse(process.argv[1]);
const h=s=>crypto.createHash('sha256').update(s,'utf8').digest('hex');
const ids=[data.a.normalize('NFC'),data.b.normalize('NFC')].sort((a,b)=>Buffer.compare(Buffer.from(a,'utf8'),Buffer.from(b,'utf8')));
const pair='pair:v1:'+h(JSON.stringify(ids));
console.log(JSON.stringify({pair,enc:'enc:v1:'+h(JSON.stringify([data.session,pair,data.anchor]))}));'''
    for a, b, _ in VECTORS:
        data = json.dumps({'a': a, 'b': b, 'session': SESSION, 'anchor': ANCHOR}, ensure_ascii=True)
        result = subprocess.run([node, '-e', program, data], capture_output=True, text=True, check=True)
        result = json.loads(result.stdout)
        pair = pair_and_online_roles(a, b, NS)[0]
        assert result == {'pair': pair, 'enc': encounter_id(SESSION, pair, ANCHOR)}


@pytest.fixture(scope='module')
def replay():
    base = 'https://schemas.ait3040.invalid/contracts/'
    docs = {}
    reg = Registry()
    for name in ('common', 'track_snapshot', 'replay'):
        doc = json.loads((CONTRACTS / (name + '.schema.json')).read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(doc)
        doc['$id'] = base + name + '.schema.json'
        docs[name] = doc
        reg = reg.with_resource(doc['$id'], Resource.from_contents(doc))
    return lambda name: Draft202012Validator({'$ref':base+'replay.schema.json#/$defs/'+name}, registry=reg, format_checker=FormatChecker())


def test_control_schema_approved_fields(replay):
    v = replay('control_request')
    assert v.is_valid({'action':'SEEK', 'target_time':'2025-10-01T12:00:00Z', 'expected_version':1})
    assert not v.is_valid({'action':'SEEK', 'expected_version':1})
    assert not v.is_valid({'action':'PAUSE'})
    assert not v.is_valid({'action':'WRONG', 'expected_version':1})
    assert not v.is_valid({'action':'SEEK', 'target_time':'2025-10-01T12:00:00+01:00', 'expected_version':1})


@pytest.mark.parametrize('state', ['READY', 'PLAYING', 'PAUSED', 'ENDED', 'EXPIRED'])
def test_approved_session_states(replay, state):
    assert replay('session_state').is_valid(state)
    assert not replay('session_state').is_valid('INVALID')


def test_reference_control_transitions_and_version_conflicts():
    # Small test-only oracle; it is not an implementation or proof of runtime atomicity.
    def apply(state, version, action, expected):
        if version != expected:
            return 'CONFLICT', state, version, False
        result = {'PLAY':'PLAYING', 'PAUSE':'PAUSED', 'RESUME':'PLAYING',
                  'RESET':'READY', 'SEEK':'PAUSED'}[action]
        return 'OK', result, version + 1, action in ('RESET', 'SEEK')
    for action, status, new in [('PLAY','PLAYING',False),('PAUSE','PAUSED',False),
                                ('RESUME','PLAYING',False),('RESET','READY',True),('SEEK','PAUSED',True)]:
        assert apply('READY', 3, action, 3) == ('OK', status, 4, new)
        assert apply('READY', 3, action, 2) == ('CONFLICT', 'READY', 3, False)


def test_track_list_schema_and_limit(replay):
    v = replay('track_list')
    page = {'items':[], 'total':0, 'limit':100, 'offset':0, 'snapshot_id':'123e4567-e89b-12d3-a456-426614174002', 'simulation_time':ANCHOR}
    assert v.is_valid(page)
    for name in page:
        assert not v.is_valid({k:value for k,value in page.items() if k != name})
    assert not v.is_valid(dict(page,limit=101)) and not v.is_valid(dict(page,limit=0))


def test_openapi_replay_paths_and_statuses():
    api = yaml.safe_load((CONTRACTS/'api_contract.yaml').read_text(encoding='utf-8'))
    base = '/api/v1/replay/sessions'
    assert {'201','422','503'} <= set(api['paths'][base]['post']['responses'])
    for suffix in ('/{session_id}', '/{session_id}/control', '/{session_id}/tracks', '/{session_id}/tracks/{vessel_id}'):
        operation = api['paths'][base+suffix]['post' if suffix.endswith('/control') else 'get']
        assert {'200','404','410','422','503'} <= set(operation['responses'])
    control=api['paths'][base+'/{session_id}/control']['post']
    assert '409' in control['responses']
    assert any(x['name']=='Idempotency-Key' and not x['required'] for x in control['parameters'])
    key = next(x for x in control['parameters'] if x['name']=='Idempotency-Key')
    assert key['schema']['minLength'] == 1 and key['schema']['maxLength'] == 128


def test_openapi_replay_examples_match_partial_schemas(replay):
    api = yaml.safe_load((CONTRACTS/'api_contract.yaml').read_text(encoding='utf-8'))
    base = '/api/v1/replay/sessions/{session_id}'
    control = api['paths'][base+'/control']['post']['requestBody']['content']['application/json']['example']
    page = api['paths'][base+'/tracks']['get']['responses']['200']['content']['application/json']['example']
    assert replay('control_request').is_valid(control)
    assert replay('track_list').is_valid(page)


def test_snapshot_pagination_example_and_expiry():
    # Illustrates a frozen snapshot; no claim that a server implements it yet.
    frozen = tuple(sorted(['simulated:b', 'simulated:a'], key=lambda x: x.encode('utf-8')))
    def page(offset, now_seconds):
        if now_seconds >= 300:
            raise TimeoutError('410')
        return frozen[offset:offset+1]
    assert page(0, 1) + page(1, 299) == ('simulated:a', 'simulated:b')
    with pytest.raises(TimeoutError, match='410'):
        page(1, 300)


def test_error_response_example_matches_existing_schema():
    schema = json.loads((CONTRACTS/'error.schema.json').read_text(encoding='utf-8'))
    common = json.loads((CONTRACTS/'common.schema.json').read_text(encoding='utf-8'))
    base = 'https://schemas.ait3040.invalid/contracts/'
    schema['$id'], common['$id'] = base+'error.schema.json', base+'common.schema.json'
    registry = Registry().with_resource(common['$id'], Resource.from_contents(common))
    example = {'schema_version':'1.0.0', 'error_code':'CONFLICT', 'message':'conflict', 'request_id':None, 'details':None}
    Draft202012Validator(schema, registry=registry).validate(example)
