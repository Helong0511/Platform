"""广告数据与仪表盘统计 Schema。

包含 AdData 行数据、Dashboard 卡片指标、趋势图序列等管理端/客户端展示结构。

说明：请求/响应 JSON 结构定义，供 FastAPI 校验与 OpenAPI 文档生成。"""
from datetime import date

from pydantic import BaseModel, ConfigDict


# Python 3.10+ 使用内置类型注解

class StatItem(BaseModel):
    """
    仪表盘单个统计卡片项（含环比趋势）
    
    业务数据模型，用于 API 请求/响应的序列化与校验。
    """
    id: str
    label: str
    value: int | float
    trend: float
    precision: int = 0


class DashboardStatsResponse(BaseModel):
    """
    仪表盘汇总响应：卡片列表 + 衍生指标字典
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    stats: list[StatItem]
    metrics: dict[str, float]


class TrendSeriesItem(BaseModel):
    """
    趋势图单条序列（名称 + 按日数值数组）
    
    业务数据模型，用于 API 请求/响应的序列化与校验。
    """
    name: str
    data: list[int | float]


class TrendDataResponse(BaseModel):
    """
    趋势图响应：横轴日期 + 多条序列
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    dates: list[str]
    series: list[TrendSeriesItem]


class AdDataBase(BaseModel):
    """
    广告数据行基础字段（日期 + 产品 + 国家 + 投放指标）
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    date: date  # 改为必需字段，不是 Optional

    product_id: int | None = None
    product_name: str | None = None  # 添加产品名称字段
    ad_unit: str | None = None  # 广告单元（可为空）
    country_code: str | None = None  # 国家代码（ISO 3166-1 二字母代码）
    country_name_zh: str | None = None  # 国家中文名称
    request_count: int | None = None
    match_count: int | None = None
    coverage_rate: float | None = None
    display_count: int | None = None
    display_rate: float | None = None
    click_count: int | None = None
    click_rate: float | None = None
    viewability_rate: float | None = None
    cpc: float | None = None
    pageviews: int | None = None
    ecpm_after_deduct: float | None = None
    revenue_after_deduct: float | None = None


class AdDataInDBBase(AdDataBase):
    """
    数据库广告数据记录
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    id: int

    model_config = ConfigDict(from_attributes=True)


class AdDataResponse(AdDataInDBBase):
    """
    广告数据 API 响应；管理员可见扣减前金额及客户信息
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    # 管理员额外字段
    client_id: int | None = None
    client_name: str | None = None
    user_name: str | None = None  # 添加用户名称字段
    ecpm_before_deduct: float | None = None
    revenue_before_deduct: float | None = None


class AdDataListResponse(BaseModel):
    """
    广告数据分页列表响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    data: list[AdDataResponse]
    total: int
    page: int
    page_size: int


class AdDataSummaryResponse(BaseModel):
    """
    广告数据区间汇总（展示、点击、收入、平均 eCPM）
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    total_impressions: int
    total_clicks: int
    total_revenue: float
    average_ecpm: float
    date_range: str


class AdDataUpdate(BaseModel):
    """
    更新广告数据的Schema
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    product_id: int | None = None
    ad_unit: str | None = None  # 广告单元（可为空，空字符串表示无）
    country_code: str | None = None  # 国家代码（支持多种格式：alpha_2_code、alpha_3_code、numeric_code、country_name_en、country_name_zh、official_name_en、official_name_zh）
    request_count: int | None = None
    match_count: int | None = None
    display_count: int | None = None
    click_count: int | None = None
    viewability_rate: float | None = None
    cpc: float | None = None
    pageviews: int | None = None
    ecpm_after_deduct: float | None = None
    ecpm_before_deduct: float | None = None
    revenue_after_deduct: float | None = None
    revenue_before_deduct: float | None = None

    model_config = ConfigDict(from_attributes=True)
