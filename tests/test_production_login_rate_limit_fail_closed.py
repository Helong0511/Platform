"""生产登录限流在 Redis 不可用时必须 fail-closed。"""
import pytest

from app.core.middleware import _should_fail_closed_rate_limit


@pytest.mark.parametrize(
    ("is_production", "bucket", "redis_counted", "expected"),
    [
        (True, "login", False, True),
        (True, "login", True, False),
        (False, "login", False, False),
        (True, "api", False, False),
        (True, "client-open-api", False, False),
    ],
)
def test_production_login_rate_limit_fails_closed_only_without_redis(
    is_production, bucket, redis_counted, expected
):
    assert _should_fail_closed_rate_limit(
        is_production=is_production,
        bucket=bucket,
        redis_counted=redis_counted,
    ) is expected
