"""淘宝搜索数据（TBSearchData）Schema。

按日期、产品、国家维度存储 redirects/searches/clicks 等投放侧指标。

说明：请求/响应 JSON 结构定义，供 FastAPI 校验与 OpenAPI 文档生成。"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.schemas.base import BaseSchema


class TBSearchDataBase(BaseSchema):
    """
    TB 搜索数据基础字段（日期 + 产品 + 国家维度指标）
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    date: date
    product_id: int
    product_name: str | None = None
    country_code: str | None = None
    country_name_zh: str | None = None
    redirects: int | None = Field(default=0, ge=0, le=2147483647)
    searches: int | None = Field(default=0, ge=0, le=2147483647)
    monetized: int | None = Field(default=0, ge=0, le=2147483647)
    clicks: int | None = Field(default=0, ge=0, le=2147483647)
    revenue: Decimal | None = Decimal('0')
    rpm: Decimal | None = Decimal('0')
    # 减扣前字段仅管理员填充；客户响应保持 None，避免对照出扣减
    revenue_before_deduct: Decimal | None = None
    rpm_before_deduct: Decimal | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_non_finite_amount_payload(cls, data):
        """在字段 Decimal 核心解析前拦截非有限金额，返回稳定中文错误。"""
        if not isinstance(data, dict):
            return data
        for field_name in (
            "revenue",
            "rpm",
            "revenue_before_deduct",
            "rpm_before_deduct",
        ):
            value = data.get(field_name)
            if value is None:
                continue
            try:
                parsed = Decimal(str(value))
            except Exception:
                continue
            if not parsed.is_finite():
                raise ValueError("金额和 RPM 必须是有限数字")
        return data

    @field_validator(
        "revenue",
        "rpm",
        "revenue_before_deduct",
        "rpm_before_deduct",
        mode="before",
    )
    @classmethod
    def reject_non_finite_raw_amounts(cls, value):
        """在 Pydantic Decimal 解析前拦截 NaN/Infinity，并返回稳定中文错误。"""
        if value is None:
            return value
        try:
            parsed = Decimal(str(value))
        except Exception:
            return value
        if not parsed.is_finite():
            raise ValueError("金额和 RPM 必须是有限数字")
        return value

    @field_validator(
        "revenue",
        "rpm",
        "revenue_before_deduct",
        "rpm_before_deduct",
    )
    @classmethod
    def validate_finite_amounts(
        cls, value: Decimal | None, info: ValidationInfo
    ) -> Decimal | None:
        """按对应 MySQL DECIMAL 列精度校验，避免数据库静默舍入或溢出。"""
        if value is None:
            return value
        if not value.is_finite():
            raise ValueError("金额和 RPM 必须是有限数字")

        # ORM: revenue/revenue_before_deduct DECIMAL(12,4);
        # rpm/rpm_before_deduct DECIMAL(10,4)。
        max_abs = (
            Decimal("99999999.9999")
            if info.field_name in {"revenue", "revenue_before_deduct"}
            else Decimal("999999.9999")
        )
        if abs(value) > max_abs:
            raise ValueError(f"{info.field_name}超出数据库 DECIMAL 存储范围")
        if value.quantize(Decimal("0.0001")) != value:
            raise ValueError(f"{info.field_name}最多允许 4 位小数")
        return value


class TBSearchDataInDBBase(TBSearchDataBase):
    """
    数据库持久化模型，含主键与时间戳
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TBSearchDataResponse(TBSearchDataInDBBase):
    """
    API 列表/详情响应，附带客户与用户展示名
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    client_id: int | None = None
    client_name: str | None = None
    user_name: str | None = None


class TBSearchDataListResponse(BaseSchema):
    """
    分页列表包装（兼容旧接口结构）
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    data: list[TBSearchDataResponse]
    total: int
    page: int
    page_size: int


class TBSearchDataUpdate(BaseSchema):
    """
    单条更新请求，所有字段可选（仅提交需修改项）
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    product_id: int | None = None
    country_code: str | None = None
    redirects: int | None = Field(default=None, ge=0, le=2147483647)
    searches: int | None = Field(default=None, ge=0, le=2147483647)
    monetized: int | None = Field(default=None, ge=0, le=2147483647)
    clicks: int | None = Field(default=None, ge=0, le=2147483647)
    revenue: Decimal | None = None
    rpm: Decimal | None = None
    revenue_before_deduct: Decimal | None = None
    rpm_before_deduct: Decimal | None = None

    @field_validator(
        "revenue",
        "rpm",
        "revenue_before_deduct",
        "rpm_before_deduct",
    )
    @classmethod
    def validate_finite_amounts(
        cls, value: Decimal | None, info: ValidationInfo
    ) -> Decimal | None:
        """按对应 MySQL DECIMAL 列精度校验，避免数据库静默舍入或溢出。"""
        if value is None:
            return value
        if not value.is_finite():
            raise ValueError("金额和 RPM 必须是有限数字")

        max_abs = (
            Decimal("99999999.9999")
            if info.field_name in {"revenue", "revenue_before_deduct"}
            else Decimal("999999.9999")
        )
        if abs(value) > max_abs:
            raise ValueError(f"{info.field_name}超出数据库 DECIMAL 存储范围")
        if value.quantize(Decimal("0.0001")) != value:
            raise ValueError(f"{info.field_name}最多允许 4 位小数")
        return value

    @model_validator(mode="after")
    def reject_explicit_nulls_for_non_nullable_fields(self):
        """区分字段未提交与显式 null，避免把 NULL 写入数据库 NOT NULL 列。"""
        non_nullable_fields = {
            "product_id",
            "redirects",
            "searches",
            "monetized",
            "clicks",
            "revenue",
            "rpm",
            "revenue_before_deduct",
            "rpm_before_deduct",
        }
        for field_name in self.model_fields_set & non_nullable_fields:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name}不能显式设置为 null")
        return self
