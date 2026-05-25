"""斗篷 /report 服务层单元测试。"""
import os
import sys

import pytest

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_normalize_report_phase():
    from app.routes.short_link.cloak_report_service import normalize_report_phase

    assert normalize_report_phase("load") == "load"
    assert normalize_report_phase("CLICK") == "click"
    assert normalize_report_phase("invalid") == "click"
    assert normalize_report_phase(None) == "click"


def test_resolve_report_dp_sanitizes_invalid():
    from app.routes.short_link.cloak_report_service import resolve_report_dp

    assert resolve_report_dp("../x", None, "未知") is None
    assert resolve_report_dp("master-1", None, "未知") == "master-1"


def test_resolve_report_dp_from_referer():
    from app.routes.short_link.cloak_report_service import resolve_report_dp

    referer = "https://example.com/change/abc123?dp=pixel_a"
    assert resolve_report_dp(None, None, referer) == "pixel_a"


def test_build_dedupe_key_load_vs_click():
    from app.routes.short_link.cloak_report_service import build_dedupe_key

    assert build_dedupe_key("load", "sc", "sess", "fb") == "cloak_load_fb:sc:sess"
    assert build_dedupe_key("click", "sc", "sess", "fb") == "click_count:sc:sess"
    assert build_dedupe_key("click", "sc", None, "fb") is None


def test_ensure_fbclid_generates_when_empty():
    from app.routes.short_link.cloak_report_service import ensure_fbclid

    assert ensure_fbclid("existing") == "existing"
    generated = ensure_fbclid("")
    assert len(generated) >= 32


@pytest.mark.asyncio
async def test_try_mark_report_dedupe_duplicate(monkeypatch):
    from app.routes.short_link import cloak_report_service as mod

    class _Redis:
        async def set(self, key, val, ex=None, nx=False):
            return None

    async def _fake_redis():
        return _Redis()

    monkeypatch.setattr(mod, "get_redis_client", _fake_redis)
    assert await mod.try_mark_report_dedupe("k1") is True
