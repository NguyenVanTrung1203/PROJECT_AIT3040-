"""Synthetic-only HTTP boundary over one process-local replay authority."""
from __future__ import annotations

import os
import threading
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from backend.app.replay_api import APIProblem
from src.runtime.config import load_config
from src.runtime.batch_scheduler import AutomaticEvaluationScheduler
from src.runtime.m5a_service import M5aRuntime, RuntimeUnavailable
from src.runtime.trusted_fixture import FixtureProvider, SOURCE


class ReplayAuthority:
    """Shares the fixture provider's replay instance with the existing routes."""
    def __init__(self, provider):
        self.provider = provider
        self.api = provider._api

    def active_s5_session(self):
        """Return the authoritative active S5 session, if one exists.

        The provider is the singleton owner for the synthetic S5 source. Keep
        discovery and session creation under the same lock so concurrent tabs
        cannot observe an empty slot and create a second session.
        """
        p = self.provider
        with p._lock:
            current = p._session
            if current is None:
                return None
            try:
                view = self.api.get_session(current.session_id)
            except APIProblem as exc:
                if exc.status_code != 410:
                    raise
                # An expired session is no longer active. Retain ReplayAPI's
                # history; only release the singleton's active-session pointer.
                p._session, p._snapshot, p._candidates = None, None, ()
                return None
            if view.source_id != SOURCE:
                raise APIProblem(503, 'ACTIVE_SESSION_SOURCE_MISMATCH',
                                 'The active S5 session has an unexpected source')
            if view.status not in {'READY', 'PAUSED', 'PLAYING'}:
                # ENDED sessions remain in ReplayAPI but no longer occupy the
                # active S5 slot. No live session is reset or deleted here.
                p._session, p._snapshot, p._candidates = None, None, ()
                return None
            p._session = view
            return view

    def create_session(self, request):
        p = self.provider
        with p._lock:
            if request.source_id == SOURCE:
                if self.active_s5_session() is not None:
                    raise APIProblem(409, 'S5_SESSION_EXISTS', 'Only one active S5 fixture session per process is supported')
                view = self.api.create_session(request)
                p._session, p._snapshot, p._candidates = view, None, ()
                return view
            return self.api.create_session(request)

    def _check_session(self, session_id):
        view = self.api.get_session(session_id)
        if view.source_id == SOURCE and (self.provider._session is None or self.provider._session.session_id != session_id):
            raise APIProblem(409, 'SESSION_STALE', 'The S5 session was replaced')
        return view

    def get_session(self, session_id):
        with self.provider._lock:
            return self._check_session(session_id)

    def control(self, session_id, request, idempotency_key):
        p = self.provider
        with p._lock:
            current = self.api.get_session(session_id)
            if current.source_id == SOURCE and (p._session is None or p._session.session_id != session_id):
                # Allow only an idempotent retry of a completed handoff.
                if request.action not in ('SEEK', 'RESET') or not idempotency_key:
                    raise APIProblem(409, 'SESSION_STALE', 'The S5 session was replaced')
                result = self.api.control(session_id, request, idempotency_key)
                if p._session is None or result.session_id != p._session.session_id:
                    raise APIProblem(409, 'SESSION_STALE', 'The S5 session was replaced')
                return result
            result = self.api.control(session_id, request, idempotency_key)
            if current.source_id == SOURCE:
                p._session, p._snapshot, p._candidates = result, None, ()
            return result

    def list_tracks(self, session_id, **kwargs):
        with self.provider._lock:
            self._check_session(session_id)
            return self.api.list_tracks(session_id, **kwargs)

    def get_track(self, session_id, vessel_id, **kwargs):
        with self.provider._lock:
            self._check_session(session_id)
            return self.api.get_track(session_id, vessel_id, **kwargs)


