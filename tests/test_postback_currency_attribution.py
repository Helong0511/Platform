import pytest

from app.core.postback.transformers.normalizer import DataNormalizer
from app.core.postback.bft_handler import BftPostbackHandler
from app.models.postback import PostbackConversion, PendingPostbackConversion
from app.models.deduction import ConversionDeductionLog
from app.core.deduction.deduction_manager import DeductionResult
from scripts.backfill_currency_attribution import extract_currency


@pytest.mark.parametrize(
    ("raw_data", "expected_currency", "expected_source"),
    [
        ({"payout": "12.34", "currency_code": "cny"}, "CNY", "upstream_field:currency_code"),
        ({"payout": "12.34"}, "USD", "system_fallback_usd"),
        ({"payout": "12.34", "currency": "   "}, "USD", "system_fallback_usd"),
    ],
)
def test_generic_postback_currency_source_attribution(raw_data, expected_currency, expected_source):
    normalized = DataNormalizer.normalize(raw_data, "generic")
    assert normalized["currency"] == expected_currency
    assert normalized["currency_source"] == expected_source


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_data", "expected_currency", "expected_source"),
    [
        ({"payout": "12.34", "currencyCode": "eur"}, "EUR", "upstream_field:currencyCode"),
        ({"payout": "12.34"}, "USD", "system_fallback_usd"),
    ],
)
async def test_bft_postback_currency_source_attribution(raw_data, expected_currency, expected_source):
    normalized = await BftPostbackHandler().normalize(raw_data)
    assert normalized["currency"] == expected_currency
    assert normalized["currency_source"] == expected_source


def test_generic_postback_rejects_invalid_iso_currency_instead_of_fallback():
    with pytest.raises(ValueError):
        DataNormalizer.normalize({"payout": "12.34", "currency": "ZZZ"}, "generic")


def test_postback_conversion_persists_currency_and_source_defaults():
    currency = PostbackConversion.__table__.c.currency
    source = PostbackConversion.__table__.c.currency_source
    assert currency.default.arg == "USD"
    assert str(currency.server_default.arg).strip("'") == "USD"
    assert source.default.arg == "system_fallback_usd"
    assert str(source.server_default.arg).strip("'") == "system_fallback_usd"


@pytest.mark.asyncio
async def test_bft_postback_rejects_invalid_iso_currency_instead_of_fallback():
    with pytest.raises(ValueError):
        await BftPostbackHandler().normalize({"payout": "12.34", "currency": "ZZZ"})


def test_pending_postback_conversion_persists_currency_and_source_defaults():
    currency = PendingPostbackConversion.__table__.c.currency
    source = PendingPostbackConversion.__table__.c.currency_source
    assert currency.default.arg == "USD"
    assert str(currency.server_default.arg).strip("'") == "USD"
    assert source.default.arg == "system_fallback_usd"
    assert str(source.server_default.arg).strip("'") == "system_fallback_usd"


@pytest.mark.parametrize(
    ("raw_data", "expected_currency", "expected_source"),
    [
        ('{"currency":"cny"}', "CNY", "upstream_field:currency"),
        ('{"currency_code":" eur "}', "EUR", "upstream_field:currency_code"),
        ('{"currencyCode":"JPY"}', "JPY", "upstream_field:currencyCode"),
        ('{"_payload":{"currency":"gbp"}}', "GBP", "upstream_field:currency"),
        ('{"payout":"10"}', "USD", "system_fallback_usd"),
        ("not-json", "USD", "system_fallback_usd"),
    ],
)
def test_historical_currency_backfill_extracts_source_without_guessing(
    raw_data, expected_currency, expected_source
):
    assert extract_currency(raw_data) == (expected_currency, expected_source)


def test_conversion_deduction_log_persists_currency_defaults():
    currency = ConversionDeductionLog.__table__.c.currency
    source = ConversionDeductionLog.__table__.c.currency_source
    assert currency.default.arg == "USD"
    assert str(currency.server_default.arg).strip("'") == "USD"
    assert source.default.arg == "system_fallback_usd"
    assert str(source.server_default.arg).strip("'") == "system_fallback_usd"


def test_deduction_result_serializes_currency_attribution():
    result = DeductionResult(currency="CNY", currency_source="upstream_field:currency_code")
    data = result.to_dict()
    assert data["currency"] == "CNY"
    assert data["currency_source"] == "upstream_field:currency_code"
