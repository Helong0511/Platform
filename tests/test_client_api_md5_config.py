"""客户开放 API 的旧 MD5 签名必须由显式配置控制。"""

import hashlib
import hmac
from types import SimpleNamespace

import pytest

from app.core import api_auth, config


def test_md5_compatibility_defaults_off_in_production(monkeypatch):
    monkeypatch.setenv("PRODUCTION_ENV", "production")
    monkeypatch.delenv("CLIENT_API_ALLOW_MD5", raising=False)
    assert config._resolve_client_api_allow_md5() is False


def test_md5_compatibility_defaults_on_in_development(monkeypatch):
    monkeypatch.setenv("PRODUCTION_ENV", "development")
    monkeypatch.delenv("CLIENT_API_ALLOW_MD5", raising=False)
    assert config._resolve_client_api_allow_md5() is True


@pytest.mark.parametrize("raw, expected", [
    ("true", True), ("1", True), ("yes", True),
    ("false", False), ("0", False), ("no", False),
])
def test_explicit_md5_compatibility_setting_is_respected(monkeypatch, raw, expected):
    monkeypatch.setenv("PRODUCTION_ENV", "production")
    monkeypatch.setenv("CLIENT_API_ALLOW_MD5", raw)
    assert config._resolve_client_api_allow_md5() is expected


def _signature_inputs(secret="synthetic-client-secret"):
    values = {
        "client_id": 17,
        "secret_key": secret,
        "req_time": 1_800_000_000,
    }
    sign_string = api_auth._build_sign_string(**values)
    return values, sign_string


def test_production_setting_rejects_legacy_md5_signature(monkeypatch):
    monkeypatch.setattr(config, "settings", SimpleNamespace(CLIENT_API_ALLOW_MD5=False))
    values, sign_string = _signature_inputs()
    md5_signature = hashlib.md5(sign_string.encode("utf-8")).hexdigest()

    assert api_auth.verify_signature(**values, sign=md5_signature) is False


def test_explicit_compatibility_setting_accepts_legacy_md5_signature(monkeypatch):
    monkeypatch.setattr(config, "settings", SimpleNamespace(CLIENT_API_ALLOW_MD5=True))
    values, sign_string = _signature_inputs()
    md5_signature = hashlib.md5(sign_string.encode("utf-8")).hexdigest()

    assert api_auth.verify_signature(**values, sign=md5_signature) is True


def test_hmac_sha256_remains_supported_when_md5_is_disabled(monkeypatch):
    monkeypatch.setattr(config, "settings", SimpleNamespace(CLIENT_API_ALLOW_MD5=False))
    values, sign_string = _signature_inputs()
    signature = hmac.new(
        values["secret_key"].encode("utf-8"),
        sign_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert api_auth.verify_signature(**values, sign=signature) is True


def test_missing_md5_setting_fails_closed(monkeypatch):
    monkeypatch.setattr(config, "settings", SimpleNamespace())
    values, sign_string = _signature_inputs()
    md5_signature = hashlib.md5(sign_string.encode("utf-8")).hexdigest()

    assert api_auth.verify_signature(**values, sign=md5_signature) is False
