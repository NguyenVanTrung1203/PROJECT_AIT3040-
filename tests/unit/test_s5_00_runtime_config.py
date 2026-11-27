"""S5-00 configuration tests; no model inference or Test split access."""
from dataclasses import replace
from decimal import Decimal
import json
import pytest
from src.runtime import config as c


@pytest.fixture
def setup(tmp_path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    pin = tmp_path / "external-pin.json"
    pin.write_text(json.dumps({"manifest_sha256": c.MANIFEST_SHA, "lock_id": c.LOCK_ID,
                               "payload_sha256": c.PAYLOAD_SHA}), encoding="utf8")
    env = {"AIT3040_MODEL_PACKAGE": str(package),
           "AIT3040_MODEL_MANIFEST_PIN": str(pin),
           "AIT3040_RUNTIME_DEVICE": "cpu",
           "AIT3040_RUNTIME_AUTHORITY": c.AUTHORITY,
           "AIT3040_DEMO_MAX_VESSELS": "10",
           "AIT3040_MAX_CONCURRENCY": "1"}
    def verified(path, manifest):
        assert path == package.resolve() and manifest == c.MANIFEST_SHA
        return {"lock_id": c.LOCK_ID, "package_identity": c.PAYLOAD_SHA,
                "operating_points": {"M5a": {"threshold": 0.42},
                                     "CV": {"threshold": 0.435}, "comparator": ">="}}
    monkeypatch.setattr(c, "verify_active", verified)
    return env, pin


@pytest.mark.parametrize("model,threshold", [("M5a", "0.420"), ("CV", "0.435")])
def test_valid_prototype_authority(setup, model, threshold):
    env, _ = setup
    result = c.resolve_threshold(c.load_config(env), (model, model))
    assert result.available and result.threshold == Decimal(threshold)
    assert result.authority == c.AUTHORITY and result.comparator == ">="


def test_missing_authority_and_package_fail_closed(setup):
    env, _ = setup
    for key in ("AIT3040_RUNTIME_AUTHORITY", "AIT3040_MODEL_PACKAGE",
                "AIT3040_MODEL_MANIFEST_PIN"):
        invalid = dict(env)
        invalid.pop(key)
        with pytest.raises(c.RuntimeConfigurationError):
            c.load_config(invalid)
    assert c.resolve_threshold(None, ("M5a", "M5a")).threshold is None


@pytest.mark.parametrize("key,value", [
    ("AIT3040_MODEL_LOCK_ID", "wrong"),
    ("AIT3040_M5A_THRESHOLD", "0.435"),
    ("AIT3040_CV_THRESHOLD", "NaN"),
    ("AIT3040_CV_THRESHOLD", "0.420"),
    ("AIT3040_RUNTIME_DEVICE", "auto"),
    ("AIT3040_RUNTIME_SCOPE", "PRODUCTION"),
    ("AIT3040_OFFICIAL_ALERTS", "true"),
    ("AIT3040_MAX_CONCURRENCY", "0"),
    ("AIT3040_DEMO_MAX_VESSELS", "1"),
])
def test_invalid_configuration_rejected(setup, key, value):
    env, _ = setup
    env[key] = value
    with pytest.raises(c.RuntimeConfigurationError):
        c.load_config(env)


def test_mixed_and_unknown_models_never_resolve(setup):
    cfg = c.load_config(setup[0])
    for pair in (("M5a", "CV"), ("CV", "M5a"), ("M5a", "unknown"), ("M5a",), ([], [])):
        result = c.resolve_threshold(cfg, pair)
        assert not result.available and result.threshold is None


def test_official_alert_and_modified_configuration_rejected(setup):
    cfg = c.load_config(setup[0])
    assert c.resolve_threshold(cfg, ("M5a", "M5a"), official_alert=True).threshold is None
    assert c.resolve_threshold(replace(cfg, lock_id="wrong"), ("CV", "CV")).threshold is None
    assert c.resolve_threshold(replace(cfg, cv_threshold=Decimal("0.420")), ("CV", "CV")).threshold is None


def test_tampered_pin_and_failed_verifier_are_unavailable(setup, monkeypatch):
    env, pin = setup
    cfg = c.load_config(env)
    pin.write_text("{}", encoding="utf8")
    assert c.resolve_threshold(cfg, ("M5a", "M5a")).threshold is None
    pin.write_text(json.dumps({"manifest_sha256": c.MANIFEST_SHA, "lock_id": c.LOCK_ID,
                               "payload_sha256": c.PAYLOAD_SHA}), encoding="utf8")
    def reject(*_args):
        raise ValueError("integrity")
    monkeypatch.setattr(c, "verify_active", reject)
    assert c.resolve_threshold(cfg, ("M5a", "M5a")).threshold is None


def test_release_active_model_threshold_mismatch_unavailable(setup, monkeypatch):
    cfg = c.load_config(setup[0])
    monkeypatch.setattr(c, "verify_active", lambda *_: {
        "lock_id": c.LOCK_ID, "package_identity": c.PAYLOAD_SHA,
        "operating_points": {"M5a": {"threshold": 0.435}, "comparator": ">="}})
    assert c.resolve_threshold(cfg, ("M5a", "M5a")).threshold is None
