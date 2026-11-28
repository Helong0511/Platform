from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.postback.processor import _resolve_cloak_postback_purchase_currency
from app.models.postback import CloakConfig
from app.schemas.cloak import CloakConfigCreate, CloakConfigUpdate


def test_all_cloak_currency_columns_have_usd_orm_and_database_defaults():
    for field in ("report_currency", "load_report_currency", "postback_report_currency"):
        column = CloakConfig.__table__.c[field]
        assert column.default.arg == "USD"
        assert str(column.server_default.arg).strip("'") == "USD"
        assert column.nullable is True
    assert CloakConfig.__table__.c.report_currency_source.default.arg == "system_fallback_usd"
    assert CloakConfig.__table__.c.load_report_currency_source.default.arg == "system_fallback_usd"
    assert CloakConfig.__table__.c.postback_report_currency_source.default.arg == "system_fallback_usd"


def test_new_cloak_schema_defaults_all_purchase_phases_to_usd():
    config = CloakConfigCreate(
        cloak_name="ci-currency-default",
        pixel_id="123456789",
        access_token="test-token",
    )
    assert config.report_currency == "USD"
    assert config.load_report_currency == "USD"
    assert config.postback_report_currency == "USD"


def test_cloak_update_keeps_omitted_currency_as_no_change():
    update = CloakConfigUpdate()
    assert update.report_currency is None
    assert update.load_report_currency is None
    assert update.postback_report_currency is None


@pytest.mark.parametrize("field", ["report_currency", "load_report_currency", "postback_report_currency"])
def test_cloak_create_rejects_non_iso_currency(field):
    with pytest.raises(ValidationError):
        CloakConfigCreate(
            cloak_name="ci-invalid-currency",
            pixel_id="123456789",
            access_token="test-token",
            **{field: "ZZZ"},
        )

@pytest.mark.parametrize("field", ["report_currency", "load_report_currency", "postback_report_currency"])
def test_cloak_update_rejects_non_iso_currency(field):
    with pytest.raises(ValidationError):
        CloakConfigUpdate(**{field: "ZZZ"})


def test_dynamic_cloak_purchase_inherits_upstream_currency_when_config_uses_usd_fallback():
    currency, source = _resolve_cloak_postback_purchase_currency(
        upstream_currency="EUR",
        upstream_currency_source="upstream_field:currency",
        configured_currency="USD",
        configured_currency_source="system_fallback_usd",
        fixed_amount=None,
    )
    assert currency == "EUR"
    assert source == "upstream_field:currency"


def test_dynamic_cloak_purchase_rejects_explicit_currency_mismatch():
    with pytest.raises(ValueError, match="不一致"):
        _resolve_cloak_postback_purchase_currency(
            upstream_currency="EUR",
            upstream_currency_source="upstream_field:currency",
            configured_currency="USD",
            configured_currency_source="manual_override",
            fixed_amount=None,
        )


def test_fixed_cloak_purchase_uses_configured_currency_or_usd_fallback():
    currency, source = _resolve_cloak_postback_purchase_currency(
        upstream_currency="EUR",
        upstream_currency_source="upstream_field:currency",
        configured_currency="USD",
        configured_currency_source="system_fallback_usd",
        fixed_amount=Decimal("9.99"),
    )
    assert currency == "USD"
    assert source == "system_fallback_usd"
