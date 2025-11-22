from datetime import date, datetime
from pydantic import BaseModel, field_serializer


# Python 3.10+ 使用内置类型注解

class StatItem(BaseModel):
    id: str
    label: str
    value: int | float
    trend: float
    precision: int = 0


class DashboardStatsResponse(BaseModel):
    stats: list[StatItem]
    metrics: dict[str, float]


class TrendSeriesItem(BaseModel):
    name: str
    data: list[int | float]


class TrendDataResponse(BaseModel):
    dates: list[str]
    series: list[TrendSeriesItem]


class AdDataBase(BaseModel):
    date: date  # 改为必需字段，不是 Optional

    product_id: int | None = None
    product_name: str | None = None  # 添加产品名称字段
    country_code: str | None = None  # 国家代码（ISO 3166-1 二字母代码）
    country_name_zh: str | None = None  # 国家中文名称
    request_count: int | None = None
    match_count: int | None = None
    coverage_rate: float | None = None
    display_count: int | None = None
    display_rate: float | None = None
    click_count: int | None = None
    click_rate: float | None = None
    ecpm_after_deduct: float | None = None
    revenue_after_deduct: float | None = None


class AdDataInDBBase(AdDataBase):
    id: int

    class Config:
        from_attributes = True


class AdDataResponse(AdDataInDBBase):
    # 管理员额外字段
    client_id: int | None = None
    client_name: str | None = None
    user_name: str | None = None  # 添加用户名称字段
    ecpm_before_deduct: float | None = None
    revenue_before_deduct: float | None = None


class AdDataListResponse(BaseModel):
    data: list[AdDataResponse]
    total: int
    page: int
    page_size: int


class AdDataSummaryResponse(BaseModel):
    total_impressions: int
    total_clicks: int
    total_revenue: float
    average_ecpm: float
    date_range: str


class AdDataUpdate(BaseModel):
    """更新广告数据的Schema"""
    product_id: int | None = None
    country_code: str | None = None  # 国家代码（支持多种格式：alpha_2_code、alpha_3_code、numeric_code、country_name_en、country_name_zh、official_name_en、official_name_zh）
    request_count: int | None = None
    match_count: int | None = None
    display_count: int | None = None
    click_count: int | None = None
    ecpm_after_deduct: float | None = None
    ecpm_before_deduct: float | None = None
    revenue_after_deduct: float | None = None
    revenue_before_deduct: float | None = None

    class Config:
        from_attributes = True
