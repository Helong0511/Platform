"""扣量配置存在历史重复记录时，查询结果必须保持稳定。"""
from types import SimpleNamespace

import pytest

from app.core.deduction.deduction_cache import DeductionConfigCache
from app.core.deduction.deduction_manager import DeductionManager


class _Scalars:
    def first(self):
        return None


class _Result:
    def scalars(self):
        return _Scalars()


class _CaptureSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _Result()


def _assert_stable_order(statement):
    clauses = list(statement._order_by_clauses)
    assert len(clauses) == 2
    assert "priority DESC" in str(clauses[0])
    assert "id ASC" in str(clauses[1])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "target_id"),
    [
        ("_find_offer_config", 101),
        ("_find_advertiser_config", 202),
        ("_find_publisher_config", 303),
    ],
)
async def test_manager_uses_id_as_stable_tie_breaker(method_name, target_id):
    session = _CaptureSession()
    manager = DeductionManager(session)

    await getattr(manager, method_name)(target_id)

    _assert_stable_order(session.statement)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("level", "target_id"),
    [("offer", 101), ("advertiser", 202), ("publisher", 303)],
)
async def test_cache_query_uses_id_as_stable_tie_breaker(level, target_id):
    session = _CaptureSession()
    cache = DeductionConfigCache(session)

    await cache._load_from_db(level, target_id)

    _assert_stable_order(session.statement)
