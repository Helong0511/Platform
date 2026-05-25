"""生产环境追踪密钥校验（不依赖数据库）"""
import os

import pytest

from app.core.tracking.ad_tracking_codec import AdTrackingCodec


def test_default_dev_key_is_64_hex():
    assert len(AdTrackingCodec._DEFAULT_KEY_HEX) == 64


def test_master_key_rejects_invalid_hex_length(monkeypatch):
    monkeypatch.setattr(
        AdTrackingCodec,
        "_resolve_master_key_hex",
        classmethod(lambda cls: "abc"),
    )
    with pytest.raises(ValueError, match="64"):
        AdTrackingCodec._master_key()


def test_production_rejects_builtin_default_key(monkeypatch):
    """与 config 启动校验一致：生产 + 默认密钥应视为不安全。"""
    monkeypatch.setenv("PRODUCTION_ENV", "production")
    monkeypatch.setenv("AD_TRACKING_MASTER_KEY_HEX", AdTrackingCodec._DEFAULT_KEY_HEX)
    assert AdTrackingCodec._DEFAULT_KEY_HEX == os.environ["AD_TRACKING_MASTER_KEY_HEX"]
