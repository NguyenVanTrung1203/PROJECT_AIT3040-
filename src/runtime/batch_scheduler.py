"""Single-process, one-worker scheduler for synthetic minute-grid evaluation."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
import threading
import time

from src.data.replay_time import parse_utc_ns, utc_iso_ns
from src.runtime.m5a_service import RuntimeUnavailable
from src.runtime.trusted_fixture import SOURCE

MINUTE_NS = 60 * 1_000_000_000


@dataclass
class EvaluationJob:
    snapshot: object
    coverage: object
    deadline: float
    cancellation: threading.Event
    enqueued_at: float
    session_generation: int

    @property
    def anchor(self):
        return self.snapshot.anchor_utc

    @property
    def key(self):
        return self.snapshot.session_id, self.anchor


class AutomaticEvaluationScheduler:
    """Backend-owned scheduler; clients only read its published state."""

    def __init__(self, runtime_state, *, poll_seconds=0.1):
        self._state = runtime_state
        self._poll_seconds = poll_seconds
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='s5-evaluation')
        self._active: EvaluationJob | None = None
        self._pending: EvaluationJob | None = None
        self._worker_busy = False
        self._binding = None
        self._last_anchor: dict[str, int] = {}
        self._seen: set[tuple[str, str]] = set()
        self._recent_skips = []
        self._latencies = []
        self._monitoring_status = 'IDLE'
        self._latest = None
        self._last_outcome = None
        self._error = None
        self._missed_deadlines = 0
        self._failed_anchors = []

    def start(self):
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._poll, name='s5-scheduler', daemon=True)
            self._thread.start()

    def close(self):
        self._stop.set()
        with self._lock:
            if self._active is not None:
                self._active.cancellation.set()
            pending = self._pending
            self._pending = None
            thread = self._thread
        if pending is not None:
            self._state.provider.release_evaluation_snapshot(pending.snapshot)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=10)
        self._executor.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def _floor_anchor(simulation_time: str) -> tuple[int, str]:
        value = parse_utc_ns(simulation_time, field='simulation_time')
        floor = value - value % MINUTE_NS
        return floor, utc_iso_ns(floor)

    def _poll(self):
        while not self._stop.is_set():
            try:
                view = self._state.replay.active_s5_session()
                self._observe(view)
            except Exception as exc:
                with self._lock:
                    self._error = 'SCHEDULER_CLOCK_UNAVAILABLE: ' + type(exc).__name__
                    if self._monitoring_status == 'PLAYING':
                        self._invalidate_jobs('CLOCK_UNAVAILABLE')
                        self._monitoring_status = 'UNAVAILABLE'
            self._stop.wait(self._poll_seconds)

    def _observe(self, view):
        if view is None:
            with self._lock:
                self._invalidate_jobs('SESSION_CLOSED')
                self._binding = None
                self._monitoring_status = 'IDLE'
                self._error = None
            return
        if view.source_id != SOURCE:
            with self._lock:
                self._invalidate_jobs('SOURCE_CHANGED')
                self._binding = (view.session_id, view.version, view.source_id, view.status)
                self._monitoring_status = 'UNAVAILABLE'
                self._error = 'S5_SOURCE_CHANGED'
            return
        if view.status != 'PLAYING':
            with self._lock:
                self._invalidate_jobs('REPLAY_NOT_PLAYING')
                self._binding = (view.session_id, view.version, view.source_id, view.status)
                self._monitoring_status = 'PAUSED' if view.status == 'PAUSED' else view.status
                self._error = None
            return

        binding = (view.session_id, view.version, view.source_id, view.status)
        with self._lock:
            if binding != self._binding:
                self._invalidate_jobs('SESSION_GENERATION_CHANGED')
                self._binding = binding
            self._monitoring_status = 'PLAYING'
            self._error = None
        floor_ns, floor_text = self._floor_anchor(view.simulation_time)
        with self._lock:
            prior = self._last_anchor.get(view.session_id)
            next_ns = floor_ns if prior is None else prior + MINUTE_NS
        while next_ns <= floor_ns and not self._stop.is_set():
            anchor = utc_iso_ns(next_ns)
            key = (view.session_id, anchor)
            with self._lock:
                self._last_anchor[view.session_id] = next_ns
                if key in self._seen:
                    next_ns += MINUTE_NS
                    continue
                self._seen.add(key)
            self._create_and_enqueue(view, anchor)
            next_ns += MINUTE_NS

    def _create_and_enqueue(self, view, anchor):
        try:
            deadline = self._state.provider._api.evaluation_deadline(view.session_id, anchor, 1.0)
            snapshot, coverage = self._state.provider.evaluation_snapshot(
                view.session_id, anchor, view.version)
            job = EvaluationJob(snapshot, coverage, deadline, threading.Event(),
                                time.monotonic(), view.version)
        except Exception as exc:
            self._record_skip(view.session_id, anchor, 'SNAPSHOT_UNAVAILABLE:' + type(exc).__name__)
            return
        if time.monotonic() >= job.deadline:
            self._record_skip(view.session_id, anchor, 'DEADLINE_EXPIRED_BEFORE_QUEUE')
            with self._lock:
                self._missed_deadlines += 1
            self._state.provider.release_evaluation_snapshot(snapshot)
            return
        with self._lock:
            if self._binding != (view.session_id, view.version, view.source_id, 'PLAYING'):
                job.cancellation.set()
                self._state.provider.release_evaluation_snapshot(snapshot)
                self._record_skip(view.session_id, anchor, 'SESSION_GENERATION_CHANGED')
                return
            if not self._worker_busy:
                self._active = job
                self._worker_busy = True
                self._executor.submit(self._run_job, job)
                return
            previous = self._pending
            self._pending = job
            if previous is not None:
                previous.cancellation.set()
                self._record_skip(previous.snapshot.session_id, previous.anchor, 'REPLACED_BY_LATEST_PENDING')
                self._state.provider.release_evaluation_snapshot(previous.snapshot)

    def _run_job(self, job):
        started = time.perf_counter()
        outcome = 'FAILED'
        detail = None
        model = None
        token = None
        stage = None
        harness = None
        start_boundary_seconds = None
        end_boundary_seconds = None
        threshold_checks_before = None
        try:
            if job.cancellation.is_set():
                raise RuntimeUnavailable('BATCH_CANCELLED')
            if time.monotonic() >= job.deadline:
                raise RuntimeUnavailable('BATCH_DEADLINE_EXPIRED')
            harness = self._state.model()
            model = self._state._model
            # A manual PAUSED evaluation may have cached this same encounter
            # under an earlier generation/snapshot. Recompute it under the
            # current lease; never rebind or reuse the prior response.
            harness.invalidate_stale_anchor_cache(job.snapshot)
            threshold_checks_before = model._context.threshold_semantic_check_count
            boundary_started = time.perf_counter()
            token = model.begin_batch(job.snapshot, job.coverage.candidates,
                                      job.deadline, job.cancellation)
            start_boundary_seconds = time.perf_counter() - boundary_started
            try:
                stage = harness.begin_batch_stage()
                result_rows = []
                for index, candidate in enumerate(job.coverage.candidates):
                    if job.cancellation.is_set():
                        raise RuntimeUnavailable('BATCH_CANCELLED')
                    if time.monotonic() >= job.deadline:
                        raise RuntimeUnavailable('BATCH_DEADLINE_EXPIRED')
                    request_id = 'auto:' + hashlib.sha256(
                        f'{job.snapshot.session_id}:{job.anchor}:{candidate.pair_id}'.encode('utf-8')
                    ).hexdigest()
                    risk = stage.evaluate(job.snapshot, candidate, request_id, token)
                    result_rows.append({'pair_id': candidate.pair_id,
                                        'vessel_ids': list(candidate.vessels),
                                        'risk': risk})
                token.assert_live()
                boundary_started = time.perf_counter()
                model.verify_batch_end(token)
                end_boundary_seconds = time.perf_counter() - boundary_started
                if job.cancellation.is_set() or time.monotonic() >= job.deadline:
                    raise RuntimeUnavailable('BATCH_CANCELLED_OR_EXPIRED_BEFORE_PUBLICATION')
                published = harness.publish_batch_stage(stage, job.snapshot, token)
                stage = None
                elapsed = time.perf_counter() - started
                outcome = 'COMPLETED'
                batch = {'session_id': job.snapshot.session_id,
                         'session_generation': job.session_generation,
                         'snapshot_id': job.snapshot.snapshot_id,
                         'anchor_utc': job.anchor,
                         'source_identity': job.snapshot.source_identity,
                         'fixture_sha256': job.snapshot.fixture_sha256,
                         'expected': job.coverage.expected,
                         'evaluated': len(published),
                         'eligible': job.coverage.eligible,
                         'unavailable': job.coverage.unavailable,
                         'latency_seconds': elapsed,
                         'deadline_budget_seconds': 60.0,
                         'start_boundary_seconds': start_boundary_seconds,
                         'end_boundary_seconds': end_boundary_seconds,
                         'full_verification_calls': 2,
                         'threshold_authority_semantic_checks': model._context.threshold_semantic_check_count - threshold_checks_before,
                         'model_load_count': model.load_count,
                         'completed_at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                         'pairs': result_rows,
                         'alerts': harness.alerts_for_session(job.snapshot.session_id)}
                with self._lock:
                    self._latest = batch
                    self._latencies.append(elapsed)
                    self._latencies = self._latencies[-100:]
                    self._last_outcome = 'COMPLETED'
                    self._error = None
            finally:
                if stage is not None and harness is not None:
                    harness.discard_batch_stage(stage)
                if token is not None and model is not None:
                    model.discard_batch(token)
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            detail = message[:180]
            if 'DEADLINE' in message or time.monotonic() >= job.deadline:
                outcome = 'MISSED_DEADLINE'
                with self._lock:
                    self._missed_deadlines += 1
            elif 'CANCEL' in message or 'STALE' in message or 'GENERATION' in message:
                outcome = 'CANCELLED'
            else:
                outcome = 'FAILED'
            with self._lock:
                self._last_outcome = outcome
                self._error = detail
                if outcome == 'FAILED':
                    self._failed_anchors.append({'session_id': job.snapshot.session_id,
                                                 'anchor_utc': job.anchor, 'reason': detail})
                    self._failed_anchors = self._failed_anchors[-50:]
        finally:
            self._state.provider.release_evaluation_snapshot(job.snapshot)
            elapsed = time.perf_counter() - started
            with self._lock:
                self._last_outcome = outcome
                self._active = None
                pending = self._pending
                self._pending = None
                if pending is None:
                    self._worker_busy = False
                elif (pending.cancellation.is_set() or time.monotonic() >= pending.deadline or
                      pending.snapshot.session_id != job.snapshot.session_id or
                      pending.session_generation != job.session_generation):
                    pending.cancellation.set()
                    self._record_skip(pending.snapshot.session_id, pending.anchor,
                                      'PENDING_JOB_STALE_OR_EXPIRED')
                    self._state.provider.release_evaluation_snapshot(pending.snapshot)
                    self._worker_busy = False
                    pending = None
                else:
                    self._active = pending
            if pending is not None:
                self._executor.submit(self._run_job, pending)

    def _invalidate_jobs(self, reason):
        active = self._active
        if active is not None:
            active.cancellation.set()
        pending = self._pending
        self._pending = None
        if pending is not None:
            pending.cancellation.set()
            self._record_skip(pending.snapshot.session_id, pending.anchor, reason)
            self._state.provider.release_evaluation_snapshot(pending.snapshot)

    def _record_skip(self, session_id, anchor, reason):
        with self._lock:
            self._recent_skips.append({'session_id': session_id, 'anchor_utc': anchor, 'reason': reason})
            self._recent_skips = self._recent_skips[-50:]

    def status(self, session_id: str | None = None) -> dict:
        with self._lock:
            latest = self._latest
            if latest is not None and session_id is not None and latest['session_id'] != session_id:
                latest = None
            samples = sorted(self._latencies)
            def percentile(q):
                if not samples:
                    return None
                index = max(0, min(len(samples) - 1, math.ceil(len(samples) * q) - 1))
                return samples[index]
            return {'monitoring_status': self._monitoring_status,
                    'session_id': None if self._binding is None else self._binding[0],
                    'session_generation': None if self._binding is None else self._binding[1],
                    'running': self._active is not None,
                    'active_anchor': None if self._active is None else self._active.anchor,
                    'pending_anchor': None if self._pending is None else self._pending.anchor,
                    'latest_completed_anchor': None if latest is None else latest['anchor_utc'],
                    'latest_batch': latest,
                    'last_outcome': self._last_outcome,
                    'last_error': self._error,
                    'skipped_anchors': list(self._recent_skips),
                    'failed_anchors': list(self._failed_anchors),
                    'missed_deadlines': self._missed_deadlines,
                    'latency_sample_count': len(samples),
                    'latency_p50_seconds': percentile(0.50),
                    'latency_p95_seconds': percentile(0.95)}
