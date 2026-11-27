"""S5-only byte-bound loading and batch-boundary Model Lock verification."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import threading
from types import MappingProxyType
from typing import Mapping
import time

import numpy as np
import torch
import yaml

from src.inference.m5a_wrapper import CHECKPOINT_SHA, MANIFEST_SHA as ARTIFACT_MANIFEST_SHA, RUN
from src.models.m5a import ResidualGRU
from src.models.scalers import TrainOnlyScaler
from src.release.offline_lock import DETACHED, MANIFEST, PAYLOAD, LockError, validate_manifest_values
from src.risk.adapter import REFERENCE_HASH, verify_reference
from src.runtime.config import AUTHORITY, LOCK_ID, MANIFEST_SHA, PAYLOAD_SHA, THRESHOLDS, RuntimeConfig

PROJECTION_CONFIG_SHA = 'a3cb3a5a767d15dc1adc4669f33b0717b638bd8e11a41aa7f415d223024e35bf'
BOUND_SOURCES = ('src/inference/m5a_wrapper.py', 'src/models/m5a.py',
                 'src/models/scalers.py', 'src/models/pipeline.py',
                 'src/models/kinematics.py', 'src/training/engine.py',
                 'src/training/loss.py', 'src/models/__init__.py',
                 'src/release/offline_lock.py', 'configs/model_config.yaml',
                 'configs/projection_config.yaml')


class VerifiedContextError(RuntimeError):
    """A package, authority, or byte-bound loading check failed."""


@dataclass(frozen=True)
class BatchToken:
    context_identity: str
    config_identity: str
    model_generation: str
    lock_id: str
    pin_sha256: str
    session_id: str
    session_generation: int
    snapshot_id: str
    anchor_utc: str
    source_identity: str
    fixture_sha256: str
    candidate_set: tuple[tuple[str, tuple[str, str]], ...]
    deadline_monotonic: float
    cancellation: threading.Event
    nonce: str

    def assert_live(self):
        if self.cancellation.is_set():
            raise VerifiedContextError('batch cancelled')
        if time.monotonic() >= self.deadline_monotonic:
            raise VerifiedContextError('batch deadline expired')

    def assert_binding(self, context: 'VerifiedRuntimeContext', snapshot, candidate):
        self.assert_live()
        if (context.identity != self.context_identity or context.config_identity != self.config_identity or
                context.model_generation != self.model_generation or self.lock_id != LOCK_ID or
                self.pin_sha256 != context.identity_obj['pin_sha256'] or
                snapshot.session_id != self.session_id or snapshot.session_version != self.session_generation or
                snapshot.snapshot_id != self.snapshot_id or snapshot.anchor_utc != self.anchor_utc or
                snapshot.source_identity != self.source_identity or snapshot.fixture_sha256 != self.fixture_sha256 or
                (candidate.pair_id, tuple(candidate.vessels)) not in self.candidate_set):
            raise VerifiedContextError('batch token binding mismatch')


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_package_file(root: Path, relative: str) -> bytes:
    if (not isinstance(relative, str) or not relative or '\\' in relative):
        raise VerifiedContextError('invalid package relative path')
    rel = PurePosixPath(relative)
    if rel.is_absolute() or any(part in ('', '.', '..') for part in rel.parts):
        raise VerifiedContextError('package path traversal')
    path = root.joinpath(*rel.parts)
    for parent in (path, *path.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise VerifiedContextError('package symlink is forbidden')
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise VerifiedContextError('package file is missing or escaping')
    return path.read_bytes()


def _load_package(config: RuntimeConfig) -> tuple[dict, dict[str, bytes], str, dict]:
    if type(config) is not RuntimeConfig:
        raise VerifiedContextError('runtime configuration type mismatch')
    root = config.package_path.resolve(strict=True)
    pin_path = config.pin_path.resolve(strict=True)
    if not root.is_dir() or pin_path.is_relative_to(root) or pin_path.is_symlink() or not pin_path.is_file():
        raise VerifiedContextError('external package or pin path is invalid')

    pin_bytes = pin_path.read_bytes()
    try:
        pin = json.loads(pin_bytes.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerifiedContextError('external pin is invalid') from exc
    if (pin.get('manifest_sha256'), pin.get('payload_sha256'), pin.get('lock_id')) != (MANIFEST_SHA, PAYLOAD_SHA, LOCK_ID):
        raise VerifiedContextError('external pin identity mismatch')

    manifest_bytes = _read_package_file(root, MANIFEST)
    manifest_sha = _sha256(manifest_bytes)
    if manifest_sha != MANIFEST_SHA:
        raise VerifiedContextError('manifest pin mismatch')
    detached_bytes = _read_package_file(root, DETACHED)
    if detached_bytes.decode('ascii').strip() != manifest_sha:
        raise VerifiedContextError('detached checksum mismatch')
    try:
        manifest = validate_manifest_values(json.loads(manifest_bytes.decode('utf-8')))
    except (UnicodeDecodeError, json.JSONDecodeError, LockError, TypeError) as exc:
        raise VerifiedContextError('Model Lock manifest semantics are invalid') from exc
    if (manifest.get('lock_id'), manifest.get('package_identity'), manifest.get('payload_sha256')) != (LOCK_ID, PAYLOAD_SHA, PAYLOAD_SHA):
        raise VerifiedContextError('Model Lock identity mismatch')

    payload_bytes = _read_package_file(root, PAYLOAD)
    if _sha256(payload_bytes) != PAYLOAD_SHA:
        raise VerifiedContextError('package payload identity mismatch')
    try:
        payload = json.loads(payload_bytes.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerifiedContextError('package payload index is invalid') from exc
    expected = payload.get('files') if isinstance(payload, dict) and payload.get('version') == 1 else None
    if not isinstance(expected, dict) or not expected:
        raise VerifiedContextError('package payload inventory is invalid')

    actual: set[str] = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise VerifiedContextError('package symlink is forbidden')
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative not in (PAYLOAD, MANIFEST, DETACHED):
                actual.add(relative)
    if actual != set(expected):
        raise VerifiedContextError('package inventory mismatch')

    contents: dict[str, bytes] = {}
    for relative, expected_sha in expected.items():
        data = _read_package_file(root, relative)
        if _sha256(data) != expected_sha:
            raise VerifiedContextError('package payload hash mismatch: ' + relative)
        contents[relative] = data

    source_root = Path(__file__).resolve().parents[2]
    source_hashes = {}
    for name in BOUND_SOURCES:
        packaged = contents.get('snapshot/' + name)
        if packaged is None:
            raise VerifiedContextError('bound source is absent from Model Lock: ' + name)
        worktree = (source_root / name).read_bytes()
        if worktree.replace(b'\r\n', b'\n') != packaged.replace(b'\r\n', b'\n'):
            raise VerifiedContextError('runtime source differs from pinned snapshot: ' + name)
        source_hashes[name] = _sha256(packaged)

    run_dir = f'snapshot/artifacts/checkpoints/{RUN}'
    checksum_path = f'{run_dir}/checksums.sha256'
    checksum_bytes = contents.get(checksum_path)
    if checksum_bytes is None or _sha256(checksum_bytes) != ARTIFACT_MANIFEST_SHA:
        raise VerifiedContextError('T10 artifact checksum manifest mismatch')
    try:
        entries: dict[str, str] = {}
        for line in checksum_bytes.decode('utf-8').splitlines():
            digest, name = line.split('  ', 1)
            if PurePosixPath(name).name != name or name in entries:
                raise ValueError('invalid artifact checksum entry')
            entries[name] = digest
    except (UnicodeDecodeError, ValueError) as exc:
        raise VerifiedContextError('T10 artifact checksum manifest is invalid') from exc
    if len(entries) != 12 or entries.get('best_model.pt') != CHECKPOINT_SHA:
        raise VerifiedContextError('T10 artifact identity mismatch')
    for name, expected_sha in entries.items():
        data = contents.get(f'{run_dir}/{name}')
        if data is None or _sha256(data) != expected_sha:
            raise VerifiedContextError('T10 artifact hash mismatch: ' + name)

    verify_reference()
    identity_obj = {
        'manifest_sha256': manifest_sha,
        'payload_sha256': _sha256(payload_bytes),
        'pin_sha256': _sha256(pin_bytes),
        'lock_id': manifest.get('lock_id'),
        'package_identity': manifest.get('package_identity'),
        'source_hashes': source_hashes,
        'artifact_manifest_sha256': _sha256(checksum_bytes),
        'risk_reference_sha256': REFERENCE_HASH,
    }
    identity = _sha256(json.dumps(identity_obj, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    metadata = {'manifest': manifest, 'payload': payload, 'pin_sha256': _sha256(pin_bytes),
                'identity_obj': identity_obj, 'run_dir': run_dir, 'artifact_entries': entries}
    return metadata, contents, identity, identity_obj


def _load_scaler(data: bytes, expected_kind: str) -> TrainOnlyScaler:
    try:
        value = json.loads(data.decode('utf-8'))
        if value.get('version') != 1 or value.get('kind') != expected_kind:
            raise ValueError('scaler kind/version mismatch')
        scaler = TrainOnlyScaler(expected_kind)
        scaler.mean = np.asarray(value['mean'], dtype=np.float64)
        scaler.scale = np.asarray(value['scale'], dtype=np.float64)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise VerifiedContextError('scaler bytes are invalid') from exc
    if (scaler.mean.shape != (scaler.tail[-1],) or scaler.scale.shape != scaler.mean.shape or
            not np.isfinite(scaler.mean).all() or not np.isfinite(scaler.scale).all() or (scaler.scale <= 0).any()):
        raise VerifiedContextError('scaler parameters are invalid')
    return scaler


@dataclass(frozen=True)
class VerifiedInference:
    model: torch.nn.Module
    x_scaler: TrainOnlyScaler
    residual_scaler: TrainOnlyScaler
    device: torch.device


def _load_inference(config: RuntimeConfig, metadata: dict, contents: Mapping[str, bytes]) -> VerifiedInference:
    run_dir = metadata['run_dir']
    entries = metadata['artifact_entries']
    try:
        manifest = json.loads(contents[f'{run_dir}/training_manifest.json'].decode('utf-8'))
        run_config = yaml.safe_load(contents[f'{run_dir}/run_config.yaml'])
        projection = contents['snapshot/configs/projection_config.yaml']
        model_config = contents['snapshot/configs/model_config.yaml']
        if _sha256(projection) != PROJECTION_CONFIG_SHA:
            raise ValueError('projection config differs from the approved source')
        if _sha256(model_config) != entries['run_config.yaml']:
            raise ValueError('repository model config differs from T10 run config')
        checkpoint_bytes = contents[f'{run_dir}/best_model.pt']
        checkpoint = torch.load(BytesIO(checkpoint_bytes), map_location='cpu', weights_only=True)
        if (manifest['run_id'] != RUN or manifest['best_epoch'] != 1 or manifest['seed'] != 20261110
                or manifest['checkpoint_sha256'] != entries['best_model.pt']
                or manifest['x_scaler_sha256'] != entries['x_scaler.json']
                or manifest['residual_scaler_sha256'] != entries['residual_scaler.json']
                or manifest['model_config_sha256'] != entries['run_config.yaml']
                or checkpoint['artifact_kind'] != 'TRAINING_CANDIDATE' or checkpoint['epoch'] != 1
                or checkpoint['seed'] != manifest['seed'] or checkpoint['config'] != run_config
                or checkpoint['scalers'] != {'input': 'x_scaler.json', 'residual': 'residual_scaler.json'}
                or checkpoint['dataset_manifest_sha256'] != manifest['dataset_manifest_sha256']):
            raise ValueError('run provenance/config mismatch')
        x_scaler = _load_scaler(contents[f'{run_dir}/x_scaler.json'], 'input')
        residual_scaler = _load_scaler(contents[f'{run_dir}/residual_scaler.json'], 'residual')
        if config.device not in ('cpu', 'cuda'):
            raise ValueError('an explicit cpu or cuda device is required')
        if config.device == 'cuda' and not torch.cuda.is_available():
            raise ValueError('CUDA is unavailable')
        device = torch.device(config.device)
        model = ResidualGRU()
        model.load_state_dict(checkpoint['model_state'], strict=True)
        if sum(parameter.numel() for parameter in model.parameters()) != 15390:
            raise ValueError('model parameter count mismatch')
        model.to(device).eval()
        return VerifiedInference(model, x_scaler, residual_scaler, device)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError,
            KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise VerifiedContextError('verified model bytes could not be loaded') from exc


def _config_identity(config: RuntimeConfig) -> str:
    values = {'package_path': str(config.package_path.resolve()), 'pin_path': str(config.pin_path.resolve()),
              'device': config.device, 'authority': config.authority,
              'max_vessels': config.max_vessels, 'max_concurrency': config.max_concurrency,
              'lock_id': config.lock_id, 'm5a_threshold': str(config.m5a_threshold),
              'cv_threshold': str(config.cv_threshold), 'scope': config.scope,
              'official_alerts': config.official_alerts}
    return _sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode('utf-8'))


class VerifiedRuntimeContext:
    """One model generation loaded from the exact bytes verified at startup."""

    def __init__(self, config: RuntimeConfig, identity: str, identity_obj: dict,
                 generation: str, backend: VerifiedInference):
        self.config = config
        self.identity = identity
        self.identity_obj = MappingProxyType(dict(identity_obj))
        self.config_identity = _config_identity(config)
        self.model_generation = generation
        self.backend = backend
        self._invalidated = False
        self._lock = threading.RLock()
        self._manifest = None
        self._boundary_verification_count = 0
        self._threshold_semantic_check_count = 0

    @classmethod
    def load(cls, config: RuntimeConfig):
        try:
            metadata, contents, identity, identity_obj = _load_package(config)
            backend = _load_inference(config, metadata, contents)
            generation = os.urandom(16).hex()
            context = cls(config, identity, identity_obj, generation, backend)
            context.bind_verified_manifest(metadata)
            if not context._resolve_threshold(metadata['manifest'], ('M5a', 'M5a')).available:
                raise VerifiedContextError('M5a threshold authority is unavailable')
            if not context._resolve_threshold(metadata['manifest'], ('CV', 'CV')).available:
                raise VerifiedContextError('CV threshold authority is unavailable')
            return context
        except Exception as exc:
            if isinstance(exc, VerifiedContextError):
                raise
            raise VerifiedContextError('verified runtime context initialization failed') from exc

    @property
    def invalidated(self) -> bool:
        with self._lock:
            return self._invalidated

    def invalidate(self):
        with self._lock:
            self._invalidated = True

    def verify_boundary(self) -> dict:
        """Verify package, source, risk reference and both threshold points once."""
        with self._lock:
            if self._invalidated:
                raise VerifiedContextError('runtime context is invalidated; restart from a valid package')
            self._boundary_verification_count += 1
            try:
                if _config_identity(self.config) != self.config_identity:
                    raise VerifiedContextError('runtime configuration identity changed')
                metadata, _, identity, _ = _load_package(self.config)
                if identity != self.identity:
                    raise VerifiedContextError('verified package identity changed')
                self._resolve_threshold(metadata['manifest'], ('M5a', 'M5a'))
                self._resolve_threshold(metadata['manifest'], ('CV', 'CV'))
                self._manifest = metadata['manifest']
                return metadata
            except Exception as exc:
                self._invalidated = True
                if isinstance(exc, VerifiedContextError):
                    raise
                raise VerifiedContextError('runtime package boundary verification failed') from exc

    def _resolve_threshold(self, manifest: dict, active_models: tuple[str, str], *, official_alert: bool = False):
        from src.runtime.config import ThresholdResult
        with self._lock:
            self._threshold_semantic_check_count += 1
        cfg = self.config
        if official_alert or cfg.official_alerts or cfg.scope != 'ACADEMIC_PROTOTYPE':
            return ThresholdResult(False, None, 'SCOPE_UNAUTHORIZED')
        if cfg.authority != AUTHORITY or cfg.lock_id != LOCK_ID:
            return ThresholdResult(False, None, 'AUTHORITY_UNAVAILABLE')
        if (not isinstance(active_models, tuple) or len(active_models) != 2 or
                not all(isinstance(model, str) for model in active_models) or
                active_models[0] != active_models[1] or active_models[0] not in THRESHOLDS):
            return ThresholdResult(False, None, 'MODEL_UNAVAILABLE')
        if cfg.m5a_threshold != THRESHOLDS['M5a'] or cfg.cv_threshold != THRESHOLDS['CV']:
            return ThresholdResult(False, None, 'THRESHOLD_INVALID')
        points = manifest.get('operating_points', {})
        model = active_models[0]
        try:
            threshold = Decimal(str(points.get(model, {}).get('threshold')))
        except Exception:
            return ThresholdResult(False, None, 'RELEASE_UNAVAILABLE')
        if (manifest.get('lock_id') != LOCK_ID or manifest.get('package_identity') != PAYLOAD_SHA or
                points.get('comparator') != '>=' or not threshold.is_finite() or threshold != THRESHOLDS[model]):
            return ThresholdResult(False, None, 'RELEASE_UNAVAILABLE')
        return ThresholdResult(True, THRESHOLDS[model], None, AUTHORITY, '>=')

    def resolve_threshold(self, active_models: tuple[str, str], *, official_alert: bool = False):
        with self._lock:
            if self._invalidated or self._manifest is None:
                from src.runtime.config import ThresholdResult
                return ThresholdResult(False, None, 'AUTHORITY_UNAVAILABLE')
            manifest = self._manifest
        if self.invalidated:
            from src.runtime.config import ThresholdResult
            return ThresholdResult(False, None, 'AUTHORITY_UNAVAILABLE')
        # Threshold semantics are re-evaluated against the boundary-verified manifest.
        return self._resolve_threshold(manifest, active_models, official_alert=official_alert)

    def bind_verified_manifest(self, metadata: dict):
        with self._lock:
            if self._invalidated or metadata.get('identity_obj') is None:
                raise VerifiedContextError('runtime context cannot bind an unverified manifest')
            self._manifest = metadata['manifest']

    @property
    def boundary_verification_count(self):
        with self._lock:
            return self._boundary_verification_count

    @property
    def threshold_semantic_check_count(self):
        with self._lock:
            return self._threshold_semantic_check_count
