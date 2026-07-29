"""淘宝搜索数据（TBSearchData）Schema。

按日期、产品、国家维度存储 redirects/searches/clicks 等投放侧指标。

说明：请求/响应 JSON 结构定义，供 FastAPI 校验与 OpenAPI 文档生成。"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import ConfigDict

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
    redirects: int | None = 0
    searches: int | None = 0
    monetized: int | None = 0
    clicks: int | None = 0
    revenue: Decimal | None = Decimal('0')
    rpm: Decimal | None = Decimal('0')
    revenue_before_deduct: Decimal | None = Decimal('0')
    rpm_before_deduct: Decimal | None = Decimal('0')


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
    redirects: int | None = None
    searches: int | None = None
    monetized: int | None = None
    clicks: int | None = None
    revenue: Decimal | None = None
    rpm: Decimal | None = None
    revenue_before_deduct: Decimal | None = None
    rpm_before_deduct: Decimal | None = None
