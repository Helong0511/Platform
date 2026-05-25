"""
预发双轨自动化门控（无真实 DB/Redis，CI 与预发 --auto 共用）。

运行:
  python -m pytest tests/test_dual_track_prerelease_gates.py -v
"""
import os
import sys

import pytest

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_TEST_KEY_HEX = "b" * 64


@pytest.fixture
def dual_track_env(monkeypatch):
    from app.core import config

    monkeypatch.setenv("PERSIST_CLICKS_TO_DB", "true")
    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.setattr(
        config.settings, "AD_TRACKING_MASTER_KEY_HEX", _TEST_KEY_HEX, raising=False
    )


def test_startup_mode_description_matches_dual_track(dual_track_env):
    from app.core.tracking import click_persist

    mode = click_persist.describe_click_persist_mode()
    assert click_persist.should_persist_clicks_to_db() is True
    assert "强制写库" in mode
    assert "追踪令牌" in mode


@pytest.mark.asyncio
async def test_token_associator_returns_ids_without_clicks_row(dual_track_env):
    """ClickAssociator：令牌路径在无 clicks 行时仍能返回 offer/publisher/advertiser ID。"""
    from unittest.mock import AsyncMock

    from app.core.tracking.click_token import generate_click_id_unified
    from app.core.postback.transformers.click_associator import ClickAssociator

    cid = generate_click_id_unified(offer_id=11, publisher_id=22, advertiser_id=33)
    db = AsyncMock()
    assoc = await ClickAssociator.associate(cid, db)
    assert assoc is not None
    assert assoc.get("_from_token") is True
    assert assoc["offer_id"] == 11
    assert assoc["publisher_id"] == 22
    assert assoc["advertiser_id"] == 33


@pytest.mark.asyncio
async def test_cloak_persist_scheduled_when_dual_track(dual_track_env):
    from app.routes.short_link.cloak_click_persist import schedule_cloak_report_click_persist

    class _Bg:
        def __init__(self):
            self.tasks = []

        def add_task(self, fn):
            self.tasks.append(fn)

    bg = _Bg()
    schedule_cloak_report_click_persist(
        bg,
        short_code="pre",
        fbclid="fb",
        resolved_dp=None,
        email=None,
        phone=None,
        client_ip="127.0.0.1",
        user_agent="ua",
        referer=None,
        original_request_url="http://x/s/pre",
    )
    assert len(bg.tasks) == 1


def test_prerelease_checklist_module_importable():
    from tests.dual_track_prerelease_checklist import MANUAL_CHECKLIST, validate_env_file

    assert len(MANUAL_CHECKLIST) >= 4
    assert isinstance(validate_env_file(), list)
