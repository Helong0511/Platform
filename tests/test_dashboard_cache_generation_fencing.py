"""Dashboard 缓存必须受数据与权限 Generation 双重 fencing。"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.cache_invalidation_outbox import (
    CacheGenerationUnavailable,
    get_cache_generations,
)
from app.services import dashboard_service as dashboard_service_module
from app.services.dashboard_service import DashboardService, _build_dashboard_cache_key


@pytest.mark.asyncio
async def test_get_cache_generations_reads_both_namespaces_in_one_query():
    result = MagicMock()
    result.all.return_value = [("ad_data", 17), ("user_stats", 9)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    generations = await get_cache_generations(db, ("ad_data", "user_stats"))

    assert generations == {"ad_data": 17, "user_stats": 9}
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_cache_generations_fails_closed_when_namespace_is_missing():
    result = MagicMock()
    result.all.return_value = [("ad_data", 17)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(CacheGenerationUnavailable, match="user_stats"):
        await get_cache_generations(db, ("ad_data", "user_stats"))


@pytest.mark.parametrize(
    "changed",
    [
        {"ad_data": 18, "user_stats": 9},
        {"ad_data": 17, "user_stats": 10},
    ],
)
def test_dashboard_cache_key_changes_when_data_or_permission_generation_changes(
    changed,
):
    original = {"ad_data": 17, "user_stats": 9}

    old_key = _build_dashboard_cache_key("dashboard_stats", "month", 123, original)
    new_key = _build_dashboard_cache_key("dashboard_stats", "month", 123, changed)

    assert old_key != new_key


def test_dashboard_stats_and_trends_both_use_generation_fenced_keys():
    source = Path("app/services/dashboard_service.py").read_text(encoding="utf-8")

    assert source.count(
        'get_cache_generations(self.db, ("ad_data", "user_stats"))'
    ) == 2
    assert source.count("_build_dashboard_cache_key(") == 3  # helper + stats + trends
    assert source.count("get_or_set_single_flight(") == 2
    assert "get_cached(" not in source
    assert "set_cached(" not in source


def test_dashboard_permission_and_data_mutations_advance_fenced_namespaces():
    user_service = Path("app/services/user_service.py").read_text(encoding="utf-8")
    client_service = Path("app/services/client_service.py").read_text(encoding="utf-8")
    product_service = Path("app/services/product_service.py").read_text(encoding="utf-8")
    ad_data_update = Path(
        "app/services/ad_data/commands/update_command.py"
    ).read_text(encoding="utf-8")
    ad_data_delete = Path(
        "app/services/ad_data/commands/delete_command.py"
    ).read_text(encoding="utf-8")

    assert "await self.invalidate_user_stats_cache()" in user_service
    assert 'namespace="user_stats"' in user_service
    assert 'advance_cache_generation(self.db, namespace="user_stats")' in client_service
    assert "await advance_cache_generation(self.db)" in client_service
    assert "await advance_cache_generation(self.db)" in product_service
    assert "await advance_cache_generation(self.db)" in ad_data_update
    assert "await advance_cache_generation(self.db)" in ad_data_delete


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("public_method", "private_method", "payload"),
    [
        (
            "get_dashboard_stats",
            "_get_dashboard_stats_uncached",
            {"stats": [], "metrics": {}},
        ),
        (
            "get_trend_data",
            "_get_trend_data_uncached",
            {"dates": [], "series": []},
        ),
    ],
)
async def test_dashboard_cache_methods_use_single_flight(
    monkeypatch, public_method, private_method, payload
):
    from types import SimpleNamespace

    service = DashboardService(object())
    generations = {"ad_data": 17, "user_stats": 9}
    monkeypatch.setattr(
        dashboard_service_module,
        "get_cache_generations",
        AsyncMock(return_value=generations),
    )
    captured = {}

    async def fake_single_flight(cache_key, factory, **kwargs):
        captured["cache_key"] = cache_key
        captured["kwargs"] = kwargs
        return await factory()

    monkeypatch.setattr(
        dashboard_service_module,
        "get_or_set_single_flight",
        fake_single_flight,
    )
    builder = AsyncMock(return_value=payload)
    setattr(service, private_method, builder)
    current_user = SimpleNamespace(id=123)

    result = await getattr(service, public_method)("month", current_user)

    assert result == payload
    cache_name = (
        "dashboard_stats"
        if public_method == "get_dashboard_stats"
        else "dashboard_trends"
    )
    assert captured["cache_key"] == _build_dashboard_cache_key(
        cache_name, "month", 123, generations
    )
    assert captured["kwargs"]["ttl"] == 60
    assert captured["kwargs"]["key_prefix"] == "dashboard"
    assert captured["kwargs"]["wait_timeout"] == 45
    builder.assert_awaited_once_with("month", current_user)
