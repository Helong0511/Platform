"""Postback 转化租户归属必须来自服务器侧点击/渠道关联。"""
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.postback.savers.conversion_saver import ConversionSaver
from app.core.postback import pipeline as postback_pipeline


class FakeResult:
    def __init__(self, scalar):
        self.scalar = scalar

    def scalar_one_or_none(self):
        return self.scalar


class FakeDB:
    def __init__(self, verified_product_id=None):
        self.verified_product_id = verified_product_id
        self.execute_calls = 0
        self.added = None

    async def execute(self, statement):
        self.execute_calls += 1
        return FakeResult(self.verified_product_id)

    def add(self, value):
        self.added = value

    async def flush(self):
        self.added.id = 501

    async def refresh(self, value):
        return None


def _normalized_data():
    return {
        "platform": "bft",
        "conversion_id": "conversion-1",
        "click_id": "click-1",
        "event_name": "default",
        "event_value": Decimal("0.0000"),
        "payout": Decimal("1.0000"),
        "devad_id": None,
        "os": None,
        "carrier": None,
        "ip": None,
        "gid": None,
        "product_id": 100,
        "client_id": 99,
        "raw_data": {"client_id": 99, "product_id": 100},
    }


@pytest.mark.asyncio
async def test_conversion_client_and_product_come_from_verified_click_owner():
    db = FakeDB(verified_product_id=100)
    click_association = {
        "click_id": "click-1",
        "offer_id": 2,
        "publisher_id": 3,
        "advertiser_id": 4,
        "client_id": 12,
        "publisher": SimpleNamespace(client_id=12),
    }

    conversion = await ConversionSaver.save(
        normalized_data=_normalized_data(),
        click_association=click_association,
        final_payout=Decimal("1.0000"),
        conversion_status="approved",
        db=db,
    )

    assert conversion.client_id == 12
    assert conversion.product_id == 100
    assert db.execute_calls == 1
    stored_raw = json.loads(conversion.raw_data)
    assert stored_raw["client_id"] == 99  # 原始请求保留，便于审计
    assert stored_raw["_attribution"]["client_id"] == 12
    assert stored_raw["_attribution"]["product_id"] == 100


@pytest.mark.asyncio
async def test_unassociated_callback_cannot_assign_client_or_product_from_payload():
    db = FakeDB(verified_product_id=100)

    conversion = await ConversionSaver.save(
        normalized_data=_normalized_data(),
        click_association=None,
        final_payout=Decimal("1.0000"),
        conversion_status="approved",
        db=db,
    )

    assert conversion.client_id is None
    assert conversion.product_id is None
    assert db.execute_calls == 0


@pytest.mark.asyncio
async def test_product_from_another_client_is_not_attached_to_conversion():
    db = FakeDB(verified_product_id=None)
    click_association = {
        "click_id": "click-1",
        "offer_id": 2,
        "publisher_id": 3,
        "advertiser_id": 4,
        "client_id": 12,
        "publisher": SimpleNamespace(client_id=12),
    }

    conversion = await ConversionSaver.save(
        normalized_data=_normalized_data(),
        click_association=click_association,
        final_payout=Decimal("1.0000"),
        conversion_status="approved",
        db=db,
    )

    assert conversion.client_id == 12
    assert conversion.product_id is None



@pytest.mark.asyncio
async def test_discount_step_uses_trusted_tenant_attribution_not_callback_fields(monkeypatch):
    captured = {}

    async def resolve_trusted_attribution(**kwargs):
        return 12, 100

    async def fake_calculate(**kwargs):
        captured.update(kwargs)
        return Decimal("1.0000"), {"deducted": False}, False

    monkeypatch.setattr(
        ConversionSaver,
        "resolve_trusted_attribution",
        staticmethod(resolve_trusted_attribution),
    )
    monkeypatch.setattr(
        postback_pipeline.DiscountChecker,
        "calculate",
        staticmethod(fake_calculate),
    )

    context = postback_pipeline.PostbackPipelineContext(
        platform="bft",
        raw_data={},
        db=object(),
        normalized_data={
            "payout": Decimal("1.0000"),
            "client_id": 99,
            "product_id": 999,
            "click_id": "click-1",
        },
        click_association={
            "offer_id": 2,
            "publisher_id": 3,
            "advertiser_id": 4,
            "client_id": 12,
        },
    )

    await postback_pipeline.step_apply_discount(context)

    assert captured["client_id"] == 12
    assert captured["product_id"] == 100
    assert context.trusted_attribution_resolved is True
    assert context.trusted_client_id == 12
    assert context.trusted_product_id == 100
