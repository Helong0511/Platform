"""Offer 缓存写入路径审计：无业务读取者时不得继续产生 Redis 写入。"""
from pathlib import Path


def test_short_link_resolution_does_not_write_offer_cache():
    source = Path("app/routes/short_link/utils.py").read_text(encoding="utf-8")
    assert "set_offer_cache" not in source


def test_offer_cache_warmup_does_not_write_redis():
    source = Path("app/core/cache_manager.py").read_text(encoding="utf-8")
    start = source.index("async def warmup_offers(")
    end = source.index("async def warmup_all(", start)
    section = source[start:end]
    assert "return 0" in section
    assert "set_offer_cache" not in section
    assert "get_offer_cache_entry" not in section


def test_no_business_module_reads_offer_advertiser_cache():
    app_root = Path("app")
    readers = []
    for path in app_root.rglob("*.py"):
        if path.as_posix() == "app/core/offer_cache.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "get_offer_advertiser_id(" in source:
            readers.append(path.as_posix())
    assert readers == []


def test_no_application_module_calls_offer_cache_writer():
    app_root = Path("app")
    writers = []
    for path in app_root.rglob("*.py"):
        if path.as_posix() == "app/core/offer_cache.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "set_offer_cache(" in source:
            writers.append(path.as_posix())
    assert writers == []


def test_no_business_module_reads_offer_cache_entry():
    app_root = Path("app")
    management_modules = {
        "app/core/offer_cache.py",
        "app/core/cache_manager.py",
    }
    readers = []
    for path in app_root.rglob("*.py"):
        if path.as_posix() in management_modules:
            continue
        source = path.read_text(encoding="utf-8")
        if "get_offer_cache_entry(" in source:
            readers.append(path.as_posix())
    assert readers == []
