"""
用户操作日志Schema
用于API请求和响应的数据验证
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema, ResponseBaseSchema, PaginatedResponseBaseSchema


class UserAuditLogBase(BaseSchema):
    """用户操作日志基础模型"""
    user_id: Optional[int] = Field(None, description="用户ID")
    username: Optional[str] = Field(None, max_length=50, description="用户名")
    action_type: str = Field(..., max_length=50, description="操作类型")
    resource_type: Optional[str] = Field(None, max_length=50, description="资源类型")
    resource_id: Optional[int] = Field(None, description="资源ID")
    resource_name: Optional[str] = Field(None, max_length=255, description="资源名称")
    ip_address: Optional[str] = Field(None, max_length=50, description="IP地址")
    user_agent: Optional[str] = Field(None, max_length=500, description="用户代理")
    request_method: Optional[str] = Field(None, max_length=10, description="HTTP请求方法")
    request_path: Optional[str] = Field(None, max_length=500, description="请求路径")
    request_params: Optional[str] = Field(None, description="请求参数")
    status_code: Optional[int] = Field(None, description="HTTP状态码")
    success: bool = Field(True, description="操作是否成功")
    error_message: Optional[str] = Field(None, description="错误信息")
    details: Optional[str] = Field(None, description="详细信息")


class UserAuditLogResponse(UserAuditLogBase):
    """用户操作日志响应模型"""
    id: int
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class UserAuditLogQuery(BaseModel):
    """用户操作日志查询参数"""
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(10, ge=1, le=100, description="每页数量")
    user_id: Optional[int] = Field(None, description="用户ID筛选")
    username: Optional[str] = Field(None, max_length=50, description="用户名筛选")
    action_type: Optional[str] = Field(None, max_length=50, description="操作类型筛选")
    resource_type: Optional[str] = Field(None, max_length=50, description="资源类型筛选")
    ip_address: Optional[str] = Field(None, max_length=50, description="IP地址筛选")
    success: Optional[bool] = Field(None, description="是否成功筛选")
    start_date: Optional[datetime] = Field(None, description="开始时间")
    end_date: Optional[datetime] = Field(None, description="结束时间")


# 响应类型别名
AuditLogResponse = ResponseBaseSchema[UserAuditLogResponse]
AuditLogListResponse = PaginatedResponseBaseSchema[list[UserAuditLogResponse]]
