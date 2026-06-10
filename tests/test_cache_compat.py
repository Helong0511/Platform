"""cache_compat 与旧 query_cache 键命名空间一致性测试。"""
from app.core.infrastructure import cache_compat


def test_legacy_storage_key_adds_prefix_once():
    assert cache_compat._legacy_storage_key("abc123") == "query_cache:abc123"
    assert cache_compat._legacy_storage_key("query_cache:abc123") == "query_cache:abc123"


def test_generate_cache_key_deterministic():
    k1 = cache_compat.generate_cache_key("dashboard", 1, period="week")
    k2 = cache_compat.generate_cache_key("dashboard", 1, period="week")
    k3 = cache_compat.generate_cache_key("dashboard", 1, period="month")
    assert k1 == k2
    assert k1 != k3


def test_cache_prefix_constant():
    assert cache_compat.CACHE_PREFIX == "query_cache:"