class RuntimeState:
    def __init__(self):
        self.provider = FixtureProvider(5, backend_replay=True)
        self.replay = ReplayAuthority(self.provider)
        self._lifecycle_lock = threading.RLock()
        self._model = None
        self._harness = None
        self._coverage = None
        self._error = 'NOT_INITIALIZED'
        self._closed = False
        self.scheduler = AutomaticEvaluationScheduler(self)

    def start(self):
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeUnavailable('SERVICE_CLOSED')
            self.scheduler.start()

    def close(self):
        # Stop/cancel scheduler work before taking the model lifecycle lock.
        # The worker may need that lock to obtain the one runtime instance.
        self.scheduler.close()
        with self._lifecycle_lock:
            self._closed = True
            if self._model is not None:
                self._model.close()

    def model(self):
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeUnavailable('SERVICE_CLOSED')
            if self._harness is None:
                try:
                    from src.runtime.risk_service import FixtureRiskHarness
                    config = load_config(os.environ)
                    if config.device != 'cpu':
                        raise ValueError('S5-04A requires explicit CPU')
                    model = M5aRuntime(config, self.provider)
                    harness = FixtureRiskHarness(self.provider, model)
                    self._model = model
                    self._harness = harness
                    self._error = None
                except Exception as exc:
                    self._error = 'RUNTIME_CONFIGURATION_OR_ARTIFACT_UNAVAILABLE'
                    raise RuntimeUnavailable(self._error) from exc
            return self._harness

    def coverage(self, session_id, snapshot_id=None):
        p = self.provider
        with p._lock:
            view = self.replay._check_session(session_id)
            if view.source_id != SOURCE:
                raise APIProblem(404, 'SOURCE_NOT_SUPPORTED', 'Runtime requires the S5 fixture source')
            current = p._snapshot
            try:
                if current is not None:
                    p._check(current)
                    # ReplayAPI pins snapshots with a bounded TTL. The trusted
                    # provider also caches its in-process copy, so validate the
                    # API pin before returning that copy after a page reload.
                    self.replay.api.list_tracks(session_id, limit=1, offset=0,
                                                snapshot_id=current.snapshot_id)
            except APIProblem as exc:
                if exc.status_code not in (404, 410):
                    raise
                # The session can remain active after its snapshot expires.
                # Drop only the derived snapshot/coverage so the next
                # snapshot-less candidate request pins the current replay
                # clock again. Callers presenting the old ID receive 409 below.
                p._snapshot, p._candidates = None, ()
                self._coverage = None
                current = None
            except ValueError:
                current = None
            if current is None:
                if snapshot_id is not None:
                    raise APIProblem(409, 'SNAPSHOT_STALE', 'Snapshot no longer represents the replay clock')
                current = p.snapshot()
                self._coverage = p.candidates(current)
            if snapshot_id is not None and snapshot_id != current.snapshot_id:
                raise APIProblem(409, 'SNAPSHOT_STALE', 'Snapshot does not match the current replay state')
            if self._coverage is None or not p._candidates:
                self._coverage = p.candidates(current)
            return current, self._coverage


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: StrictStr = Field(min_length=1, max_length=64)
    pair_id: StrictStr = Field(min_length=1, max_length=80)
    request_id: StrictStr = Field(min_length=1, max_length=128)


router = APIRouter(prefix='/api/v1/runtime', tags=['synthetic-runtime'])


def _error(status, code, message):
    raise HTTPException(status_code=status, detail={'error_code': code, 'message': message, 'details': None})


def _state(request):
    return request.app.state.s5_runtime


@router.get('/status')
def runtime_status(request: Request):
    s = _state(request)
    model_ready = (s._model is not None and not s._closed and
                   s._model._context is not None and not s._model._context.invalidated)
    return {'source_id': SOURCE, 'scope': 'SYNTHETIC_FIXTURE',
            'runtime_status': 'READY' if model_ready else 'UNAVAILABLE',
            'reason': 'SERVICE_CLOSED' if s._closed else
                      'RUNTIME_CONTEXT_INVALIDATED' if s._model is not None and s._model._context.invalidated else s._error,
            'model_load_count': 0 if s._model is None else s._model.load_count,
            'official_alerts': False, 'team_interface_approval': 'PENDING'}


