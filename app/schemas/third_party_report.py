"""第三方 Conversions API 上报日志 Schema

职责：定义斗篷/Meta 像素上报记录的查询筛选与分页响应字段。

供 /third-party-reports API 使用。

说明：请求/响应 JSON 结构定义，供 FastAPI 自动校验与 OpenAPI 文档生成。

说明：请求/响应 JSON 结构定义，供 FastAPI 校验与 OpenAPI 文档生成。"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema, ResponseBaseSchema, PaginatedResponseBaseSchema


class ThirdPartyReportLogBase(BaseSchema):
    """
    第三方上报日志基础模型
    
    继承 BaseSchema。公共字段基类，供 Create/Update/Response 等模型复用。
    """
    source: str = Field(..., max_length=50, description="来源")
    adsid: str = Field(..., max_length=500, description="广告ID")
    event: str = Field(..., max_length=50, description="事件类型")
    conversion_id: Optional[str] = Field(None, max_length=255, description="转化ID")
    currency: Optional[str] = Field(None, max_length=10, description="货币类型")
    amount: Optional[Decimal] = Field(None, description="支付金额")
    email: Optional[str] = Field(None, max_length=255, description="邮箱")
    ip: Optional[str] = Field(None, max_length=50, description="IP地址")
    phone: Optional[str] = Field(None, max_length=50, description="手机号")
    ua: Optional[str] = Field(None, description="用户代理")
    report_params: Optional[str] = Field(None, description="完整上报参数（JSON格式）")
    use_hash: bool = Field(True, description="是否对email、ip、phone进行哈希处理")
    status: str = Field(..., max_length=20, description="状态")
    attempt_count: int = Field(0, description="尝试次数")
    max_attempts: int = Field(3, description="最大尝试次数")
    response_status: Optional[int] = Field(None, description="响应状态码")
    response_body: Optional[str] = Field(None, description="响应内容")
    log_id: Optional[str] = Field(None, max_length=100, description="日志ID")
    """
    第三方上报日志响应模型
    
    继承 ThirdPartyReportLogBase。单条或列表项的 API 响应数据结构。
    """


class ThirdPartyReportLogResponse(ThirdPartyReportLogBase):
    """
    第三方上报日志响应模型
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    id: int
    created_at: datetime
    report_start_time: Optional[datetime] = None
    report_success_time: Optional[datetime] = None
    """
    第三方上报日志列表响应模型（轻量字段）
    
    继承 BaseSchema。单条或列表项的 API 响应数据结构。
    """

    model_config = {
        "from_attributes": True
    }


class ThirdPartyReportLogListResponse(BaseSchema):
    """
    第三方上报日志列表响应模型（轻量字段）
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    id: int
    source: str = Field(..., max_length=50, description="来源")
    adsid: str = Field(..., max_length=500, description="广告ID")
    event: str = Field(..., max_length=50, description="事件类型")
    conversion_id: Optional[str] = Field(None, max_length=255, description="转化ID")
    currency: Optional[str] = Field(None, max_length=10, description="货币类型")
    amount: Optional[Decimal] = Field(None, description="支付金额")
    use_hash: bool = Field(True, description="是否对email、ip、phone进行哈希处理")
    status: str = Field(..., max_length=20, description="状态")
    attempt_count: int = Field(0, description="尝试次数")
    max_attempts: int = Field(3, description="最大尝试次数")
    response_status: Optional[int] = Field(None, description="响应状态码")
    log_id: Optional[str] = Field(None, max_length=100, description="日志ID")
    """
    第三方上报日志查询参数
    
    继承 BaseModel。查询/筛选/分页参数模型。
    """
    created_at: datetime
    report_start_time: Optional[datetime] = None
    report_success_time: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class ThirdPartyReportLogQuery(BaseModel):
    """
    第三方上报日志查询参数
    
    查询/筛选参数模型，用于列表接口的过滤条件与分页。
    """
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(10, ge=1, le=100, description="每页数量")
    source: Optional[str] = Field(None, max_length=50, description="来源筛选")
    adsid: Optional[str] = Field(None, max_length=500, description="广告ID筛选")
    event: Optional[str] = Field(None, max_length=50, description="事件类型筛选")
    status: Optional[str] = Field(None, max_length=20, description="状态筛选")
    start_date: Optional[datetime] = Field(None, description="开始时间")
    end_date: Optional[datetime] = Field(None, description="结束时间")


# 响应类型别名
ThirdPartyReportLogResponseSingle = ResponseBaseSchema[ThirdPartyReportLogResponse]
ThirdPartyReportLogResponseList = PaginatedResponseBaseSchema[list[ThirdPartyReportLogListResponse]]
