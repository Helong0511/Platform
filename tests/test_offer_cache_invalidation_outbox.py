"""Offer 缓存失效 Outbox 的事务边界测试。"""
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import OfferCacheInvalidationOutbox
from app.services.offer_cache_invalidation_outbox import (
    enqueue_offer_cache_invalidation,
)


@pytest.mark.asyncio
async def test_offer_invalidation_events_rollback_with_business_transaction():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(OfferCacheInvalidationOutbox.__table__.create)
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async with factory() as session:
            await enqueue_offer_cache_invalidation(session, 41)
            count = await session.scalar(
                select(func.count()).select_from(OfferCacheInvalidationOutbox)
            )
            assert count == 2
            # 登记函数不得提交；业务回滚必须连同两个失效事件一起回滚。
            await session.rollback()

        async with factory() as session:
            count = await session.scalar(
                select(func.count()).select_from(OfferCacheInvalidationOutbox)
            )
            assert count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_offer_invalidation_commit_persists_first_and_second_pass():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(OfferCacheInvalidationOutbox.__table__.create)
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async with factory() as session:
            await enqueue_offer_cache_invalidation(session, 42)
            await enqueue_offer_cache_invalidation(session, 43)
            await session.commit()

        async with factory() as session:
            events = list(
                (
                    await session.scalars(
                        select(OfferCacheInvalidationOutbox).order_by(
                            OfferCacheInvalidationOutbox.run_at
                        )
                    )
                ).all()
            )
            assert len(events) == 4
            assert {event.offer_id for event in events} == {42, 43}
            assert {event.phase for event in events} == {"first", "second"}
            assert all(event.status == "pending" for event in events)
            pairs = {
                offer_id: [event for event in events if event.offer_id == offer_id]
                for offer_id in (42, 43)
            }
            for pair in pairs.values():
                assert len(pair) == 2
                assert {event.phase for event in pair} == {"first", "second"}
                assert pair[0].group_key == pair[1].group_key
                assert pair[0].event_key != pair[1].event_key
                first = next(event for event in pair if event.phase == "first")
                second = next(event for event in pair if event.phase == "second")
                assert second.run_at - first.run_at >= timedelta(seconds=1)
            assert pairs[42][0].group_key != pairs[43][0].group_key
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("offer_id", [0, -1, True, 1.5, "42"])
async def test_offer_invalidation_rejects_invalid_ids(offer_id):
    class NoWriteSession:
        def add_all(self, events):
            raise AssertionError("invalid offer id must be rejected before enqueue")

    with pytest.raises(ValueError, match="offer_id"):
        await enqueue_offer_cache_invalidation(NoWriteSession(), offer_id)
