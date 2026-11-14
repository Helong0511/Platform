"""用户操作审计日志 Schema

职责：定义审计日志查询参数、列表轻量字段与详情响应结构。

供 /audit-logs API 与 log_* 审计写入共用字段约定。

说明：请求/响应 JSON 结构定义，供 FastAPI 自动校验与 OpenAPI 文档生成。

说明：请求/响应 JSON 结构定义，供 FastAPI 校验与 OpenAPI 文档生成。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema, ResponseBaseSchema, PaginatedResponseBaseSchema


class ClientErrorReportRequest(BaseModel):
    """前端错误上报请求；使用 JSON body，避免敏感错误内容进入 URL 查询日志。"""

    error_type: str = Field(..., min_length=1, max_length=100)
    error_message: str = Field(..., min_length=1, max_length=500)
    error_stack: Optional[str] = Field(None, max_length=2000)
    error_url: Optional[str] = Field(None, max_length=500)
    user_agent: Optional[str] = Field(None, max_length=500)



class UserAuditLogBase(BaseSchema):
    """
    用户操作日志基础模型
    
    继承 BaseSchema。公共字段基类，供 Create/Update/Response 等模型复用。
    """
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
    details: Optional[str] = Field(None, description="脱敏后的详细审计信息")
    """
    用户操作日志响应模型
    
    继承 UserAuditLogBase。单条或列表项的 API 响应数据结构。
    """


class UserAuditLogResponse(UserAuditLogBase):
    """
    用户操作日志响应模型
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    id: int
    """
    用户操作日志列表响应模型（轻量字段，优化列表加载性能）
    
    继承 BaseSchema。单条或列表项的 API 响应数据结构。
    """

    model_config = {
        "from_attributes": True
    }


class UserAuditLogListResponse(BaseSchema):
    """
    用户操作日志列表响应模型（轻量字段，优化列表加载性能）
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    id: int
    user_id: Optional[int] = Field(None, description="用户ID")
    username: Optional[str] = Field(None, max_length=50, description="用户名")
    action_type: str = Field(..., max_length=50, description="操作类型")
    resource_type: Optional[str] = Field(None, max_length=50, description="资源类型")
    resource_id: Optional[int] = Field(None, description="资源ID")
    resource_name: Optional[str] = Field(None, max_length=255, description="资源名称")
    ip_address: Optional[str] = Field(None, max_length=50, description="IP地址")
    """
    用户操作日志查询参数
    
    继承 BaseModel。查询/筛选/分页参数模型。
    """
    request_path: Optional[str] = Field(None, max_length=500, description="请求路径")
    status_code: Optional[int] = Field(None, description="HTTP状态码")
    success: bool = Field(True, description="操作是否成功")
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class UserAuditLogQuery(BaseModel):
    """
    用户操作日志查询参数
    
    查询/筛选参数模型，用于列表接口的过滤条件与分页。
    """
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
AuditLogListResponse = PaginatedResponseBaseSchema[list[UserAuditLogListResponse]]
