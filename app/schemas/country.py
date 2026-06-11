"""国家信息 Schema：对应 countries 表，供系统服务维护接口使用。"""
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import BaseSchema, IDBaseSchema


_ALPHA2_PATTERN = re.compile(r"^[A-Za-z]{2}$")
_ALPHA3_PATTERN = re.compile(r"^[A-Za-z]{3}$")
_NUMERIC_PATTERN = re.compile(r"^\d{3}$")


def _normalize_alpha2(value: str) -> str:
    code = value.strip().upper()
    if not _ALPHA2_PATTERN.match(code):
        raise ValueError("国家二字代码必须为 2 位字母（ISO 3166-1 alpha-2）")
    return code


def _normalize_alpha3(value: str) -> str:
    code = value.strip().upper()
    if not _ALPHA3_PATTERN.match(code):
        raise ValueError("国家三字代码必须为 3 位字母（ISO 3166-1 alpha-3）")
    return code


def _normalize_numeric(value: str) -> str:
    code = value.strip()
    if not _NUMERIC_PATTERN.match(code):
        raise ValueError("国家数字代码必须为 3 位数字（ISO 3166-1 numeric）")
    return code


class CountryBase(BaseSchema):
    """国家信息公共字段。"""

    alpha_2_code: str = Field(..., min_length=2, max_length=2, description="国家二字代码")
    alpha_3_code: str = Field(..., min_length=3, max_length=3, description="国家三字代码")
    numeric_code: str = Field(..., min_length=3, max_length=3, description="国家数字代码")
    country_name_zh: str = Field(..., min_length=1, max_length=100, description="国家中文名称")
    country_name_en: str = Field(..., min_length=1, max_length=100, description="国家英文名称")
    official_name_zh: Optional[str] = Field(None, max_length=150, description="官方中文名称")
    official_name_en: Optional[str] = Field(None, max_length=150, description="官方英文名称")
    independent_status: bool = Field(True, description="是否独立国家")
    continent: Optional[str] = Field(None, max_length=50, description="所属大洲")
    subregion: Optional[str] = Field(None, max_length=50, description="所属地区")

    @field_validator("alpha_2_code")
    @classmethod
    def validate_alpha_2(cls, value: str) -> str:
        return _normalize_alpha2(value)

    @field_validator("alpha_3_code")
    @classmethod
    def validate_alpha_3(cls, value: str) -> str:
        return _normalize_alpha3(value)

    @field_validator("numeric_code")
    @classmethod
    def validate_numeric(cls, value: str) -> str:
        return _normalize_numeric(value)

    @field_validator(
        "country_name_zh",
        "country_name_en",
        "official_name_zh",
        "official_name_en",
        "continent",
        "subregion",
    )
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class CountryCreate(CountryBase):
    """创建国家请求体。"""

    pass


class CountryUpdate(BaseModel):
    """更新国家请求体：仅提交的字段参与更新。"""

    alpha_2_code: Optional[str] = Field(None, min_length=2, max_length=2, description="国家二字代码")
    alpha_3_code: Optional[str] = Field(None, min_length=3, max_length=3, description="国家三字代码")
    numeric_code: Optional[str] = Field(None, min_length=3, max_length=3, description="国家数字代码")
    country_name_zh: Optional[str] = Field(None, min_length=1, max_length=100, description="国家中文名称")
    country_name_en: Optional[str] = Field(None, min_length=1, max_length=100, description="国家英文名称")
    official_name_zh: Optional[str] = Field(None, max_length=150, description="官方中文名称")
    official_name_en: Optional[str] = Field(None, max_length=150, description="官方英文名称")
    independent_status: Optional[bool] = Field(None, description="是否独立国家")
    continent: Optional[str] = Field(None, max_length=50, description="所属大洲")
    subregion: Optional[str] = Field(None, max_length=50, description="所属地区")

    @field_validator("alpha_2_code")
    @classmethod
    def validate_alpha_2(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_alpha2(value)

    @field_validator("alpha_3_code")
    @classmethod
    def validate_alpha_3(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_alpha3(value)

    @field_validator("numeric_code")
    @classmethod
    def validate_numeric(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_numeric(value)

    @field_validator(
        "country_name_zh",
        "country_name_en",
        "official_name_zh",
        "official_name_en",
        "continent",
        "subregion",
    )
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class CountryResponse(CountryBase, IDBaseSchema):
    """国家信息 API 响应。"""

    pass


class UnrecognizedCountryCodeItem(BaseSchema):
    """业务数据中出现但未在 countries 表登记的国家代码。"""

    country_code: str = Field(..., description="未识别的国家代码")
    ad_data_count: int = Field(0, description="广告数据中出现次数")
    tb_search_data_count: int = Field(0, description="TB搜索数据中出现次数")
    ad_data_archive_count: int = Field(0, description="广告数据归档中出现次数")
    total_count: int = Field(0, description="总出现次数")
    sources: list[str] = Field(default_factory=list, description="数据来源表标识")
    is_valid_alpha2: bool = Field(False, description="是否为合法 ISO 二字代码格式，可直接添加")
