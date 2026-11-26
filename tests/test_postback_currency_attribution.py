import pytest

from app.core.postback.transformers.normalizer import DataNormalizer
from app.core.postback.bft_handler import BftPostbackHandler


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