@router.get('/scheduler')
def scheduler_status(request: Request, session_id: str | None = None):
    """Read-only view of the single backend-owned automatic scheduler."""
    return _state(request).scheduler.status(session_id)


@router.get('/active-session')
def active_s5_session(request: Request):
    """Supplemental local-prototype discovery for the single active S5 session."""
    try:
        view = _state(request).replay.active_s5_session()
        return {'session': None if view is None else view.as_contract_response()}
    except APIProblem as exc:
        _error(exc.status_code, exc.error_code, exc.message)


@router.get('/sessions/{session_id}/candidates')
def candidates(session_id: str, request: Request):
    s = _state(request)
    try:
        snapshot, coverage = s.coverage(session_id)
        return {'session_id': snapshot.session_id, 'session_version': snapshot.session_version,
                'snapshot_id': snapshot.snapshot_id, 'anchor_utc': snapshot.anchor_utc,
                'expected': coverage.expected, 'evaluated': coverage.evaluated,
                'eligible': coverage.eligible, 'unavailable': coverage.unavailable,
                'pairs': [{'pair_id': c.pair_id, 'vessel_ids': list(c.vessels),
                           'unavailable_reason': c.unavailable_reason} for c in coverage.candidates]}
    except APIProblem as exc:
        _error(exc.status_code, exc.error_code, exc.message)
    except ValueError as exc:
        _error(503, 'SNAPSHOT_UNAVAILABLE', str(exc))


@router.post('/sessions/{session_id}/evaluate')
def evaluate(session_id: str, body: EvaluationRequest, request: Request):
    s = _state(request)
    try:
        view = s.replay._check_session(session_id)
        if view.status != 'PAUSED':
            _error(409, 'MANUAL_EVALUATION_REQUIRES_PAUSED',
                   'Manual pair evaluation is available only while Replay is PAUSED')
        snapshot, coverage = s.coverage(session_id, body.snapshot_id)
        candidate = next((c for c in coverage.candidates if c.pair_id == body.pair_id), None)
        if candidate is None:
            _error(404, 'PAIR_NOT_FOUND', 'Pair is not in this snapshot')
        harness = s.model()
        result = harness.evaluate(snapshot, candidate, body.request_id)
        with s.provider._lock:
            s.provider._check(snapshot)
            return {'session_id': snapshot.session_id, 'session_version': snapshot.session_version,
                    'snapshot_id': snapshot.snapshot_id, 'anchor_utc': snapshot.anchor_utc, 'risk': result}
    except APIProblem as exc:
        _error(exc.status_code, exc.error_code, exc.message)
    except RuntimeUnavailable as exc:
        code = str(exc)
        status = 409 if any(x in code for x in ('STALE', 'CONFLICT', 'INPUT_UNAVAILABLE', 'UNTRUSTED')) else 503
        _error(status, code, 'Runtime evaluation is unavailable')
    except ValueError as exc:
        _error(409, 'SNAPSHOT_STALE', str(exc))


@router.get('/sessions/{session_id}/alerts')
def alerts(session_id: str, request: Request, snapshot_id: str):
    s = _state(request)
    try:
        snapshot, _ = s.coverage(session_id, snapshot_id)
        harness = s.model()
        items = harness.alerts(snapshot)
        return {'session_id': snapshot.session_id, 'session_version': snapshot.session_version,
                'snapshot_id': snapshot.snapshot_id, 'anchor_utc': snapshot.anchor_utc,
                'items': items, 'total': len(items)}
    except APIProblem as exc:
        _error(exc.status_code, exc.error_code, exc.message)
    except RuntimeUnavailable as exc:
        _error(503, str(exc), 'Runtime is unavailable')
    except ValueError as exc:
        _error(409, 'SNAPSHOT_STALE', str(exc))
