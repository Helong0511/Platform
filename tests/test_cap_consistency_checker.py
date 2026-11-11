"""Cap consistency checks must fail explicitly when Redis state cannot be read."""
import pytest

from app.core.cap import consistency_checker


class _Result:
    def scalars(self):
        return self

    def all(self):
        return []


class _DB:
    async def execute(self, statement):
        return _Result()


@pytest.mark.asyncio
async def test_consistency_check_does_not_report_success_when_redis_is_unavailable(monkeypatch):
    async def unavailable_redis():
        return None

    monkeypatch.setattr(consistency_checker, "get_redis_client", unavailable_redis)

    with pytest.raises(RuntimeError, match="Redis 不可用"):
        await consistency_checker.check_cap_consistency(_DB())
