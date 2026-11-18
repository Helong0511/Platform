"""短链 Pixel 配置生命周期与多 Worker 权威读取回归测试。"""
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


@pytest.mark.asyncio
async def test_multiple_worker_instances_never_serve_stale_pixel_credentials(monkeypatch):
    """不同 Gunicorn Worker 的服务实例必须以数据库当前值为准。"""
    short_link = SimpleNamespace(
        short_code="multi-worker-link",
        is_active=True,
        expires_at=None,
        facebook_pixel_id="123456789012345",
        facebook_access_token="old-token",
        facebook_api_version="v23.0",
        original_url="https://example.invalid",
        title="multi-worker",
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

    monkeypatch.setattr(cloak_pixel_mapping, "bridge_html_exists", lambda dp: False)
    monkeypatch.setattr(
        cloak_pixel_mapping,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 11, 12, 0, 0),
    )

    # 模拟 Worker A 读取并曾经持有旧配置；Worker B 在数据库提交配置轮换。
    worker_a = CloakPixelMappingService()
    worker_b = CloakPixelMappingService()
    db = FakeDB()

    first = await worker_a.get_pixel_config_by_dp_param(
        db=db, dp="master", short_code="multi-worker-link", use_cache=True
    )
    assert first["facebook_access_token"] == "old-token"

    short_link.facebook_pixel_id = "987654321098765"
    short_link.facebook_access_token = "new-token"

    # 即使 Worker B 没有收到 Worker A 的本地缓存失效通知，也必须读到新值。
    second = await worker_b.get_pixel_config_by_dp_param(
        db=db, dp="master", short_code="multi-worker-link", use_cache=True
    )
    third = await worker_a.get_pixel_config_by_dp_param(
        db=db, dp="master", short_code="multi-worker-link", use_cache=True
    )

    assert second["facebook_pixel_id"] == "987654321098765"
    assert second["facebook_access_token"] == "new-token"
    assert third["facebook_pixel_id"] == "987654321098765"
    assert third["facebook_access_token"] == "new-token"
    assert worker_a._cache == {}
    assert worker_b._cache == {}


@pytest.mark.asyncio
async def test_pixel_mapping_database_exception_does_not_leak_pii_to_logs(monkeypatch, caplog):
    service = CloakPixelMappingService()

    class FakeDB:
        async def execute(self, statement):
            raise RuntimeError("email=buyer@example.invalid ip=203.0.113.44 click_id=secret-click")

    with caplog.at_level("WARNING", logger=cloak_pixel_mapping.__name__):
        result = await service.get_pixel_config_by_dp_param(
            db=FakeDB(),
            dp="master",
            short_code="safe-short-code",
            use_cache=False,
        )

    assert result is None
    assert "RuntimeError" in caplog.text
    assert "safe-short-code" in caplog.text
    assert "buyer@example.invalid" not in caplog.text
    assert "203.0.113.44" not in caplog.text
    assert "secret-click" not in caplog.text


@pytest.mark.asyncio
async def test_cloak_disable_delete_and_same_name_restore_resolves_current_credentials(monkeypatch):
    """Outbox 重试应在斗篷停用/删除时停止发送，并在同名配置恢复后读取新凭据。"""
    short_link = SimpleNamespace(
        short_code="cloak-lifecycle-link",
        is_active=True,
        expires_at=None,
        facebook_pixel_id=None,
        facebook_access_token=None,
        facebook_api_version="v23.0",
        original_url="https://example.invalid",
        title="cloak-lifecycle",
        offer_id=None,
        channel_id=None,
    )
    current_config = SimpleNamespace(
        is_enabled=False,
        pixel_id="123456789012345",
        access_token="old-cloak-token",
        backup_pixel_id=None,
        backup_access_token=None,
        report_event="Purchase",
        report_value=1,
        report_currency="USD",
    )

    class ScalarRows:
        def __init__(self, value):
            self.value = value

        def first(self):
            return self.value

    class Result:
        def __init__(self, value):
            self.value = value

        def scalars(self):
            return ScalarRows(self.value)

    class FakeDB:
        async def execute(self, statement):
            if "short_links" in str(statement).lower():
                return Result(short_link)
            return Result(
                current_config
                if current_config is not None and current_config.is_enabled
                else None
            )

    monkeypatch.setattr(cloak_pixel_mapping, "bridge_html_exists", lambda dp: True)
    monkeypatch.setattr(
        cloak_pixel_mapping,
        "get_app_now_naive",
        lambda: datetime(2026, 11, 12, 12, 0, 0),
    )
    service = CloakPixelMappingService()
    db = FakeDB()

    # 停用配置不可用于发送。
    assert await service.get_pixel_config_by_dp_param(
        db=db, dp="restorable-cloak", short_code=short_link.short_code
    ) is None

    # 删除配置后仍不可发送，不会错误回退到旧进程缓存。
    current_config = None
    assert await service.get_pixel_config_by_dp_param(
        db=db, dp="restorable-cloak", short_code=short_link.short_code
    ) is None

    # 管理员以相同 dp 名称恢复配置并轮换 Token，Outbox 后续重试读取新凭据。
    current_config = SimpleNamespace(
        is_enabled=True,
        pixel_id="987654321098765",
        access_token="restored-new-token",
        backup_pixel_id=None,
        backup_access_token=None,
        report_event="Purchase",
        report_value=2,
        report_currency="USD",
    )
    restored = await service.get_pixel_config_by_dp_param(
        db=db, dp="restorable-cloak", short_code=short_link.short_code
    )

    assert restored["facebook_pixel_id"] == "987654321098765"
    assert restored["facebook_access_token"] == "restored-new-token"
    assert restored["cloak_report_value"] == 2
    assert service._cache == {}
