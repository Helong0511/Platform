"""客户 API 旧 MD5 签名策略必须 fail-closed。"""

import hashlib
import hmac
from types import SimpleNamespace

from app.core import api_auth, config


def _signature_inputs():
    values = {
        "client_id": 17,
        "secret_key": "synthetic-client-secret",
        "req_time": 1_800_000_000,
    }
    return values, api_auth._build_sign_string(**values)


def test_md5_is_rejected_when_policy_setting_is_missing(monkeypatch):
    monkeypatch.setattr(config, "settings", SimpleNamespace())
    values, sign_string = _signature_inputs()
    signature = hashlib.md5(sign_string.encode("utf-8")).hexdigest()

    assert api_auth.verify_signature(**values, sign=signature) is False


def test_md5_is_rejected_when_policy_is_disabled(monkeypatch):
    monkeypatch.setattr(config, "settings", SimpleNamespace(CLIENT_API_ALLOW_MD5=False))
    values, sign_string = _signature_inputs()
    signature = hashlib.md5(sign_string.encode("utf-8")).hexdigest()

    assert api_auth.verify_signature(**values, sign=signature) is False


def test_md5_is_accepted_only_when_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(config, "settings", SimpleNamespace(CLIENT_API_ALLOW_MD5=True))
    values, sign_string = _signature_inputs()
    signature = hashlib.md5(sign_string.encode("utf-8")).hexdigest()

    assert api_auth.verify_signature(**values, sign=signature) is True


def test_hmac_sha256_remains_available_when_md5_is_disabled(monkeypatch):
    monkeypatch.setattr(config, "settings", SimpleNamespace(CLIENT_API_ALLOW_MD5=False))
    values, sign_string = _signature_inputs()
    signature = hmac.new(
        values["secret_key"].encode("utf-8"),
        sign_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert api_auth.verify_signature(**values, sign=signature) is True
