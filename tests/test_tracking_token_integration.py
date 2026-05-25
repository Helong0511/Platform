"""
追踪令牌：生成 → Postback 关联 → 短链长度（无数据库）。

运行: python -m pytest tests/test_tracking_token_integration.py -v
"""
import os
import sys

import pytest

os.environ.setdefault("UNIT_TEST", "1")
os.environ.setdefault("PRODUCTION_ENV", "development")

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_TEST_KEY_HEX = "a" * 64


@pytest.fixture
def enable_tracking_token(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.setattr(
        config.settings, "AD_TRACKING_MASTER_KEY_HEX", _TEST_KEY_HEX, raising=False
    )
    monkeypatch.setattr(config.settings, "TRACKING_TOKEN_MAX_AGE_SECONDS", None, raising=False)


def test_generate_and_resolve_roundtrip(enable_tracking_token):
    from app.core.tracking.click_token import (
        generate_click_id_unified,
        resolve_click_from_token,
        CLICK_ID_SHORT_LINK_MAX_OUTER,
        CLICK_ID_MAX_LENGTH,
    )

    cid = generate_click_id_unified(offer_id=101, publisher_id=202, advertiser_id=303)
    assert len(cid) <= CLICK_ID_MAX_LENGTH
    assoc = resolve_click_from_token(cid)
    assert assoc is not None
    assert assoc["offer_id"] == 101
    assert assoc["publisher_id"] == 202
    assert assoc["advertiser_id"] == 303


def test_short_link_click_id_within_60(enable_tracking_token):
    from app.core.tracking.click_token import (
        generate_click_id_unified,
        CLICK_ID_SHORT_LINK_MAX_OUTER,
        CLICK_ID_MAX_LENGTH,
        _looks_like_tracking_token,
    )

    # 短链仅带 offer，compact 令牌应 ≤60；超限时回退旧版随机 id
    cid = generate_click_id_unified(offer_id=1, for_short_link=True)
    assert len(cid) <= CLICK_ID_MAX_LENGTH
    if _looks_like_tracking_token(cid):
        assert len(cid) <= CLICK_ID_SHORT_LINK_MAX_OUTER


@pytest.mark.asyncio
async def test_click_associator_token_path(enable_tracking_token, monkeypatch):
    from unittest.mock import AsyncMock

    from app.core.tracking.click_token import generate_click_id_unified
    from app.core.postback.transformers.click_associator import ClickAssociator

    cid = generate_click_id_unified(offer_id=9, publisher_id=8, advertiser_id=7)
    db = AsyncMock()
    db.execute = AsyncMock()
    assoc = await ClickAssociator.associate(cid, db)
    assert assoc is not None
    assert assoc["offer_id"] == 9
    assert assoc["publisher_id"] == 8
    assert assoc.get("_from_token") is True


def test_legacy_random_click_id_when_token_disabled(monkeypatch):
    from app.core import config
    from app.core.tracking.click_token import generate_click_id_unified, use_tracking_token

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", False, raising=False)
    legacy = generate_click_id_unified()
    assert not use_tracking_token()
    assert len(legacy) >= 10


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
