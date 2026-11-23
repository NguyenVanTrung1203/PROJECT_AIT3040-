"""Illustrative in-memory examples of approved invariants, not a replay runtime test."""
import pytest


class ReferenceExample:
    def __init__(self):
        self.session = 'S1'
        self.count = 1
        self.records = {}
        self.latest = {}
        self.alerts = {}

    def control(self, session, key, action, target=None):
        identity = (session, key)
        payload = (action, target)
        if identity in self.records:
            previous_payload, result = self.records[identity]
            if previous_payload != payload:
                raise ValueError('conflict')
            return result
        if session != self.session:
            raise ValueError('old session')
        if action in ('reset', 'seek'):
            self.count += 1
            self.session = f'S{self.count}'
        self.records[identity] = (payload, self.session)
        return self.session

    def evaluate(self, session, pair, anchor, decision):
        if session != self.session:
            raise ValueError('old session')
        identity = (session, pair)
        if anchor <= self.latest.get(identity, -1):
            return
        self.latest[identity] = anchor
        if decision is None and identity in self.alerts:
            self.alerts[identity] = 'DATA_UNAVAILABLE'
        elif decision is True:
            self.alerts[identity] = 'ACTIVE'
        elif decision is False and identity in self.alerts:
            self.alerts[identity] = 'RESOLVED'


@pytest.mark.parametrize(('action', 'target'), [('reset', None), ('seek', -1), ('seek', 1)])
def test_reset_and_any_seek_create_one_isolated_session(action, target):
    ref = ReferenceExample()
    ref.evaluate('S1', 'pair', 1, True)
    created = ref.control('S1', 'key', action, target)
    assert created != 'S1'
    assert ref.control('S1', 'key', action, target) == created
    assert (created, 'pair') not in ref.alerts
    with pytest.raises(ValueError):
        ref.evaluate('S1', 'pair', 2, False)


@pytest.mark.parametrize('action', ['play', 'pause', 'resume'])
def test_play_pause_resume_keep_session(action):
    ref = ReferenceExample()
    assert ref.control('S1', 'key', action) == 'S1'


def test_control_conflict_and_old_evaluation_do_not_mutate():
    ref = ReferenceExample()
    ref.control('S1', 'key', 'pause')
    with pytest.raises(ValueError, match='conflict'):
        ref.control('S1', 'key', 'resume')
    ref.evaluate('S1', 'pair', 10, True)
    ref.evaluate('S1', 'pair', 10, False)
    ref.evaluate('S1', 'pair', 9, False)
    assert ref.alerts[('S1', 'pair')] == 'ACTIVE'
    ref.evaluate('S1', 'pair', 11, None)
    assert ref.alerts[('S1', 'pair')] == 'DATA_UNAVAILABLE'


def test_end_does_not_resolve_alert():
    ref = ReferenceExample()
    ref.evaluate('S1', 'pair', 1, True)
    assert ref.control('S1', 'end-key', 'end') == 'S1'
    assert ref.alerts[('S1', 'pair')] == 'ACTIVE'
