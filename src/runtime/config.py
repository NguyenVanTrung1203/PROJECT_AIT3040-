"""Fail-closed configuration for the approved S5 academic prototype.

This module resolves operating points only. It does not score risk, decide an
alert, validate runtime inputs, or authorize maritime/production alerts.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping
import json

from src.release.offline_lock import verify_active

BASELINE = "8f252c522914aa30ba05bd28368ec60cab71c5a6"
LOCK_ID = "offline-t14-15980ed4f7255ddbdb943979"
MANIFEST_SHA = "257e77a3a5ae2b2175926145cc0d3c483ccacdaf80f3479d9c352d69f8f6dcdc"
PAYLOAD_SHA = "15980ed4f7255ddbdb943979df7dda320ac4ae448e24feb357fa51f3dd38dd79"
AUTHORITY = "S5-D10-TRUNG-ACADEMIC-PROTOTYPE"
THRESHOLDS = {"M5a": Decimal("0.420"), "CV": Decimal("0.435")}


class RuntimeConfigurationError(ValueError):
    """Configuration is invalid; runtime must remain unavailable."""


@dataclass(frozen=True)
class RuntimeConfig:
    package_path: Path
    pin_path: Path
    device: str
    authority: str
    max_vessels: int
    max_concurrency: int
    lock_id: str
    m5a_threshold: Decimal
    cv_threshold: Decimal
    scope: str = "ACADEMIC_PROTOTYPE"
    official_alerts: bool = False


@dataclass(frozen=True)
class ThresholdResult:
    available: bool
    threshold: Decimal | None
    reason: str | None
    authority: str | None = None
    comparator: str | None = None


def _decimal(value: str, name: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise RuntimeConfigurationError(f"invalid {name}") from exc
    if not result.is_finite():
        raise RuntimeConfigurationError(f"invalid {name}")
    return result


def load_config(env: Mapping[str, str]) -> RuntimeConfig:
    """Read explicit settings; absence is an error, never implicit authority."""
    required = ("AIT3040_MODEL_PACKAGE", "AIT3040_MODEL_MANIFEST_PIN",
                "AIT3040_RUNTIME_DEVICE", "AIT3040_RUNTIME_AUTHORITY",
                "AIT3040_DEMO_MAX_VESSELS", "AIT3040_MAX_CONCURRENCY")
    if any(not env.get(key, "").strip() for key in required):
        raise RuntimeConfigurationError("missing required runtime configuration")
    if env["AIT3040_RUNTIME_AUTHORITY"] != AUTHORITY:
        raise RuntimeConfigurationError("missing or invalid prototype authority")
    if env["AIT3040_RUNTIME_DEVICE"] not in ("cpu", "cuda"):
        raise RuntimeConfigurationError("explicit cpu or cuda device required")
    if env.get("AIT3040_OFFICIAL_ALERTS", "false") != "false":
        raise RuntimeConfigurationError("official alerts are not authorized")
    if env.get("AIT3040_RUNTIME_SCOPE", "ACADEMIC_PROTOTYPE") != "ACADEMIC_PROTOTYPE":
        raise RuntimeConfigurationError("invalid runtime scope")
    if env.get("AIT3040_MODEL_LOCK_ID", LOCK_ID) != LOCK_ID:
        raise RuntimeConfigurationError("invalid lock identity")
    try:
        vessel_text = env["AIT3040_DEMO_MAX_VESSELS"]
        concurrency_text = env["AIT3040_MAX_CONCURRENCY"]
        if not vessel_text.isascii() or not vessel_text.isdecimal() or not concurrency_text.isascii() or not concurrency_text.isdecimal():
            raise ValueError("expected positive integers")
        vessels, concurrency = int(vessel_text), int(concurrency_text)
    except (ValueError, TypeError) as exc:
        raise RuntimeConfigurationError("invalid resource bounds") from exc
    if vessels < 2 or concurrency < 1:
        raise RuntimeConfigurationError("resource bounds outside allowed limits")
    m5a = _decimal(env.get("AIT3040_M5A_THRESHOLD", "0.420"), "M5a threshold")
    cv = _decimal(env.get("AIT3040_CV_THRESHOLD", "0.435"), "CV threshold")
    if m5a != THRESHOLDS["M5a"] or cv != THRESHOLDS["CV"]:
        raise RuntimeConfigurationError("threshold does not match approved operating point")
    package = Path(env["AIT3040_MODEL_PACKAGE"]).expanduser().resolve()
    pin = Path(env["AIT3040_MODEL_MANIFEST_PIN"]).expanduser().resolve()
    if not package.is_dir() or not pin.is_file() or pin.is_relative_to(package):
        raise RuntimeConfigurationError("external package or pin path is missing or invalid")
    return RuntimeConfig(package, pin, env["AIT3040_RUNTIME_DEVICE"], AUTHORITY,
                         vessels, concurrency, LOCK_ID, m5a, cv)


def resolve_threshold(config: RuntimeConfig | None, active_models: tuple[str, str],
                      *, official_alert: bool = False) -> ThresholdResult:
    """Verify independent pin and immutable package before resolving a threshold.

    Returning a threshold is not a risk decision. The later trusted runtime
    boundary must validate source, pair, input and identity and recheck before
    publication. Any error yields an unavailable threshold.
    """
    if config is None:
        return ThresholdResult(False, None, "AUTHORITY_UNAVAILABLE")
    if official_alert or config.official_alerts or config.scope != "ACADEMIC_PROTOTYPE":
        return ThresholdResult(False, None, "SCOPE_UNAUTHORIZED")
    if config.authority != AUTHORITY or config.lock_id != LOCK_ID:
        return ThresholdResult(False, None, "AUTHORITY_UNAVAILABLE")
    if (not isinstance(active_models, tuple) or len(active_models) != 2
            or not all(isinstance(model, str) for model in active_models)
            or active_models[0] != active_models[1] or active_models[0] not in THRESHOLDS):
        return ThresholdResult(False, None, "MODEL_UNAVAILABLE")
    if config.m5a_threshold != THRESHOLDS["M5a"] or config.cv_threshold != THRESHOLDS["CV"]:
        return ThresholdResult(False, None, "THRESHOLD_INVALID")
    try:
        if not config.package_path.is_dir() or not config.pin_path.is_file() or config.pin_path.resolve().is_relative_to(config.package_path.resolve()):
            raise RuntimeConfigurationError("missing external package or pin")
        pin = json.loads(config.pin_path.read_text(encoding="utf-8"))
        if (pin.get("manifest_sha256") != MANIFEST_SHA or pin.get("lock_id") != LOCK_ID
                or pin.get("payload_sha256") != PAYLOAD_SHA):
            raise RuntimeConfigurationError("external pin mismatch")
        release = verify_active(config.package_path, MANIFEST_SHA)
        points = release.get("operating_points", {})
        model = active_models[0]
        if (release.get("lock_id") != LOCK_ID or release.get("package_identity") != PAYLOAD_SHA
                or points.get("comparator") != ">="
                or _decimal(str(points.get(model, {}).get("threshold")), "release threshold") != THRESHOLDS[model]):
            raise RuntimeConfigurationError("release identity or threshold mismatch")
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return ThresholdResult(False, None, "RELEASE_UNAVAILABLE")
    return ThresholdResult(True, THRESHOLDS[active_models[0]], None, AUTHORITY, ">=")
