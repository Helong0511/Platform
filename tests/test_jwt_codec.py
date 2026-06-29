"""JWT 编解码单元测试。"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.jwt_codec import (
    ExpiredSignatureError,
    decode,
    decode_unsigned_payload,
    encode,
)


def test_jwt_roundtrip_hs256():
    secret = "test-secret-key-at-least-32-bytes!"
    payload = {
        "sub": "42",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "type": "access",
    }
    token = encode(payload, secret, algorithm="HS256")
    decoded = decode(token, secret, algorithms=["HS256"])
    assert decoded["sub"] == "42"
    assert decoded["type"] == "access"


def test_jwt_decode_without_signature():
    secret = "test-secret-key-at-least-32-bytes!"
    token = encode({"sub": "7"}, secret, algorithm="HS256")
    decoded = decode_unsigned_payload(token)
    assert decoded["sub"] == "7"


def test_jwt_expired_raises():
    secret = "test-secret-key-at-least-32-bytes!"
    payload = {
        "sub": "1",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
    }
    token = encode(payload, secret, algorithm="HS256")
    with pytest.raises(ExpiredSignatureError):
        decode(token, secret, algorithms=["HS256"])
