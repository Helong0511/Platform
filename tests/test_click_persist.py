"""click 落库策略。"""
import os
import sys

import pytest

os.environ.setdefault("UNIT_TEST", "1")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def test_skip_persist_when_token_on_and_not_explicit(monkeypatch):
    from app.core import config
    from app.core.tracking import click_persist

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.delenv("PERSIST_CLICKS_TO_DB", raising=False)
    assert click_persist.should_persist_clicks_to_db() is False


def test_persist_when_explicit_true(monkeypatch):
    from app.core.tracking import click_persist

    monkeypatch.setenv("PERSIST_CLICKS_TO_DB", "true")
    assert click_persist.should_persist_clicks_to_db() is True


def test_persist_true_overrides_tracking_token(monkeypatch):
    from app.core import config
    from app.core.tracking import click_persist

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.setenv("PERSIST_CLICKS_TO_DB", "true")
    assert click_persist.should_persist_clicks_to_db() is True


@pytest.mark.asyncio
async def test_enqueue_writes_when_persist_true_with_token(monkeypatch):
    from app.core import config
    from app.core.clicks_queue import enqueue_click, get_queue_length

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.setenv("PERSIST_CLICKS_TO_DB", "true")

    class _Redis:
        def __init__(self):
            self.items = []

        async def llen(self, _key):
            return len(self.items)

        async def rpush(self, _key, val):
            self.items.append(val)
            return len(self.items)

    fake = _Redis()

    async def _fake_redis():
        return fake

    monkeypatch.setattr("app.core.clicks_queue.get_redis_client", _fake_redis)
    ok = await enqueue_click({"click_id": "persist-override-test"})
    assert ok is True
    assert len(fake.items) == 1


@pytest.mark.asyncio
async def test_enqueue_skips_when_not_persist(monkeypatch):
    from app.core import config
    from app.core.clicks_queue import enqueue_click

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.delenv("PERSIST_CLICKS_TO_DB", raising=False)
    assert await enqueue_click({"click_id": "test-skip"}) is True


@pytest.mark.asyncio
async def test_process_clicks_queue_skips_when_not_persist(monkeypatch):
    from app.core import config
    from app.scheduler_module.tasks.clicks_batch_processor import process_clicks_queue

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.delenv("PERSIST_CLICKS_TO_DB", raising=False)
    result = await process_clicks_queue()
    assert result["skipped"] is True
    assert result["processed"] == 0


def test_dual_mode_token_plus_persist_true(monkeypatch):
    """令牌 + 强制写库：与生产 .env 双轨配置一致。"""
    from app.core import config
    from app.core.tracking import click_persist
    from app.core.tracking.click_token import resolve_click_from_token

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.setenv("PERSIST_CLICKS_TO_DB", "true")
    assert click_persist.should_persist_clicks_to_db() is True
    assert "追踪令牌" in click_persist.describe_click_persist_mode()

    from app.core.tracking.click_token import generate_click_id_unified

    cid = generate_click_id_unified(offer_id=1, publisher_id=2, for_short_link=True)
    assert resolve_click_from_token(cid) is not None


def test_describe_mode_explicit_false(monkeypatch):
    from app.core import config
    from app.core.tracking import click_persist

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.setenv("PERSIST_CLICKS_TO_DB", "false")
    assert click_persist.should_persist_clicks_to_db() is False
    assert "强制不写库" in click_persist.describe_click_persist_mode()


def test_archive_skip_when_token_and_empty_table(monkeypatch):
    from app.core import config
    from app.services.tracking.clicks_archive_service import ClicksArchiveService

    class _Db:
        pass

    svc = ClicksArchiveService()

    async def _count_zero(_db):
        return 0

    monkeypatch.setattr(config.settings, "USE_TRACKING_TOKEN", True, raising=False)
    monkeypatch.delenv("PERSIST_CLICKS_TO_DB", raising=False)
    monkeypatch.setattr(svc, "count_clicks", _count_zero)

    import asyncio

    assert asyncio.run(svc.should_skip_archive(_Db())) is True
