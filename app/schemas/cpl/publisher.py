"""渠道（下游）Pydantic 数据模型。

定义渠道创建/更新/响应的字段校验，包括 Postback 配置、
价格折扣、关联客户及转发成功检查规则等。

说明：CPL 业务字段模型，与数据库表及前端表单校验保持一致。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import Field, ConfigDict

from app.schemas.base import BaseSchema


class PublisherBase(BaseSchema):
    """
    渠道基础模型
    
    继承 BaseModel。公共字段基类，供 Create/Update/Response 等模型复用。
    """
    publisher_name: str = Field(..., max_length=100, description="渠道名称")
    email: Optional[str] = Field(None, max_length=255, description="邮箱（可选）")
    price_discount: Decimal = Field(Decimal('0'), ge=0, le=100,
                                  description="渠道级别的价格折扣比例（0-100），用于旧价格折扣系统，计算给渠道的最终金额")
    postback_url: Optional[str] = Field(None, description="Postback URL（可选）")
    postback_method: str = Field('GET', description="Postback请求方式：GET/POST")
    postback_success_check: Optional[str] = Field(None,
                                                  description="转发成功检查配置（JSON格式，用于检查响应内容是否表示成功）")
    client_id: Optional[int] = Field(None, description="关联的客户ID（可选）")
    """
    创建渠道
    
    继承 PublisherBase。创建请求体：提交新记录所需字段，由 Pydantic 校验必填项与取值范围。
    """

"""

更新渠道



继承 BaseModel。更新请求体：字段均可选，仅提交需要修改的列。

"""

class PublisherCreate(PublisherBase):
    """
    创建渠道
    
    创建请求体：包含新建记录所需字段，提交前由 Pydantic 自动校验类型与取值范围。
    """
    """
    渠道响应
    
    继承 PublisherBase。单条或列表项的 API 响应数据结构。
    """


class PublisherUpdate(BaseSchema):
    """
    更新渠道
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    publisher_name: Optional[str] = Field(None, max_length=100, description="渠道名称")
    email: Optional[str] = Field(None, max_length=255, description="邮箱")
    price_discount: Optional[Decimal] = Field(None, ge=0, le=100, description="价格折扣比例（0-100），用于旧价格折扣系统")
    postback_url: Optional[str] = Field(None, description="Postback URL")
    postback_method: Optional[str] = Field(None, description="Postback请求方式：GET/POST")
    postback_success_check: Optional[str] = Field(None,
                                                  description="转发成功检查配置（JSON格式，用于检查响应内容是否表示成功）")
    client_id: Optional[int] = Field(None, description="关联的客户ID（可选）")
    is_active: Optional[bool] = Field(None, description="是否激活")


class PublisherResponse(PublisherBase):
    """
    渠道响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    id: int
    active_advertiser_count: int
    client_id: Optional[int] = None
    client_name: Optional[str] = None  # 客户名称（从关联的Client获取）
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
