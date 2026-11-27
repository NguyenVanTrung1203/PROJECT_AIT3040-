from dataclasses import replace
import copy

import numpy as np
import pytest
from jsonschema.exceptions import ValidationError

from src.data.track_buffer import TrackBuffer, TrackBufferError, validate_track_snapshot_runtime
from src.runtime.trusted_fixture import FixtureProvider, candidate_ids, _events
from scripts.contract_identity_reference import encounter_id, pair_and_online_roles
from scripts.verify_feature_contract import common_en, velocity_en

ANCHOR = '2024-11-01T00:09:00Z'


@pytest.fixture
def ready():
    p = FixtureProvider(5)
    p.create(ANCHOR)
    s = p.snapshot()
    return p, s, p.candidates(s)


def test_coverage_and_unavailable(ready):
    p, s, c = ready
    assert (c.expected, c.evaluated, c.eligible, c.unavailable) == (10, 10, 6, 4)
    assert len({x.pair_id for x in c.candidates}) == 10
    for row in c.candidates:
        assert row.vessels[0] != row.vessels[1]
        assert (row.pair_id, row.vessels) == pair_and_online_roles(*row.vessels, {'simulated'})
        encounter, reason = p.encounter(s, row)
        assert (reason is None) == (row.unavailable_reason is None)
        if encounter:
            assert encounter.encounter_id == encounter_id(s.session_id, row.pair_id, s.anchor_utc)
            assert encounter.encounter_id != row.pair_id


@pytest.mark.parametrize('count', [2, 3, 5])
def test_pair_count(count):
    ids = [f'simulated:s5-01:{i}' for i in range(count)]
    pairs = candidate_ids(list(reversed(ids)), 5)
    assert len(pairs) == count * (count - 1) // 2
    assert all(pair[1][0].encode() < pair[1][1].encode() for pair in pairs)


@pytest.mark.parametrize('ids,bound', [(['simulated:s5-01:a'] * 2, 5), (['invalid', 'simulated:s5-01:b'], 5), (['simulated:s5-01:a', 'simulated:s5-01:b', 'simulated:s5-01:c'], 2)])
def test_reject_duplicate_invalid_and_overlimit(ids, bound):
    with pytest.raises(ValueError):
        candidate_ids(ids, bound)


def test_envelope_is_immutable_and_forgery_rejected(ready):
    p, s, c = ready
    with pytest.raises(TypeError):
        s.tracks[0]['history'][0]['latitude'] = 0
    with pytest.raises(ValueError, match='UNTRUSTED'):
        p.candidates(replace(s))
    with pytest.raises(ValueError, match='UNTRUSTED'):
        p.encounter(s, replace(c.candidates[0]))


def test_session_seek_reset_new_session_invalidate(ready):
    p, s, c = ready
    p.control('SEEK', '2024-11-01T00:12:00Z')
    with pytest.raises(ValueError):
        p.encounter(s, c.candidates[0])
    s2 = p.snapshot()
    assert (s2.session_id, s2.session_version) != (s.session_id, s.session_version)
    p.control('RESET')
    with pytest.raises(ValueError):
        p.candidates(s2)
    s3 = p.snapshot()
    assert s3.anchor_utc == '2024-11-01T00:00:00Z'
    p.create(ANCHOR)
    with pytest.raises(ValueError):
        p.candidates(s3)


def test_playback_advance_and_backseek(ready):
    p, s, _ = ready
    p.control('PLAY')
    p.advance(60)
    later = p.snapshot()
    assert later.anchor_utc == '2024-11-01T00:10:00Z'
    with pytest.raises(ValueError):
        p.candidates(s)
    p.control('SEEK', '2024-11-01T00:08:00Z')
    earlier = p.snapshot()
    assert earlier.anchor_utc == '2024-11-01T00:08:00Z'
    assert p.candidates(earlier).eligible == 0


