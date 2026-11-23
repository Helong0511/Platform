"""Postback event_name must use one non-NULL canonical value across ingest and approval."""
from types import SimpleNamespace

import pytest

from app.core.postback.transformers.normalizer import (
    DataNormalizer,
    normalize_event_name,
)
from app.core.postback.validators.duplicate_checker import DuplicateChecker
from app.services.cpl.postback_pending_service import PostbackPendingService


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "default"),
        ("", "default"),
        ("   ", "default"),
        (" purchase ", "purchase"),
        ("install", "install"),
    ],
)
def test_normalize_event_name_maps_missing_and_blank_values(value, expected):
    assert normalize_event_name(value) == expected


def test_data_normalizer_never_emits_null_or_blank_event_name():
    for raw_value in (None, "", "  "):
        normalized = DataNormalizer.normalize(
            {"conversion_id": "conversion-1", "event_name": raw_value},
            "partner_a",
        )
        assert normalized["event_name"] == "default"


class _ExecuteResult:
    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def first(self):
        return None


class _QueryCaptureDB:
    def __init__(self):
        self.statement = None
        self.added = []

    async def execute(self, statement):
        self.statement = statement
        return _ExecuteResult()

    def add(self, value):
        self.added.append(value)


@pytest.mark.asyncio
async def test_duplicate_checker_queries_default_for_missing_event_name():
    db = _QueryCaptureDB()

    duplicate = await DuplicateChecker.is_duplicate(
        platform="partner_a",
        conversion_id="conversion-1",
        event_name=None,
        db=db,
    )

    assert duplicate is False
    assert "default" in db.statement.compile().params.values()


@pytest.mark.asyncio
async def test_pending_approval_normalizes_legacy_null_before_lookup_and_insert(monkeypatch):
    service = PostbackPendingService()
    pending = SimpleNamespace(
        id=17,
        platform="partner_a",
        conversion_id="conversion-legacy",
        event_name=None,
        click_id=None,
        click_time=None,
        event_value=None,
        original_payout=None,
        payout=None,
        devad_id=None,
        os=None,
        carrier=None,
        ip=None,
        gid=None,
        product_id=None,
        client_id=None,
        raw_data=None,
        status="pending",
        approved_at=None,
    )
    db = _QueryCaptureDB()

    existing_id = await service._pending_conversion_exists(pending, db)
    assert existing_id is None
    assert pending.event_name == "default"
    assert "default" in db.statement.compile().params.values()

    async def no_click_association(_pending, _db):
        return None

    monkeypatch.setattr(service, "_resolve_click_assoc", no_click_association)
    conversion = await service._create_conversion_from_pending(pending, db)

    assert conversion.event_name == "default"
    assert pending.event_name == "default"
    assert pending.status == "approved"
    assert db.added == [conversion]
