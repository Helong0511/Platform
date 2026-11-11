"""短链 Pixel 配置缓存生命周期回归测试。"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services import cloak_pixel_mapping
from app.services.cloak_pixel_mapping import CloakPixelMappingService
from app.services.short_link_service import ShortLinkService


def test_pixel_cache_can_be_invalidated_by_short_code():
    service = CloakPixelMappingService()
    service._cache = {
        "short-a:dp1": {"facebook_pixel_id": "1"},
        "short-a:dp2": {"facebook_pixel_id": "2"},
        "short-b:dp1": {"facebook_pixel_id": "3"},
    }
    service._cache_timestamps = {
        key: datetime.now().timestamp() for key in service._cache
    }

    service.invalidate_cache_for_short_code("short-a")

    assert set(service._cache) == {"short-b:dp1"}
    assert set(service._cache_timestamps) == {"short-b:dp1"}


@pytest.mark.asyncio
async def test_expired_cached_pixel_config_is_not_returned(monkeypatch):
    service = CloakPixelMappingService()
    service._cache["short-expired:master"] = {
        "facebook_pixel_id": "stale-pixel",
        "facebook_access_token": "stale-token",
        "is_active": True,
        "expires_at": datetime(2026, 11, 10, 23, 59, 59),
    }
    service._cache_timestamps["short-expired:master"] = datetime.now().timestamp()

    short_link = SimpleNamespace(
        short_code="short-expired",
        is_active=True,
        expires_at=datetime(2026, 11, 10, 23, 59, 59),
        facebook_pixel_id="stale-pixel",
        facebook_access_token="stale-token",
        facebook_api_version="v23.0",
        original_url="https://example.invalid",
        title="expired",
        offer_id=None,
        channel_id=None,
    )

    class ScalarRows:
        def first(self):
            return short_link

    class Result:
        def scalars(self):
            return ScalarRows()

    class FakeDB:
        async def execute(self, statement):
            return Result()

    monkeypatch.setattr(
        cloak_pixel_mapping,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )

    result = await service.get_pixel_config_by_dp_param(
        db=FakeDB(),
        dp="master",
        short_code="short-expired",
        use_cache=True,
    )

    assert result is None
    assert "short-expired:master" not in service._cache


@pytest.mark.asyncio
async def test_short_link_update_and_delete_invalidate_pixel_config_cache(monkeypatch):
    link = SimpleNamespace(short_code="short-cache-lifecycle")
    invalidated = []

    class FakeDB:
        async def flush(self):
            return None

        async def refresh(self, obj):
            return None

        async def delete(self, obj):
            return None

    async def get_link(self, link_id, current_user, include_relations=True):
        return link

    async def invalidate_short_cache(short_code):
        return None

    async def cleanup_counter(short_code):
        return None

    monkeypatch.setattr(ShortLinkService, "get_short_link_by_id", get_link)
    monkeypatch.setattr(ShortLinkService, "require_admin", lambda self, user: None)
    monkeypatch.setattr(
        "app.services.short_link_service.invalidate_short_link_cache",
        invalidate_short_cache,
    )
    monkeypatch.setattr(
        "app.services.short_link_service.cleanup_click_counter",
        cleanup_counter,
    )
    monkeypatch.setattr(
        cloak_pixel_mapping,
        "invalidate_cloak_cache",
        lambda **kwargs: invalidated.append(kwargs["short_code"]),
    )

    service = ShortLinkService(FakeDB())
    user = SimpleNamespace(id=1)

    await service.update_short_link(
        link_id=7,
        link_data={"facebook_access_token": "rotated-token", "is_active": False},
        current_user=user,
    )
    await service.delete_short_link(link_id=7, current_user=user)

    assert invalidated == ["short-cache-lifecycle", "short-cache-lifecycle"]
