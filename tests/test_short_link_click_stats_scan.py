"""短链接点击计数监控必须在 SCAN 故障时 fail-closed。"""
import pytest

from app.api_v1.tracking.short_links import _scan_click_counter_keys_for_stats


@pytest.mark.asyncio
async def test_click_stats_scan_failure_keeps_partial_keys_without_blocking_keys():
    class BrokenScanRedis:
        def __init__(self):
            self.calls = 0
            self.keys_called = False

        async def scan(self, cursor, match, count):
            self.calls += 1
            if self.calls == 1:
                return 1, [b"short_link:click_counter:a"]
            raise OSError("simulated redis scan failure")

        async def keys(self, pattern):
            self.keys_called = True
            raise AssertionError("monitoring must never issue blocking KEYS")

    redis = BrokenScanRedis()
    keys, complete, error = await _scan_click_counter_keys_for_stats(
        redis, "short_link:click_counter:*", max_iterations=10
    )

    assert keys == [b"short_link:click_counter:a"]
    assert complete is False
    assert error == "OSError"
    assert redis.keys_called is False


@pytest.mark.asyncio
async def test_click_stats_scan_marks_iteration_limit_as_incomplete():
    class LongScanRedis:
        async def scan(self, cursor, match, count):
            return cursor + 1, [f"short_link:click_counter:{cursor}"]

        async def keys(self, pattern):
            raise AssertionError("monitoring must never issue blocking KEYS")

    keys, complete, error = await _scan_click_counter_keys_for_stats(
        LongScanRedis(), "short_link:click_counter:*", max_iterations=2
    )

    assert len(keys) == 2
    assert complete is False
    assert error == "max_iterations"
