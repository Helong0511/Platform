"""Click 归因数据库故障必须与记录未命中区分。"""
import pytest

from app.core.postback.transformers.click_associator import ClickAssociator


class _UnavailableSession:
    def __init__(self):
        self.execute_calls = 0
        self.rollback_calls = 0

    async def execute(self, statement):
        self.execute_calls += 1
        raise RuntimeError("database unavailable")

    async def rollback(self):
        self.rollback_calls += 1


@pytest.mark.asyncio
async def test_click_lookup_database_error_rolls_back_and_propagates(monkeypatch):
    session = _UnavailableSession()

    async def no_sleep(_delay):
        raise AssertionError("database errors must not be retried on the same session")

    monkeypatch.setattr("app.core.postback.transformers.click_associator.asyncio.sleep", no_sleep)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await ClickAssociator.associate_from_db("click-123", session)

    assert session.execute_calls == 1
    assert session.rollback_calls == 1

@pytest.mark.asyncio
async def test_token_enrichment_database_error_rolls_back_and_propagates():
    session = _UnavailableSession()
    association = {
        "_from_token": True,
        "click_id": "click-123",
        "publisher_id": 7,
        "offer_id": None,
        "advertiser_id": None,
    }

    with pytest.raises(RuntimeError, match="database unavailable"):
        await ClickAssociator._enrich_association(association, session)

    assert session.execute_calls == 1
    assert session.rollback_calls == 1
    assert "publisher" not in association
