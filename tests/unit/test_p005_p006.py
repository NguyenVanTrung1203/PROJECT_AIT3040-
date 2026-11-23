"""P0-05/06 contract checks and test-only session model; no Replay runtime."""
import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from pydantic import ValidationError
import pytest

from backend.app.mock_tracks import MOCK_TRACKS, TrackSnapshot

ROOT = Path(__file__).resolve().parents[2]
BASE = 'https://schemas.ait3040.invalid/contracts/'


@pytest.fixture(scope='module')
def validators():
    registry = Registry()
    for name in ('common', 'track_snapshot', 'replay'):
        doc = json.loads((ROOT/'contracts'/f'{name}.schema.json').read_text(encoding='utf8'))
        doc['$id'] = BASE + name + '.schema.json'
        registry = registry.with_resource(doc['$id'], Resource.from_contents(doc))
    def get(ref):
        return Draft202012Validator({'$ref':BASE+ref}, registry=registry, format_checker=FormatChecker())
    return get


@pytest.mark.parametrize(('source','simulated','vessel','mmsi','accepted'), [
    ('REAL_AIS', False, 'physical_mmsi:123456789', '123456789', True),
    ('SYNTHETIC_AIS', True, 'physical_mmsi:123456789', '123456789', True),
    ('SYNTHETIC_AIS', True, 'simulated:demo:vessel-1', None, True),
    ('YANG_LEI', True, 'simulated:demo:vessel-1', None, True),
    ('REAL_AIS', False, 'physical_mmsi:123456789', 'bad', False),
    ('REAL_AIS', False, 'simulated:demo:vessel-1', '123456789', False),
    ('SYNTHETIC_AIS', False, 'physical_mmsi:123456789', '123456789', False),
])
def test_trajectory_provenance_and_identity_common_cases(validators, source, simulated, vessel, mmsi, accepted):
    payload = MOCK_TRACKS[0].model_dump(mode='json')
    payload.update(source_type=source, is_simulated=simulated, vessel_id=vessel, mmsi=mmsi)
    if source == 'YANG_LEI':
        for p in payload['history']:
            p['source_timestamp'] = p['original_source_timestamp'] = p['source_age_seconds'] = None
        payload['current_state'] = copy.deepcopy(payload['history'][-1])
    structural = validators('replay.schema.json#/$defs/production_track').is_valid(payload)
    try:
        TrackSnapshot.model_validate(payload)
        pydantic = True
    except ValidationError:
        pydantic = False
    assert structural == pydantic == accepted


def test_physical_identity_requires_matching_mmsi_semantics(validators):
    payload = MOCK_TRACKS[0].model_dump(mode='json')
    payload.update(source_type='SYNTHETIC_AIS', is_simulated=True,
                   vessel_id='physical_mmsi:123456789', mmsi='987654321')
    # Standard JSON Schema cannot compare two distinct string fields: this is
    # a documented semantic obligation, not a claim that structural schema rejects it.
    assert validators('replay.schema.json#/$defs/production_track').is_valid(payload)
    with pytest.raises(ValidationError, match='must match'):
        TrackSnapshot.model_validate(payload)


def test_legacy_and_production_namespace_are_separate(validators):
    payload = MOCK_TRACKS[0].model_dump(mode='json')
    assert validators('track_snapshot.schema.json').is_valid(payload)
    assert not validators('replay.schema.json#/$defs/production_track').is_valid(payload)
    assert TrackSnapshot.model_validate(payload).vessel_id.startswith('mock-vessel-')
    for field in ('schema_version', 'mmsi'):
        bad = dict(payload)
        del bad[field]
        assert not validators('track_snapshot.schema.json').is_valid(bad)
        with pytest.raises(ValidationError):
            TrackSnapshot.model_validate(bad)


TABLE = {
    'READY':   {'PLAY':'PLAYING','PAUSE':409,'RESUME':409,'RESET':'NEW_READY','SEEK':'NEW_PAUSED'},
    'PLAYING': {'PLAY':409,'PAUSE':'PAUSED','RESUME':409,'RESET':'NEW_READY','SEEK':'NEW_PAUSED'},
    'PAUSED':  {'PLAY':'PLAYING','PAUSE':409,'RESUME':'PLAYING','RESET':'NEW_READY','SEEK':'NEW_PAUSED'},
    'ENDED':   {'PLAY':409,'PAUSE':409,'RESUME':409,'RESET':409,'SEEK':409},
    'EXPIRED': {'PLAY':410,'PAUSE':410,'RESUME':410,'RESET':410,'SEEK':410},
}


