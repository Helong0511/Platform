"""短链接更新/删除时，必须同时失效像素配置内存缓存。"""
from types import SimpleNamespace

import pytest

from app.services import short_link_service as service_module
from app.services.short_link_service import ShortLinkService


class FakeDB:
    async def flush(self):
        return None

    async def refresh(self, obj):
        return None

    async def delete(self, obj):
        return None


@pytest.mark.asyncio
async def test_update_short_link_invalidates_pixel_config_cache(monkeypatch):
    link = SimpleNamespace(short_code="cache-update-001", original_url="https://old.example")
    service = ShortLinkService.__new__(ShortLinkService)
    service.db = FakeDB()
    user = SimpleNamespace(id=1, role="admin")
    calls = {"redirect": [], "pixel": []}

    async def get_link(*args, **kwargs):
        return link

    async def invalidate_redirect(short_code):
        calls["redirect"].append(short_code)

    def invalidate_pixel(short_code=None, dp=None):
        calls["pixel"].append((short_code, dp))

    monkeypatch.setattr(service, "get_short_link_by_id", get_link)
    monkeypatch.setattr(service, "require_admin", lambda current_user: None)
    monkeypatch.setattr(service_module, "invalidate_short_link_cache", invalidate_redirect)
    monkeypatch.setattr(
        "app.services.cloak_pixel_mapping.invalidate_cloak_cache",
        invalidate_pixel,
    )

    updated = await service.update_short_link(1, {"original_url": "https://new.example"}, user)

    assert updated is link
    assert link.original_url == "https://new.example"
    assert calls["redirect"] == ["cache-update-001"]
    assert calls["pixel"] == [("cache-update-001", None)]


@pytest.mark.asyncio
async def test_delete_short_link_invalidates_pixel_cache_and_click_counter(monkeypatch):
    link = SimpleNamespace(short_code="cache-delete-001")
    service = ShortLinkService.__new__(ShortLinkService)
    service.db = FakeDB()
    user = SimpleNamespace(id=1, role="admin")
    calls = {"redirect": [], "pixel": [], "counter": []}

    async def get_link(*args, **kwargs):
        return link

    async def invalidate_redirect(short_code):
        calls["redirect"].append(short_code)

    def invalidate_pixel(short_code=None, dp=None):
        calls["pixel"].append((short_code, dp))

    async def cleanup_counter(short_code):
        calls["counter"].append(short_code)

    monkeypatch.setattr(service, "get_short_link_by_id", get_link)
    monkeypatch.setattr(service, "require_admin", lambda current_user: None)
    monkeypatch.setattr(service_module, "invalidate_short_link_cache", invalidate_redirect)
    monkeypatch.setattr(service_module, "cleanup_click_counter", cleanup_counter)
    monkeypatch.setattr(
        "app.services.cloak_pixel_mapping.invalidate_cloak_cache",
        invalidate_pixel,
    )

    await service.delete_short_link(1, user)

    assert calls["redirect"] == ["cache-delete-001"]
    assert calls["pixel"] == [("cache-delete-001", None)]
    assert calls["counter"] == ["cache-delete-001"]


def test_short_link_api_reinvalidates_pixel_cache_after_commit():
    from pathlib import Path

    source = Path("app/api_v1/tracking/short_links.py").read_text(encoding="utf-8")
    update_commit = source.index("await commit_audit_log(db)", source.index("async def update_short_link"))
    update_invalidate = source.index(
        "invalidate_cloak_cache(short_code=short_link.short_code)",
        update_commit,
    )
    delete_commit = source.index("await commit_audit_log(db)", source.index("async def delete_short_link"))
    delete_invalidate = source.index(
        "invalidate_cloak_cache(short_code=short_code)",
        delete_commit,
    )

    assert update_invalidate > update_commit
    assert delete_invalidate > delete_commit
