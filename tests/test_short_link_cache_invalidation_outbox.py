"""短链接缓存失效 Outbox 的事务与精确键测试。"""
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import ShortLinkCacheInvalidationOutbox
from app.services.short_link_cache_invalidation_outbox import (
    enqueue_short_link_cache_invalidation,
)


@pytest.mark.asyncio
async def test_short_link_invalidation_events_rollback_with_business_transaction():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(ShortLinkCacheInvalidationOutbox.__table__.create)
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async with factory() as session:
            await enqueue_short_link_cache_invalidation(session, "Ab_123-x")
            count = await session.scalar(
                select(func.count()).select_from(ShortLinkCacheInvalidationOutbox)
            )
            assert count == 2
            await session.rollback()

        async with factory() as session:
            count = await session.scalar(
                select(func.count()).select_from(ShortLinkCacheInvalidationOutbox)
            )
            assert count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_short_link_invalidation_commit_persists_two_independent_phases():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(ShortLinkCacheInvalidationOutbox.__table__.create)
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async with factory() as session:
            await enqueue_short_link_cache_invalidation(session, "a12345")
            await enqueue_short_link_cache_invalidation(session, "b12345")
            await session.commit()

        async with factory() as session:
            events = list(
                (
                    await session.scalars(
                        select(ShortLinkCacheInvalidationOutbox).order_by(
                            ShortLinkCacheInvalidationOutbox.run_at
                        )
                    )
                ).all()
            )
            assert len(events) == 4
            for code in ("a12345", "b12345"):
                pair = [event for event in events if event.short_code == code]
                assert {event.phase for event in pair} == {"first", "second"}
                assert len({event.group_key for event in pair}) == 1
                assert len({event.event_key for event in pair}) == 2
                first = next(event for event in pair if event.phase == "first")
                second = next(event for event in pair if event.phase == "second")
                assert second.run_at - first.run_at >= timedelta(seconds=1)
            assert all(event.status == "pending" for event in events)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("short_code", ["", "a/b", "a*", "中文", "a" * 21, None, 123])
async def test_short_link_invalidation_rejects_untrusted_short_codes(short_code):
    class NoWriteSession:
        def add_all(self, events):
            raise AssertionError("invalid short code must be rejected before enqueue")

    with pytest.raises(ValueError, match="short_code"):
        await enqueue_short_link_cache_invalidation(NoWriteSession(), short_code)


@pytest.mark.asyncio
@pytest.mark.parametrize("delay", [0, -1, 301, True, 1.5])
async def test_short_link_invalidation_rejects_invalid_second_pass_delay(delay):
    class NoWriteSession:
        def add_all(self, events):
            raise AssertionError("invalid delay must be rejected before enqueue")

    with pytest.raises(ValueError, match="second_pass_delay_seconds"):
        await enqueue_short_link_cache_invalidation(
            NoWriteSession(), "valid01", second_pass_delay_seconds=delay
        )
