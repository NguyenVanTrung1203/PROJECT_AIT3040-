import hashlib,json,math
from collections import defaultdict
import numpy as np
from src.runtime.trusted_fixture import _events,_events_legacy,SOURCE,LEGACY_SOURCE,LEGACY_ORIGIN,WATER_ORIGIN,FixtureProvider

def test_legacy_fixture_is_exact_and_relocated_source_is_distinct():
 old=_events_legacy(); new=_events()
 assert hashlib.sha256(json.dumps(old,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()=='63280728ebd47f69fd23118d82bb7b1ac8f82cb426d8b52391f3bca423e5d06b'
 assert len(old)==len(new)==100 and SOURCE=='s5-01-synthetic-denmark-water-v2' and SOURCE!=LEGACY_SOURCE
 assert all(x['provenance']['source_file']==SOURCE for x in new)
 assert set(FixtureProvider(5)._api.sources)=={SOURCE}
 for a,b in zip(old,new):
  assert a['timestamp_utc']==b['timestamp_utc'] and a['vessel_id']==b['vessel_id'] and a['sog_kn']==b['sog_kn'] and a['cog_deg']==b['cog_deg']
  assert abs(a['latitude']-b['latitude'])<1e-12 and abs((b['longitude']-a['longitude'])-(WATER_ORIGIN[1]-LEGACY_ORIGIN[1]))<1e-12

def test_common_en_and_all_pairwise_distances_preserved():
 old=_events_legacy(); new=_events(); groups=defaultdict(list)
 for a,b in zip(old,new):
  ea=(a['longitude']-LEGACY_ORIGIN[1])*60*math.cos(math.radians(LEGACY_ORIGIN[0])); na=(a['latitude']-LEGACY_ORIGIN[0])*60
  eb=(b['longitude']-WATER_ORIGIN[1])*60*math.cos(math.radians(WATER_ORIGIN[0])); nb=(b['latitude']-WATER_ORIGIN[0])*60
  np.testing.assert_allclose([ea,na],[eb,nb],rtol=0,atol=1e-11);groups[a['timestamp_utc']].append(([ea,na],[eb,nb]))
 for values in groups.values():
  for i in range(len(values)):
   for j in range(i+1,len(values)):
    assert abs(np.linalg.norm(np.subtract(values[i][0],values[j][0]))-np.linalg.norm(np.subtract(values[i][1],values[j][1])))<1e-11

def test_e_appearance_and_history_unchanged():
 for events in (_events_legacy(),_events()):
  e=[x for x in events if x['vessel_id'].endswith(':e')]
  assert e[0]['timestamp_utc']=='2024-11-01T00:05:00Z' and len(e)==16
  assert sum(x['timestamp_utc']<='2024-11-01T00:09:00Z' for x in e)==5
  assert sum(x['timestamp_utc']<='2024-11-01T00:14:00Z' for x in e)==10