def test_features_parity_and_metadata(ready):
    p, s, c = ready
    encounter, reason = p.encounter(s, c.candidates[0])
    assert reason is None
    output = p.features(s, encounter)
    x = output.history
    assert x.shape == (2, 10, 4) and x.dtype == np.float32
    assert not x.flags.writeable and not output.anchors_en.flags.writeable
    with pytest.raises(ValueError):
        x.setflags(write=True)
    tracks = encounter.tracks
    points = np.array([[[h['latitude'], h['longitude'], h['sog_kn'], h['cog_deg']] for h in t['history']] for t in tracks])
    lat0, lon0 = points[0, 0, :2]
    en = common_en(points[:, :, 0], points[:, :, 1], lat0, lon0)
    np.testing.assert_allclose(output.anchors_en, en[:, -1], atol=1e-12)
    np.testing.assert_allclose(x[:, :, :2], en - en[:, -1:, :], atol=1e-6)
    np.testing.assert_allclose(x[:, :, 2:], velocity_en(points[:, :, 2], points[:, :, 3]), atol=1e-5)
    np.testing.assert_allclose(output.anchors_en[0] + x[0, 0, :2], 0, atol=1e-6)
    assert output.sog_cog[0][0] == (points[0, 0, 2], points[0, 0, 3])


def test_g11_and_temporal_validation(ready):
    _, s, _ = ready
    # Convert the provider's frozen representation back to a disposable test copy.
    def thaw(v):
        if hasattr(v, 'items'):
            return {k: thaw(x) for k, x in v.items()}
        if isinstance(v, tuple):
            return [thaw(x) for x in v]
        return v
    original = thaw(s.tracks[0])
    validate_track_snapshot_runtime(original, simulation_clock=ANCHOR)
    for change in ('future', 'age', 'anchor', 'timestamp', 'source'):
        t = copy.deepcopy(original)
        if change == 'future':
            t['history'][0]['source_timestamp'] = ANCHOR
        elif change == 'age':
            t['history'][0]['source_age_seconds'] = 61
        elif change == 'anchor':
            t['anchor_timestamp'] = '2024-11-01T00:10:00Z'
        elif change == 'timestamp':
            t['history'][0]['nominal_timestamp'] = 'invalid'
        elif change == 'source':
            t['source_type'] = 'REAL_AIS'
        with pytest.raises((TrackBufferError, ValueError, ValidationError)):
            validate_track_snapshot_runtime(t, simulation_clock=ANCHOR)


def test_nonfinite_event_rejected_before_snapshot():
    event = _events()[0]
    event['latitude'] = float('nan')
    with pytest.raises(TrackBufferError):
        TrackBuffer('session').ingest(event, session_id='session')


def test_source_age_inclusive_boundaries(ready):
    _, s, _ = ready
    def thaw(v):
        return {k: thaw(x) for k, x in v.items()} if hasattr(v, 'items') else [thaw(x) for x in v] if isinstance(v, tuple) else v
    t = thaw(s.tracks[0])
    t['history'][1]['source_timestamp'] = t['history'][0]['source_timestamp']
    t['history'][1]['source_age_seconds'] = 60
    validate_track_snapshot_runtime(t, simulation_clock=ANCHOR)
    t['history'][1]['source_age_seconds'] = 60.1
    with pytest.raises((TrackBufferError, ValidationError)):
        validate_track_snapshot_runtime(t, simulation_clock=ANCHOR)


def test_provider_bound_is_not_silent():
    p = FixtureProvider(2)
    p.create(ANCHOR)
    with pytest.raises(ValueError, match='VESSEL_BOUND_EXCEEDED'):
        p.snapshot()


def test_fixture_geometry_and_no_future_history(ready):
    p, s, _ = ready
    tracks = {t['vessel_id'].split(':')[-1]: t for t in s.tracks}
    def separation(a, b, index):
        pa, pb = tracks[a]['history'][index], tracks[b]['history'][index]
        return np.linalg.norm(common_en(pa['latitude'], pa['longitude'], pb['latitude'], pb['longitude']))
    assert separation('a', 'b', -1) < separation('a', 'b', 0)
    assert separation('c', 'd', -1) > separation('c', 'd', 0)
    for track in s.tracks:
        for point in track['history']:
            assert point['source_timestamp'] <= point['nominal_timestamp'] <= s.anchor_utc
            assert point['original_source_timestamp'] is None
    p.control('SEEK', '2024-11-01T00:15:00Z')
    later = p.snapshot()
    assert p.candidates(later).eligible == 10


def test_foreign_candidate_and_encounter_cannot_cross_sessions(ready):
    p, s, coverage = ready
    encounter, _ = p.encounter(s, coverage.candidates[0])
    other = FixtureProvider(5)
    other.create(ANCHOR)
    other_snapshot = other.snapshot()
    other.candidates(other_snapshot)
    with pytest.raises(ValueError, match='UNTRUSTED'):
        other.encounter(other_snapshot, coverage.candidates[0])
    with pytest.raises(ValueError, match='UNTRUSTED'):
        other.features(other_snapshot, encounter)
