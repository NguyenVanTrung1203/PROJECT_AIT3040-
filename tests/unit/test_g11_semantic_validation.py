"""Versioned G11 structural + semantic vectors; no production runtime claim."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as SchemaError
from referencing import Registry, Resource
from pydantic import ValidationError

from backend.app.mock_tracks import TrackSnapshot
from src.data.track_semantics import validate_production_track_g11, validate_track_semantics

ROOT = Path(__file__).resolve().parents[2]
BASE = 'https://schemas.ait3040.invalid/contracts/'
VECTOR_FILE = ROOT/'contracts/validation_vectors/g11_track_v1.json'
DATA = json.loads(VECTOR_FILE.read_text(encoding='utf-8'))
CASES = DATA['cases']


@pytest.fixture(scope='module')
def schemas():
    registry = Registry()
    for name in ('common', 'track_snapshot', 'replay'):
        doc = json.loads((ROOT/'contracts'/f'{name}.schema.json').read_text(encoding='utf-8'))
        doc['$id'] = BASE+name+'.schema.json'
        Draft202012Validator.check_schema(doc)
        registry = registry.with_resource(doc['$id'], Resource.from_contents(doc))
    def make(ref):
        return Draft202012Validator({'$ref':BASE+ref}, registry=registry, format_checker=FormatChecker())
    return {'PRODUCTION_V1':make('replay.schema.json#/$defs/production_track'),
            'LEGACY_MOCK':make('track_snapshot.schema.json')}


@pytest.mark.parametrize('case', CASES, ids=lambda x: x['case_id'])
def test_versioned_g11_vectors(case, schemas):
    payload, profile = case['payload'], case['profile']
    structural = schemas[profile].is_valid(payload)
    try:
        validate_track_semantics(payload, profile=profile)
        semantic = True
    except ValueError:
        semantic = False
    try:
        if profile == 'PRODUCTION_V1':
            validate_production_track_g11(payload)
        else:
            schemas[profile].validate(payload)
            validate_track_semantics(payload, profile=profile)
        combined = True
    except (ValueError, SchemaError):
        combined = False
    try:
        TrackSnapshot.model_validate(payload)
        pydantic = True
    except ValidationError:
        pydantic = False
    assert (structural, semantic, combined, pydantic) == tuple(case[k] for k in
        ('structural_expected','semantic_expected','combined_expected','pydantic_expected'))
    if profile == 'PRODUCTION_V1' and case['case_id'] not in ('mock_as_production', 'invalid_namespace'):
        assert combined == pydantic  # same production-compatible inputs; model itself is a legacy consumer


def test_vector_version_and_unique_ids():
    assert DATA['vector_version'] == '1.0.0'
    assert len({case['case_id'] for case in CASES}) == len(CASES) == 13


def test_javascript_semantics_against_same_vectors():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable; JS consumer unverified')
    program = r'''const fs=require('fs'); const data=JSON.parse(fs.readFileSync(0,'utf8'));
function valid(t,profile) {
 if(!['vessel_id','mmsi','source_type','is_simulated'].every(k=>Object.hasOwn(t,k))) return false;
 const v=t.vessel_id,m=t.mmsi,s=t.source_type,i=t.is_simulated;
 if(typeof v!=='string'||!v||typeof i!=='boolean') return false;
 if(m!==null&&(typeof m!=='string'||!/^[0-9]{9}$/.test(m))) return false;
 if(!['REAL_AIS','SYNTHETIC_AIS','YANG_LEI'].includes(s)) return false;
 if(s==='REAL_AIS'&&(i||m===null||!v.startsWith('physical_mmsi:'))) return false;
 if(s!=='REAL_AIS'&&!i) return false;
 if(v.startsWith('physical_mmsi:')&&(m===null||v!=='physical_mmsi:'+m)) return false;
 if(v.startsWith('simulated:')&&m!==null) return false;
 if(profile==='PRODUCTION_V1') {
  if(v!==v.normalize('NFC')) return false;
  if(v.startsWith('physical_mmsi:')) return true;
  if(!v.startsWith('simulated:')) return false;
  const tail=v.slice('simulated:'.length), k=tail.indexOf(':');
  if(k<=0||k===tail.length-1) return false;
 }
 return true;
}
console.log(JSON.stringify(data.cases.map(c=>valid(c.payload,c.profile))));'''
    out = subprocess.run([node,'-e',program], input=json.dumps(DATA,ensure_ascii=True),
                         capture_output=True,text=True,check=True)
    assert json.loads(out.stdout) == [c['semantic_expected'] for c in CASES]
