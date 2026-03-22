"""
第三方上报日志Schema
用于API请求和响应的数据验证
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema, ResponseBaseSchema, PaginatedResponseBaseSchema


class ThirdPartyReportLogBase(BaseSchema):
    """第三方上报日志基础模型"""
    source: str = Field(..., max_length=50, description="来源")
    adsid: str = Field(..., max_length=500, description="广告ID")
    event: str = Field(..., max_length=50, description="事件类型")
    conversion_id: Optional[str] = Field(None, max_length=255, description="转化ID")
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
    error_message: Optional[str] = Field(None, description="错误信息")


class ThirdPartyReportLogResponse(ThirdPartyReportLogBase):
    """第三方上报日志响应模型"""
    id: int
    created_at: datetime
    report_start_time: Optional[datetime] = None
    report_success_time: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class ThirdPartyReportLogQuery(BaseModel):
    """第三方上报日志查询参数"""
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
ThirdPartyReportLogResponseList = PaginatedResponseBaseSchema[list[ThirdPartyReportLogResponse]]
