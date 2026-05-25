"""斗篷 /report 点击落库与 click_id 生成。"""
import os
import sys

import pytest

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_build_cloak_url_params():
    from app.routes.short_link.cloak_click_persist import build_cloak_url_params

    raw = build_cloak_url_params("fb1", "dp1", "a@b.com", "123")
    assert raw is not None
    import json

    data = json.loads(raw)
    assert data["fbclid"] == "fb1"
    assert data["dp"] == "dp1"


def test_schedule_skips_when_persist_off(monkeypatch):
    from app.core import config
    from app.routes.short_link.cloak_click_persist import schedule_cloak_report_click_persist

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.delenv("PERSIST_CLICKS_TO_DB", raising=False)

    class _Bg:
        def __init__(self):
            self.tasks = []

        def add_task(self, fn):
            self.tasks.append(fn)

    bg = _Bg()
    schedule_cloak_report_click_persist(
        bg,
        short_code="abc",
        fbclid="f",
        resolved_dp=None,
        email="e@e.com",
        phone="1",
        client_ip="1.1.1.1",
        user_agent="ua",
        referer="ref",
        original_request_url=None,
    )
    assert len(bg.tasks) == 0


def test_schedule_adds_task_when_persist_on(monkeypatch):
    from app.core import config
    from app.routes.short_link.cloak_click_persist import schedule_cloak_report_click_persist

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.setenv("PERSIST_CLICKS_TO_DB", "true")

    class _Bg:
        def __init__(self):
            self.tasks = []

        def add_task(self, fn):
            self.tasks.append(fn)

    bg = _Bg()
    schedule_cloak_report_click_persist(
        bg,
        short_code="abc",
        fbclid="f",
        resolved_dp=None,
        email="e@e.com",
        phone="1",
        client_ip="1.1.1.1",
        user_agent="ua",
        referer="ref",
        original_request_url=None,
    )
    assert len(bg.tasks) == 1
