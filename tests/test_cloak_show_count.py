"""斗篷展示次数模块单元测试。"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_resolve_session_id_from_cookie():
    from app.routes.short_link.cloak_show_count import resolve_session_id

    req = MagicMock()
    req.cookies = {"session_id": "abc-123"}
    assert resolve_session_id(req) == "abc-123"


def test_resolve_session_id_generates_when_missing():
    from app.routes.short_link.cloak_show_count import resolve_session_id

    req = MagicMock()
    req.cookies = {}
    sid = resolve_session_id(req)
    assert len(sid) >= 32


@pytest.mark.asyncio
async def test_session_already_shown_first_visit(monkeypatch):
    from app.routes.short_link import cloak_show_count as mod

    class _Redis:
        async def set(self, key, val, ex=None, nx=False):
            return True

    async def _fake_redis():
        return _Redis()

    monkeypatch.setattr(mod, "get_redis_client", _fake_redis)
    assert await mod.session_already_shown("sc1", "sess1") is False


@pytest.mark.asyncio
async def test_session_already_shown_repeat(monkeypatch):
    from app.routes.short_link import cloak_show_count as mod

    class _Redis:
        async def set(self, key, val, ex=None, nx=False):
            return None

    async def _fake_redis():
        return _Redis()

    monkeypatch.setattr(mod, "get_redis_client", _fake_redis)
    assert await mod.session_already_shown("sc1", "sess1") is True
