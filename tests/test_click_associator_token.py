"""
ClickAssociator + 追踪令牌集成测试（无数据库）。

运行方式（推荐）:
    python -m pytest tests/test_click_associator_token.py -v

勿用「python 本文件」裸跑（旧方式只 import 不执行用例）；若直接运行会自动转 pytest。
"""
import os
import sys

os.environ.setdefault("UNIT_TEST", "1")
os.environ.setdefault("PRODUCTION_ENV", "development")

from unittest.mock import AsyncMock, MagicMock

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.tracking.click_token import resolve_click_from_token
from app.core.tracking.ad_tracking_codec import AdTrackingCodec


@pytest.mark.asyncio
async def test_token_association_has_ids_without_db(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "TRACKING_TOKEN_MAX_AGE_SECONDS", None, raising=False)

    token = AdTrackingCodec.generate(
        {"oid": 10, "pub": 20, "aid": 30},
        format="auto",
    )
    assoc = resolve_click_from_token(token)
    assert assoc is not None
    assert assoc["offer_id"] == 10
    assert assoc["publisher_id"] == 20
    assert assoc["advertiser_id"] == 30
    assert assoc.get("click_time") is not None


@pytest.mark.asyncio
async def test_enrich_loads_publisher_orm(monkeypatch):
    from app.core import config
    from app.core.postback.transformers.click_associator import ClickAssociator

    monkeypatch.setattr(config.settings, "TRACKING_TOKEN_MAX_AGE_SECONDS", None, raising=False)

    token = AdTrackingCodec.generate({"oid": 1, "pub": 2, "aid": 3}, format="auto")
    base = resolve_click_from_token(token)
    assert base is not None

    mock_pub = MagicMock()
    mock_pub.id = 2
    mock_pub.publisher_name = "TestPub"

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_pub

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    enriched = await ClickAssociator._enrich_association(base, db)
    assert enriched.get("publisher") is mock_pub


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
