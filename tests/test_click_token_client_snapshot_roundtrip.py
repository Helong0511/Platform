import pytest

from app.core.tracking.ad_tracking_codec import AdTrackingCodec
from app.core.tracking.click_token import (
    REASON_OK,
    association_from_parsed,
    generate_tracking_click_id,
)


@pytest.mark.parametrize(
    "key_hex, message",
    [
        ("", "未配置"),
        (AdTrackingCodec._DEFAULT_KEY_HEX, "默认密钥"),
        ("abc", "64 位"),
        ("z" * 64, "十六进制"),
    ],
)
def test_production_tracking_key_rejects_unsafe_values(key_hex, message):
    with pytest.raises(ValueError, match=message):
        AdTrackingCodec.validate_production_master_key(key_hex)


def test_production_tracking_key_accepts_independent_32_byte_hex_key():
    key_hex = "ab" * 32
    assert AdTrackingCodec.validate_production_master_key(key_hex) == bytes.fromhex(key_hex)


@pytest.mark.parametrize("token_format", ["compact", "full"])
def test_click_time_client_snapshot_survives_signed_token_roundtrip(
    monkeypatch, token_format
):
    # 测试使用独立临时密钥，避免依赖开发默认密钥或真实生产密钥。
    monkeypatch.setenv("AD_TRACKING_MASTER_KEY_HEX", "cd" * 32)

    token = generate_tracking_click_id(
        offer_id=10,
        publisher_id=20,
        advertiser_id=30,
        extra={"client_id": 55},
        token_format=token_format,
    )

    verified = AdTrackingCodec.verify(token)
    assert verified["valid"] is True

    parsed = AdTrackingCodec.parse(token)
    assert parsed["valid"] is True
    assert parsed["reason"] == REASON_OK

    association = association_from_parsed(parsed)
    assert association is not None
    assert association["client_id"] == 55
    assert association["publisher_id"] == 20


def test_signed_tracking_token_rejects_tampering(monkeypatch):
    monkeypatch.setenv("AD_TRACKING_MASTER_KEY_HEX", "ef" * 32)
    token = generate_tracking_click_id(
        offer_id=10,
        publisher_id=20,
        extra={"client_id": 55},
        token_format="full",
    )
    replacement = "1" if token[-1] != "1" else "2"
    tampered = token[:-1] + replacement

    assert AdTrackingCodec.verify(token)["valid"] is True
    assert AdTrackingCodec.verify(tampered)["valid"] is False
