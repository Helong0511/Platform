"""Postback event_name must use one non-NULL canonical value across ingest and approval."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.postback.transformers.normalizer import DataNormalizer
from app.core.postback import pipeline as postback_pipeline
from app.core.postback_event_name import normalize_event_name
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
    def __init__(self, existing=None):
        self.existing = existing

    def scalar_one_or_none(self):
        return self.existing

    def scalars(self):
        return self

    def first(self):
        return None


class _NestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _QueryCaptureDB:
    def __init__(self, results=None):
        self.statement = None
        self.statements = []
        self.added = []
        self.results = list(results or [_ExecuteResult(), _ExecuteResult()])

    async def execute(self, statement):
        self.statement = statement
        self.statements.append(statement)
        if self.results:
            return self.results.pop(0)
        return _ExecuteResult()

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None

    async def delete(self, value):
        self.deleted = value

    def begin_nested(self):
        return _NestedTransaction()


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
    assert len(db.added) == 1
    assert db.added[0].event_name == "default"
    assert len(db.statements) == 2


@pytest.mark.asyncio
async def test_duplicate_checker_rejects_existing_durable_receipt(monkeypatch):
    from sqlalchemy.exc import IntegrityError

    class _ReceiptConflictDB(_QueryCaptureDB):
        async def flush(self):
            raise IntegrityError("INSERT", {}, Exception("duplicate receipt"))

    db = _ReceiptConflictDB(results=[_ExecuteResult()])
    duplicate = await DuplicateChecker.is_duplicate(
        platform="partner_a",
        conversion_id="conversion-duplicate",
        event_name="install",
        db=db,
    )

    assert duplicate is True
    assert len(db.statements) == 1


@pytest.mark.asyncio
async def test_duplicate_checker_closes_race_with_committed_normal_conversion():
    db = _QueryCaptureDB(results=[_ExecuteResult(), _ExecuteResult(existing=91)])
    duplicate = await DuplicateChecker.is_duplicate(
        platform="partner_a",
        conversion_id="conversion-race",
        event_name="purchase",
        db=db,
    )

    assert duplicate is True
    assert len(db.statements) == 2
    assert "FOR UPDATE" in str(db.statements[1]).upper()
    assert db.deleted is db.added[0]


@pytest.mark.asyncio
async def test_release_receipt_normalizes_event_name_and_targets_receipt_table():
    db = _QueryCaptureDB()
    await DuplicateChecker.release_receipt(
        platform="partner_a",
        conversion_id="conversion-1",
        event_name=None,
        db=db,
    )

    sql = str(db.statement)
    assert "postback_event_receipts" in sql
    assert "default" in db.statement.compile().params.values()


def test_processor_releases_temporary_receipt_only_after_formal_conversion_save():
    processor_source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "core"
        / "postback"
        / "processor.py"
    ).read_text(encoding="utf-8")

    skip_branch = processor_source.index("if skip_save_and_forward:")
    save_conversion = processor_source.index(
        "conversion = await step_save_conversion(pipe_ctx)"
    )
    release_receipt = processor_source.index(
        "await step_release_event_receipt(pipe_ctx)"
    )

    # 被扣量分支提前提交并返回；只有正式转化成功写入后才释放临时收据。
    assert skip_branch < save_conversion < release_receipt


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
        currency="USD",
        currency_source="system_fallback_usd",
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



@pytest.mark.asyncio
async def test_pipeline_passes_canonical_event_name_into_deduction_identity(monkeypatch):
    from decimal import Decimal
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        postback_pipeline.ConversionSaver,
        "resolve_trusted_attribution",
        AsyncMock(return_value=(12, 34)),
    )
    calculate = AsyncMock(return_value=(Decimal("10.00"), None, False))
    monkeypatch.setattr(postback_pipeline.DiscountChecker, "calculate", calculate)

    ctx = SimpleNamespace(
        normalized_data={
            "payout": "10.00",
            "click_id": "click-1",
            "conversion_id": "conversion-1",
            "event_name": "   ",
            "event_identity_verified": True,
        },
        click_association={
            "offer_id": 7,
            "publisher_id": 8,
            "advertiser_id": 9,
        },
        platform="partner_a",
        db=object(),
        trusted_client_id=None,
        trusted_product_id=None,
        trusted_attribution_resolved=False,
        final_payout=Decimal("0"),
        skip_save_and_forward=False,
    )

    await postback_pipeline.step_apply_discount(ctx)

    assert calculate.await_args.kwargs["event_identity"] == {
        "platform": "partner_a",
        "conversion_id": "conversion-1",
        "event_name": "default",
    }
