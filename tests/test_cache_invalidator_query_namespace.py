"""CacheInvalidator 必须删除旧查询缓存实际使用的 query_cache: 键空间。"""
from unittest.mock import AsyncMock

import pytest

from app.core.infrastructure import cache


@pytest.mark.asyncio
async def test_cache_invalidator_prefixes_legacy_query_cache_namespace(monkeypatch):
    backend = type("Backend", (), {"delete_pattern": AsyncMock(return_value=0)})()

    async def get_backend():
        return backend

    monkeypatch.setattr(cache, "get_cache_backend", get_backend)

    await cache.CacheInvalidator._delete_patterns(
        ["offer:7", "offer:list:*", "query_cache:advertiser:list:*"]
    )

    assert [call.args[0] for call in backend.delete_pattern.await_args_list] == [
        "query_cache:offer:7",
        "query_cache:offer:list:*",
        "query_cache:advertiser:list:*",
    ]


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("offer:7", "query_cache:offer:7"),
        ("offer:list:*", "query_cache:offer:list:*"),
        ("query_cache:offer:list:*", "query_cache:offer:list:*"),
        ("", "query_cache:"),
    ],
)
def test_query_cache_pattern_normalizes_namespace_once(pattern, expected):
    assert cache.CacheInvalidator._query_cache_pattern(pattern) == expected
