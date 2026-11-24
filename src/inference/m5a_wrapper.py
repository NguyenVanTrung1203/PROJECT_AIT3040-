"""Candidate inference: trusted offline entrypoint; runtime integration is disabled."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import unicodedata

import torch
import yaml

from src.models.m5a import ResidualGRU
from src.models.scalers import TrainOnlyScaler
from src.models.pipeline import forecast
from src.models.kinematics import cv_displacement, project_forecast
from src.training.engine import severe_qc

RUN = 's3_t10_20261124_seed20261110_run01'
MANIFEST_SHA = '5f0af2eb5a4e418026b775fa412e2fc8bbc803c7438123038a1c519e5a082eb2'
CHECKPOINT_SHA = 'e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc'
FEATURES = ('own_relative_east_nm', 'own_relative_north_nm', 'east_velocity_kn', 'north_velocity_kn')


class InferenceError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_artifacts(path):
    """Verify pinned manifest and every listed file before deserializing anything."""
    path = Path(path)
    try:
        if digest(path / 'checksums.sha256') != MANIFEST_SHA:
            raise ValueError('checksum manifest mismatch')
        entries = {}
        for line in (path / 'checksums.sha256').read_text(encoding='utf-8').splitlines():
            sha, name = line.split('  ', 1)
            if Path(name).name != name or name in entries:
                raise ValueError('invalid checksum entry')
            entries[name] = sha
        if len(entries) != 12 or entries.get('best_model.pt') != CHECKPOINT_SHA:
            raise ValueError('artifact list mismatch')
        for name, sha in entries.items():
            if digest(path / name) != sha:
                raise ValueError('artifact checksum mismatch: ' + name)
        return entries
    except (OSError, ValueError) as exc:
        raise InferenceError('ARTIFACT_INTEGRITY_FAILURE', str(exc)) from exc


@dataclass(frozen=True)
class EncounterBatch:
    history: torch.Tensor  # [N,2,10,4], float32, offline A/B order
    anchors: torch.Tensor  # [N,2,2], float64 common EN
    vessel_ids: tuple      # N pairs, validated upstream stable IDs
    anchor_times: tuple    # N UTC datetimes
    history_times: tuple   # N tuples, 10 causal UTC datetimes
    source: tuple          # N source types
    provenance_verified: bool
    in_scope_verified: bool
    frame: str = 'common_EN_origin_A_t-9'
    feature_order: tuple = FEATURES


def validate(batch):
    if not isinstance(batch, EncounterBatch):
        raise InferenceError('INVALID_INPUT', 'expected EncounterBatch')
    x, a = batch.history, batch.anchors
    if not isinstance(x, torch.Tensor) or x.ndim != 4 or x.shape[1:] != (2, 10, 4) or x.shape[0] == 0:
        raise InferenceError('INSUFFICIENT_DATA', 'history must be [N,2,10,4]')
    n = x.shape[0]
    if not isinstance(a, torch.Tensor) or a.shape != (n, 2, 2) or x.dtype != torch.float32 or a.dtype != torch.float64:
        raise InferenceError('INVALID_INPUT', 'invalid anchor shape or dtype')
    if not torch.isfinite(x).all() or not torch.isfinite(a).all():
        raise InferenceError('INSUFFICIENT_DATA', 'nonfinite values')
    if (x[:, :, -1, :2].abs() > 1e-6).any():
        raise InferenceError('INVALID_INPUT', 'history must be own-anchor relative')
    if (a[:, 0, :] + x[:, 0, 0, :2].to(a.dtype)).abs().max() > 1e-6:
        raise InferenceError('INVALID_INPUT', 'common EN origin must be vessel A at t-9')
    if batch.frame != 'common_EN_origin_A_t-9' or tuple(batch.feature_order) != FEATURES:
        raise InferenceError('INVALID_INPUT', 'coordinate frame or feature ordering mismatch')
    if not all(len(v) == n for v in (batch.vessel_ids, batch.anchor_times, batch.history_times, batch.source)):
        raise InferenceError('INVALID_INPUT', 'batch metadata length mismatch')
    for ids, anchor, times, source in zip(batch.vessel_ids, batch.anchor_times, batch.history_times, batch.source):
        if len(ids) != 2 or any(not isinstance(v, str) or not v or unicodedata.normalize('NFC', v) != v for v in ids) or ids[0] == ids[1]:
            raise InferenceError('INVALID_INPUT', 'invalid vessel identities')
        if source not in ('REAL_AIS', 'SYNTHETIC_AIS', 'YANG_LEI'):
            raise InferenceError('INVALID_INPUT', 'invalid source')
        if not isinstance(anchor, datetime) or anchor.tzinfo is None or anchor.utcoffset() != timedelta(0) or anchor.microsecond:
            raise InferenceError('INVALID_INPUT', 'anchor must be UTC and exact seconds')
        if len(times) != 10 or any(not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() != timedelta(0) for t in times):
            raise InferenceError('INSUFFICIENT_DATA', 'ten UTC history timestamps required')
        if tuple(times) != tuple(anchor - timedelta(minutes=i) for i in range(9, -1, -1)):
            raise InferenceError('INVALID_INPUT', 'history timestamps are not causal minute grid')
    return n


class M5aInference:
    def __init__(self, artifacts, device='auto'):
        path = Path(artifacts)
        hashes = verify_artifacts(path)
        if device not in ('auto', 'cpu', 'cuda'):
            raise InferenceError('DEVICE_CONFIGURATION_ERROR', 'device must be auto, cpu or cuda')
        if device == 'cuda' and not torch.cuda.is_available():
            raise InferenceError('DEVICE_CONFIGURATION_ERROR', 'CUDA unavailable')
        if device == 'auto':
            try:
                if torch.cuda.is_available():
                    torch.empty(1, device='cuda')
                    device = 'cuda'
                else:
                    device = 'cpu'
            except (RuntimeError, AssertionError):
                device = 'cpu'
        self.device = torch.device(device)
        try:
            repo = Path(__file__).resolve().parents[2]
            if digest(repo / 'configs/projection_config.yaml') != 'a3cb3a5a767d15dc1adc4669f33b0717b638bd8e11a41aa7f415d223024e35bf':
                raise ValueError('projection config differs from T06/T10 baseline')
            if digest(repo / 'configs/model_config.yaml') != hashes['run_config.yaml']:
                raise ValueError('repository model config differs from run')
            manifest = json.loads((path / 'training_manifest.json').read_text(encoding='utf-8'))
            config = yaml.safe_load((path / 'run_config.yaml').read_text(encoding='utf-8'))
            checkpoint = torch.load(path / 'best_model.pt', map_location='cpu', weights_only=True)
            if (manifest['run_id'] != RUN or manifest['best_epoch'] != 1 or manifest['seed'] != 20261110
                    or manifest['checkpoint_sha256'] != hashes['best_model.pt']
                    or manifest['x_scaler_sha256'] != hashes['x_scaler.json']
                    or manifest['residual_scaler_sha256'] != hashes['residual_scaler.json']
                    or manifest['model_config_sha256'] != hashes['run_config.yaml']
                    or checkpoint['artifact_kind'] != 'TRAINING_CANDIDATE' or checkpoint['epoch'] != 1
                    or checkpoint['seed'] != manifest['seed'] or checkpoint['config'] != config
                    or checkpoint['scalers'] != {'input': 'x_scaler.json', 'residual': 'residual_scaler.json'}
                    or checkpoint['dataset_manifest_sha256'] != manifest['dataset_manifest_sha256']):
                raise ValueError('run provenance/config mismatch')
            self.x_scaler = TrainOnlyScaler.load(path / 'x_scaler.json')
            self.residual_scaler = TrainOnlyScaler.load(path / 'residual_scaler.json')
            if (self.x_scaler.kind, self.residual_scaler.kind) != ('input', 'residual'):
                raise ValueError('scaler kind mismatch')
            self.model = ResidualGRU()
            self.model.load_state_dict(checkpoint['model_state'], strict=True)
            if sum(p.numel() for p in self.model.parameters()) != 15390:
                raise ValueError('parameter count mismatch')
            self.model.to(self.device).eval()
        except (OSError, ValueError, KeyError, RuntimeError, TypeError) as exc:
            raise InferenceError('ARTIFACT_INTEGRITY_FAILURE', str(exc)) from exc

    def predict(self, batch, *, allow_fallback=True):
        """Runtime inputs are not supported until a T18 trusted adapter exists."""
        raise InferenceError('INVALID_INPUT', 'unverified runtime input; T18 adapter not implemented')

    def predict_validation(self, dataset_root, *, batch_size=128, allow_fallback=True):
        """Offline only: load, check and infer locked Validation internally."""
        from src.inference.offline_validation import load_validation, make_batch
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size <= 0:
            raise InferenceError('INVALID_INPUT', 'batch_size must be positive')
        s, h, checksum = load_validation(dataset_root)
        outputs = []
        for start in range(0, len(s.pairs), batch_size):
            stop = min(start + batch_size, len(s.pairs))
            batch = make_batch(s, h, start, stop)
            result = self._predict_tensor(batch, allow_fallback=allow_fallback)
            result['data_status'] = 'VALID'
            result['input_scope'] = 'LOCKED_OFFLINE_VALIDATION'
            result['encounter_ids'] = tuple(s.encounters.encounter_id.iloc[start:stop].astype(str))
            result['x_rows'] = s.pairs[start:stop].copy()
            outputs.append(result)
        return outputs, checksum

    def _predict_test_only(self, batch, *, allow_fallback=True):
        """TEST_ONLY synthetic tensor path: never evidence of valid provenance."""
        result = self._predict_tensor(batch, allow_fallback=allow_fallback)
        result['input_scope'] = 'TEST_ONLY_UNVERIFIED'
        result['data_status'] = 'TEST_ONLY_UNVERIFIED'
        return result

    def _predict_tensor(self, batch, *, allow_fallback):
        n = validate(batch)
        x = batch.history.reshape(-1, 10, 4).to(self.device)
        anchor = batch.anchors.reshape(-1, 2).to(self.device)
        reason = None
        with torch.inference_mode():
            try:
                result = forecast(self.model, self.x_scaler, self.residual_scaler, x, anchor)
                if not torch.isfinite(result).all() or severe_qc(result, anchor).any():
                    raise RuntimeError('nonfinite output or severe QC')
            except (RuntimeError, ValueError) as exc:
                if not allow_fallback:
                    raise InferenceError('MODEL_TECHNICAL_FAILURE', str(exc)) from exc
                reason = str(exc)
                try:
                    v = x[:, -1, 2:].to(anchor.dtype)
                    result = project_forecast(anchor[:, None, :] + cv_displacement(v), anchor, v)
                    if not torch.isfinite(result).all() or severe_qc(result, anchor).any():
                        raise ValueError('CV output failed QC')
                except (RuntimeError, ValueError) as fallback_exc:
                    raise InferenceError('FORECAST_UNAVAILABLE', str(fallback_exc)) from fallback_exc
        return {'forecast_common_en_nm': result.reshape(n, 2, 15, 2),
                'forecast_displacement_en_nm': result.reshape(n, 2, 15, 2) - batch.anchors.to(self.device)[:, :, None, :],
                'forecast_timestamps': tuple(tuple(t + timedelta(minutes=i) for i in range(1, 16)) for t in batch.anchor_times),
                'vessel_ids': batch.vessel_ids, 'data_status': 'TEST_ONLY_UNVERIFIED', 'qc_status': 'PASS',
                'active_model': 'CV' if reason else 'M5a', 'fallback_used': reason is not None,
                'fallback_reason': reason, 'projection_status': 'APPLIED', 'alert_triggered': None,
                'model_status': 'CANDIDATE', 'device': str(self.device)}
