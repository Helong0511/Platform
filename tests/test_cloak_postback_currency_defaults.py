from app.models.postback import CloakConfig
from app.schemas.cloak import CloakConfigCreate, CloakConfigUpdate


def test_postback_currency_has_no_orm_or_database_default():
    column = CloakConfig.__table__.c.postback_report_currency
    assert column.default is None
    assert column.server_default is None
    assert column.nullable is True


def test_new_cloak_schema_keeps_unconfigured_postback_currency_null():
    config = CloakConfigCreate(
        cloak_name="ci-currency-default",
        pixel_id="123456789",
        access_token="test-token",
    )
    assert config.postback_report_currency is None


def test_cloak_update_does_not_invent_postback_currency():
    update = CloakConfigUpdate()
    assert update.postback_report_currency is None
