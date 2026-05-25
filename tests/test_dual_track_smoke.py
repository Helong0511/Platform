"""
双轨配置 smoke（令牌 + 强制写库），无真实数据库/Redis。

运行: python -m pytest tests/test_dual_track_smoke.py -v
"""
import os
import sys

import pytest

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_TEST_KEY_HEX = "a" * 64


@pytest.fixture
def dual_track_env(monkeypatch):
    from app.core import config

    monkeypatch.setenv("PERSIST_CLICKS_TO_DB", "true")
    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.setattr(
        config.settings, "AD_TRACKING_MASTER_KEY_HEX", _TEST_KEY_HEX, raising=False
    )


def test_dual_track_persist_and_mode_description(dual_track_env):
    from app.core.tracking import click_persist
    from app.core.tracking.click_token import (
        _looks_like_tracking_token,
        generate_click_id_unified,
    )

    assert click_persist.should_persist_clicks_to_db() is True
    mode = click_persist.describe_click_persist_mode()
    assert "强制写库" in mode
    assert "追踪令牌" in mode

    cid = generate_click_id_unified(offer_id=1, publisher_id=2, for_short_link=True)
    assert _looks_like_tracking_token(cid)


def test_short_link_package_registers_cloak_routes():
    from app.routes.short_link import router

    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/s/{short_code}" in paths
    assert "/change/{short_code}" in paths
    assert "/report" in paths


def test_cloak_modules_import_chain():
    from app.routes.short_link.cloak_bridge_html import prepare_bridge_html
    from app.routes.short_link.cloak_show_count import resolve_session_id
    from app.routes.short_link.cloak_click_persist import schedule_cloak_report_click_persist
    from app.routes.short_link.cloak_report_service import normalize_report_phase

    assert callable(prepare_bridge_html)
    assert callable(resolve_session_id)
    assert callable(schedule_cloak_report_click_persist)
    assert normalize_report_phase("load") == "load"
