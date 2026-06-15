"""国家别名 Schema 校验测试。"""
import pytest
from pydantic import ValidationError

from app.schemas.country import CountryAliasCreate


def test_country_alias_create_strips_alias_name():
    data = CountryAliasCreate(alias_name="  U.S. Virgin Islands  ", alpha_2_code="vi")
    assert data.alias_name == "U.S. Virgin Islands"
    assert data.alpha_2_code == "VI"


def test_country_alias_create_rejects_whitespace_only_alias_name():
    with pytest.raises(ValidationError):
        CountryAliasCreate(alias_name="   ", alpha_2_code="VI")


def test_country_alias_create_blank_remark_becomes_none():
    data = CountryAliasCreate(alias_name="Test", alpha_2_code="VI", remark="   ")
    assert data.remark is None
