"""Offer PO 币种使用 ISO 4217，并在缺省时明确兜底 USD。"""
import pytest
from pydantic import ValidationError

from app.models.cpl import Offer
from app.schemas.cpl.offer import OfferCreate, OfferUpdate


def test_offer_create_defaults_currency_to_usd():
    payload = OfferCreate(offer_name="currency-test", advertiser_id=1)
    assert payload.payout_currency == "USD"


@pytest.mark.parametrize("currency", ["ZZZ", "ABC", "XTS", "XXX", "XAU"])
def test_offer_create_rejects_non_settlement_currency(currency):
    with pytest.raises(ValidationError):
        OfferCreate(offer_name="currency-test", advertiser_id=1, payout_currency=currency)


def test_offer_update_explicit_null_uses_usd_fallback():
    payload = OfferUpdate(payout_currency=None)
    assert payload.payout_currency == "USD"


def test_offer_model_persists_currency_and_source_defaults():
    assert Offer.__table__.c.payout_currency.default.arg == "USD"
    assert str(Offer.__table__.c.payout_currency.server_default.arg).strip("'") == "USD"
    assert Offer.__table__.c.payout_currency_source.default.arg == "system_fallback_usd"
    assert str(Offer.__table__.c.payout_currency_source.server_default.arg).strip("'") == "system_fallback_usd"
