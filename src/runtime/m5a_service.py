"""Synthetic-fixture M5a service. Internal types are not Contract V1 wire types."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from pathlib import Path
import threading

import numpy as np
import torch

from src.models.kinematics import cv_displacement, project_forecast
from src.models.pipeline import forecast
from src.runtime.config import RuntimeConfig, LOCK_ID, AUTHORITY
from src.runtime.trusted_fixture import FixtureProvider, Features, FEATURES, SOURCE
from src.training.engine import severe_qc
from src.runtime.verified_context import BatchToken, VerifiedContextError, VerifiedRuntimeContext


class RuntimeUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class VesselForecast:
    vessel_id: str
    active_model: str | None
    fallback_reason: str | None
    qc_status: str
    en: np.ndarray | None
    lat_lon: np.ndarray | None


@dataclass(frozen=True)
class RuntimeForecast:
    session_id: str
    session_version: int
    snapshot_id: str
    anchor_utc: str
    pair_id: str
    encounter_id: str
    lock_id: str
    timestamps: tuple
    vessels: tuple
    status: str
    risk_eligible: bool
    # risk_eligible=False always: risk is not implemented at this boundary.


_BOUND_SOURCES = ('src/inference/m5a_wrapper.py', 'src/models/m5a.py',
                  'src/models/scalers.py', 'src/models/pipeline.py',
                  'src/models/kinematics.py', 'src/training/engine.py',
                  'src/training/loss.py', 'src/models/__init__.py',
                  'src/release/offline_lock.py', 'configs/model_config.yaml',
                  'configs/projection_config.yaml')


def _readonly(array):
    array = np.ascontiguousarray(array)
    return np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape)


class M5aRuntime:
    """One loaded instance per service; an exact FixtureProvider owns the input."""
    def __init__(self, config: RuntimeConfig, provider: FixtureProvider):
        if type(config) is not RuntimeConfig or type(provider) is not FixtureProvider:
            raise RuntimeUnavailable('CONFIG_OR_PROVIDER_INVALID')
        if (config.device not in ('cpu', 'cuda') or config.authority != AUTHORITY or
            config.lock_id != LOCK_ID or config.official_alerts or config.scope != 'ACADEMIC_PROTOTYPE' or
            type(config.max_concurrency) is not int or config.max_concurrency < 1 or
            type(config.max_vessels) is not int or config.max_vessels < 2 or
            provider._max_vessels > config.max_vessels):
            raise RuntimeUnavailable('CONFIG_INVALID')
        self._config = config
        self._provider = provider
        self._semaphore = threading.BoundedSemaphore(config.max_concurrency)
        self._state_lock = threading.RLock()
        self._closed = False
        self._context = None
        self._active_batch_token = None
        self.load_count = 0
        try:
            self._context = VerifiedRuntimeContext.load(config)
            self._backend = self._context.backend
            self.load_count = 1
        except Exception as exc:
            raise RuntimeUnavailable('ARTIFACT_OR_DEVICE_UNAVAILABLE') from exc

    def _verify_integrity(self):
        if self._context is None:
            raise VerifiedContextError('runtime context is unavailable')
        self._context.verify_boundary()

    def begin_batch(self, snapshot, candidates, deadline_monotonic, cancellation):
        """Create a single-use token after a full start-boundary verification."""
        with self._state_lock:
            if self._closed or self._context is None or self._context.invalidated:
                raise RuntimeUnavailable('RUNTIME_CONTEXT_UNAVAILABLE')
            if self._active_batch_token is not None:
                raise RuntimeUnavailable('BATCH_ALREADY_ACTIVE')
            try:
                self._provider._check(snapshot)
                if not candidates or len({candidate.pair_id for candidate in candidates}) != len(candidates):
                    raise ValueError('candidate set is empty or duplicated')
                self._context.verify_boundary()
                pairs = tuple((candidate.pair_id, tuple(candidate.vessels)) for candidate in candidates)
                token = BatchToken(self._context.identity, self._context.config_identity,
                    self._context.model_generation, LOCK_ID, self._context.identity_obj['pin_sha256'],
                    snapshot.session_id, snapshot.session_version, snapshot.snapshot_id,
                    snapshot.anchor_utc, snapshot.source_identity, snapshot.fixture_sha256,
                    pairs, float(deadline_monotonic), cancellation, __import__('secrets').token_hex(16))
                token.assert_live()
                self._active_batch_token = token
                return token
            except Exception as exc:
                if isinstance(exc, RuntimeUnavailable):
                    raise
                raise RuntimeUnavailable('BATCH_BOUNDARY_VERIFICATION_FAILED') from exc

    def _assert_batch_token(self, token, snapshot=None, candidate=None):
        with self._state_lock:
            if (self._closed or self._context is None or type(token) is not BatchToken or
                    self._active_batch_token is not token or self._context.invalidated):
                raise RuntimeUnavailable('BATCH_TOKEN_INVALID')
            try:
                if snapshot is not None and candidate is not None:
                    token.assert_binding(self._context, snapshot, candidate)
                else:
                    token.assert_live()
                    if (token.context_identity != self._context.identity or
                            token.config_identity != self._context.config_identity or
                            token.model_generation != self._context.model_generation or
                            token.lock_id != LOCK_ID or token.pin_sha256 != self._context.identity_obj['pin_sha256']):
                        raise VerifiedContextError('batch context binding mismatch')
            except VerifiedContextError as exc:
                raise RuntimeUnavailable('BATCH_TOKEN_INVALID') from exc

    def resolve_batch_threshold(self, token, active_models):
        self._assert_batch_token(token)
        result = self._context.resolve_threshold(active_models)
        if not result.available:
            raise RuntimeUnavailable('AUTHORITY_UNAVAILABLE')
        return result

    def verify_batch_end(self, token):
        self._assert_batch_token(token)
        try:
            self._context.verify_boundary()
            self._assert_batch_token(token)
        except Exception as exc:
            raise RuntimeUnavailable('BATCH_FINAL_VERIFICATION_FAILED') from exc

    def complete_batch(self, token):
        with self._state_lock:
            self._assert_batch_token(token)
            self._active_batch_token = None

    def discard_batch(self, token):
        with self._state_lock:
            if self._active_batch_token is token:
                self._active_batch_token = None

    def close(self):
        with self._state_lock:
            self._closed = True
            self._active_batch_token = None

    def _run_vessel(self, x, anchor):
        """Return projected forecast or a CV fallback with per-vessel provenance."""
        velocity = x[:, -1, 2:].to(dtype=anchor.dtype)
        try:
            result = forecast(self._backend.model, self._backend.x_scaler,
                              self._backend.residual_scaler, x, anchor)
            if not torch.isfinite(result).all() or severe_qc(result, anchor).any():
                raise RuntimeError('M5A_SEVERE_QC')
            return result, 'M5a', None
        except (RuntimeError, ValueError) as exc:
            reason = 'M5A_TECHNICAL_OR_SEVERE_QC: ' + str(exc)
            try:
                result = project_forecast(anchor[:, None, :] + cv_displacement(velocity), anchor, velocity)
                if not torch.isfinite(result).all() or severe_qc(result, anchor).any():
                    raise ValueError('CV_SEVERE_QC')
                return result, 'CV', reason
            except (RuntimeError, ValueError):
                return None, None, reason + '; CV_UNAVAILABLE'

    def predict(self, snapshot, candidate, issued_features=None, *, batch_token=None):
        if not self._semaphore.acquire(blocking=False):
            raise RuntimeUnavailable('CONCURRENCY_LIMIT')
        try:
            with self._state_lock:
                if self._closed:
                    raise RuntimeUnavailable('SERVICE_CLOSED')
            if batch_token is None:
                try:
                    self._verify_integrity()
                except Exception as exc:
                    raise RuntimeUnavailable('ARTIFACT_INTEGRITY_FAILURE') from exc
            else:
                self._assert_batch_token(batch_token, snapshot, candidate)
            try:
                encounter, reason = self._provider.encounter(snapshot, candidate)
                if reason:
                    raise RuntimeUnavailable(reason)
                if issued_features is None:
                    feat = self._provider.features(snapshot, encounter)
                elif (type(issued_features) is not Features or
                      not self._provider.is_issued_features(snapshot, encounter, issued_features)):
                    raise ValueError('FEATURE_BINDING_INVALID')
                else:
                    feat = issued_features
                if (snapshot.source_identity != SOURCE or feat.frame != 'common_EN_origin_A_t-9' or
                    feat.feature_order != FEATURES or feat.history.shape != (2, 10, 4) or
                    feat.history.dtype != np.float32 or feat.anchors_en.shape != (2, 2) or
                    feat.anchors_en.dtype != np.float64 or not np.isfinite(feat.history).all() or
                    not np.isfinite(feat.anchors_en).all()):
                    raise ValueError('FEATURE_CONTRACT_INVALID')
            except (ValueError, TypeError, AttributeError) as exc:
                raise RuntimeUnavailable('INPUT_UNAVAILABLE') from exc
            x = torch.from_numpy(feat.history.copy()).to(self._backend.device)
            anchors = torch.from_numpy(feat.anchors_en.copy()).to(self._backend.device)
            lat0, lon0 = feat.origin_lat_lon
            cos0 = math.cos(math.radians(lat0))
            vessels = []
            with torch.inference_mode():
                for i, vessel_id in enumerate(candidate.vessels):
                    result, active, fallback = self._run_vessel(x[i:i+1], anchors[i:i+1])
                    en = None if result is None else _readonly(result[0].detach().cpu().numpy())
                    geo = None
                    if en is not None and abs(cos0) > 1e-12:
                        values = np.stack((en[:, 1] / 60 + lat0, en[:, 0] / (60 * cos0) + lon0), axis=-1)
                        if np.isfinite(values).all() and (np.abs(values[:, 0]) <= 90).all() and (np.abs(values[:, 1]) <= 180).all():
                            geo = _readonly(values)
                    vessels.append(VesselForecast(vessel_id, active, fallback, 'PASS' if en is not None else 'UNAVAILABLE', en, geo))
            t0 = datetime.fromisoformat(snapshot.anchor_utc.replace('Z', '+00:00'))
            times = tuple((t0 + timedelta(minutes=i)).isoformat().replace('+00:00', 'Z') for i in range(1, 16))
            if batch_token is None:
                try:
                    self._verify_integrity()
                except Exception as exc:
                    raise RuntimeUnavailable('ARTIFACT_INTEGRITY_FAILURE') from exc
            else:
                self._assert_batch_token(batch_token, snapshot, candidate)
            # The provider lock makes the recheck and construction one publish operation.
            with self._provider._lock, self._state_lock:
                if self._closed:
                    raise RuntimeUnavailable('SERVICE_CLOSED')
                try:
                    self._provider.encounter(snapshot, candidate)
                except ValueError as exc:
                    raise RuntimeUnavailable('STALE_RESULT_DISCARDED') from exc
                return RuntimeForecast(snapshot.session_id, snapshot.session_version, snapshot.snapshot_id,
                    snapshot.anchor_utc, candidate.pair_id, encounter.encounter_id, LOCK_ID, times, tuple(vessels),
                    'AVAILABLE' if all(v.en is not None for v in vessels) else 'UNAVAILABLE', False)
        finally:
            self._semaphore.release()
