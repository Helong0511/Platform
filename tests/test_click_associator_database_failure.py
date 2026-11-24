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

def test_token_database_identity_conflict_is_rejected():
    db_association = {
        "click_id": "click-123",
        "offer_id": 10,
        "publisher_id": 20,
        "advertiser_id": 30,
        "short_link_id": 40,
        "url_params": {},
    }
    token_association = {
        "click_id": "click-123",
        "offer_id": 11,
        "publisher_id": 20,
        "advertiser_id": 30,
        "short_link_id": 40,
        "url_params": {},
    }

    with pytest.raises(ValueError, match="identity conflict"):
        ClickAssociator._merge_token_and_db_association(
            db_association, token_association
        )


def test_matching_token_database_identity_keeps_database_snapshot():
    db_association = {
        "click_id": "click-123",
        "offer_id": 10,
        "publisher_id": 20,
        "advertiser_id": 30,
        "short_link_id": 40,
        "client_id": 99,
        "url_params": {},
    }
    token_association = {
        "click_id": "click-123",
        "offer_id": 10,
        "publisher_id": 20,
        "advertiser_id": 30,
        "short_link_id": 40,
        "client_id": None,
        "url_params": {},
    }

    merged = ClickAssociator._merge_token_and_db_association(
        db_association, token_association
    )

    assert merged["offer_id"] == 10
    assert merged["publisher_id"] == 20
    assert merged["advertiser_id"] == 30
    assert merged["short_link_id"] == 40
    assert merged["client_id"] == 99

@pytest.mark.parametrize(
    "identity_field",
    ["click_id", "offer_id", "publisher_id", "advertiser_id", "short_link_id"],
)
def test_each_click_identity_field_mismatch_is_rejected(identity_field):
    db_association = {
        "click_id": "click-123",
        "offer_id": 10,
        "publisher_id": 20,
        "advertiser_id": 30,
        "short_link_id": 40,
        "url_params": {},
    }
    token_association = dict(db_association)
    token_association[identity_field] = (
        "different-click" if identity_field == "click_id" else db_association[identity_field] + 1
    )

    with pytest.raises(ValueError, match="identity conflict"):
        ClickAssociator._merge_token_and_db_association(
            db_association, token_association
        )
