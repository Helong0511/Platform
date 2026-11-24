"""点击队列批量落库必须保留点击时客户归属快照。"""
from __future__ import annotations

import pytest

from app.scheduler_module.tasks import clicks_batch_processor


class _Result:
    def all(self):
        return []


class _FakeSession:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result()


@pytest.mark.asyncio
async def test_batch_insert_preserves_click_time_client_snapshot():
    db = _FakeSession()

    inserted, duplicates = await clicks_batch_processor._batch_insert_clicks(
        db,
        [
            {
                "click_id": "snapshot-click-1",
                "offer_id": 10,
                "publisher_id": 20,
                "client_id": 30,
                "advertiser_id": 40,
                "click_time": "2026-11-24T10:00:00",
            }
        ],
    )

    assert (inserted, duplicates) == (1, 0)
    assert len(db.statements) == 2
    insert_params = db.statements[1].compile().params
    assert any(
        key.startswith("client_id") and value == 30
        for key, value in insert_params.items()
    )
