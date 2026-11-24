"""广告主没有独立缓存读写路径，不应执行无效的 Redis 失效任务。"""
from pathlib import Path


def test_advertiser_service_does_not_schedule_nonexistent_cache_invalidation():
    source = Path("app/services/cpl/advertiser_service.py").read_text(encoding="utf-8")
    assert "CacheInvalidator" not in source
    assert "invalidate_advertiser_cache" not in source
    assert "legacy_get_cached" not in source
    assert "legacy_set_cached" not in source


def test_advertiser_api_remains_database_authoritative():
    source = Path("app/api_v1/cpl/advertisers.py").read_text(encoding="utf-8")
    assert "CacheInvalidator" not in source
    assert "invalidate_advertiser_cache" not in source


def test_no_business_module_calls_advertiser_cache_invalidator():
    app_root = Path("app")
    callers = []
    for path in app_root.rglob("*.py"):
        if path.as_posix() == "app/core/infrastructure/cache.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "invalidate_advertiser_cache(" in source:
            callers.append(path.as_posix())
    assert callers == []