def test_contract_schema_exposes_approved_matrix():
    schema = json.loads((ROOT/'contracts/replay.schema.json').read_text(encoding='utf8'))
    assert schema['x-control-transition-matrix'] == TABLE


class SessionModel:
    """Illustrates atomic contract rules only; never used as a production engine."""
    def __init__(self, state='READY', version=0):
        self.source = {'id':'source','state':state,'version':version,'time':10}
        self.current = self.source
        self.created = []
        self.saved = {}
        self.alerts = {('source','pair'):'ACTIVE'}

    def apply(self, action, expected, key=None, target=None):
        payload = (action, target, expected)
        if key is not None and key in self.saved:
            old_payload, result = self.saved[key]
            return result if old_payload == payload else (409, None)
        if self.source['state'] == 'EXPIRED':
            return 410, None
        if self.source['version'] != expected:
            return 409, None
        outcome = TABLE[self.source['state']][action]
        if isinstance(outcome, int):
            return outcome, None
        if action in ('RESET','SEEK') and (not key or len(key)>128):
            return 422, None
        if action == 'SEEK' and (target is None or not 0 <= target <= 100):
            return 422, None
        if action in ('RESET','SEEK'):
            self.source['state'] = 'ENDED'
            self.source['version'] += 1
            self.current = {'id':f'new-{len(self.created)+1}','state':outcome[4:],
                            'version':0,'time':0 if action=='RESET' else target}
            self.created.append(self.current)
        else:
            self.source['state'] = outcome
            self.source['version'] += 1
        result = (200, copy.deepcopy(self.current))
        if key is not None:
            self.saved[key] = (payload, result)
        return result


@pytest.mark.parametrize(('state','action','expected'), [(s,a,TABLE[s][a]) for s in TABLE for a in TABLE[s]])
def test_all_25_state_action_cases(state, action, expected):
    model = SessionModel(state, 3)
    status, effective = model.apply(action, 3, key='key', target=20 if action=='SEEK' else None)
    if isinstance(expected, int):
        assert status == expected and effective is None and model.source['version']==3
    else:
        assert status == 200
        if action in ('RESET','SEEK'):
            assert model.source['state']=='ENDED' and model.source['version']==4
            assert effective['id']!='source' and effective['state']==expected[4:] and effective['version']==0
            assert effective['time']==(0 if action=='RESET' else 20)
            assert ('new-1','pair') not in model.alerts
        else:
            assert effective['id']=='source' and effective['state']==expected and effective['version']==4


@pytest.mark.parametrize('action', ['RESET','SEEK'])
def test_control_retry_conflict_and_old_session_isolation(action):
    model = SessionModel('PLAYING', 2)
    target = 20 if action == 'SEEK' else None
    first = model.apply(action, 2, key='key', target=target)
    assert first[0]==200 and model.source['version']==3
    assert model.apply(action, 2, key='key', target=target)==first
    assert len(model.created)==1 and model.source['version']==3
    assert model.apply(action, 1, key='key', target=target)[0]==409
    assert model.apply('PLAY', 3, key='different')[0]==409
    assert ('new-1','pair') not in model.alerts


def test_same_version_competing_controls_and_auto_end():
    model = SessionModel('READY', 0)
    assert model.apply('PLAY', 0, key='one')[0]==200
    assert model.apply('RESET', 0, key='two')[0]==409
    model.source['state'] = 'ENDED'  # auto-end is not an alert decision
    assert model.alerts[('source','pair')]=='ACTIVE'
    assert model.apply('RESET', 1, key='three')[0]==409


@pytest.mark.parametrize('target', [None, -1, 101])
def test_seek_rejects_missing_or_out_of_range_target(target):
    model = SessionModel('READY', 0)
    assert model.apply('SEEK', 0, key='key', target=target)[0] == 422
    assert model.source == {'id':'source','state':'READY','version':0,'time':10}
    assert not model.created


def test_reset_requires_idempotency_key_without_state_change():
    model = SessionModel('READY', 0)
    assert model.apply('RESET', 0)[0] == 422
    assert model.source['state'] == 'READY' and model.source['version'] == 0
