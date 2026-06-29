"""客户 API 签名验证单元测试。"""
import hashlib
import hmac
import time

from app.core.api_auth import _build_sign_string, verify_signature


def test_hmac_sha256_signature_accepted():
    secret = "test-secret-key"
    req_time = int(time.time())
    sign_string = _build_sign_string(42, secret, req_time, data_type="all")
    sign = hmac.new(
        secret.encode("utf-8"),
        sign_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().lower()

    assert verify_signature(
        client_id=42,
        secret_key=secret,
        req_time=req_time,
        sign=sign,
        data_type="all",
    )


def test_md5_signature_still_compatible():
    secret = "legacy-secret"
    req_time = 1700000000
    sign_string = _build_sign_string(7, secret, req_time)
    sign = hashlib.md5(sign_string.encode("utf-8")).hexdigest().lower()

    assert verify_signature(
        client_id=7,
        secret_key=secret,
        req_time=req_time,
        sign=sign,
    )
