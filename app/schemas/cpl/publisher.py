"""
渠道 Schema
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PublisherBase(BaseModel):
    """渠道基础模型"""
    publisher_name: str = Field(..., max_length=100, description="渠道名称")
    email: Optional[str] = Field(None, max_length=255, description="邮箱（可选）")
    price_discount: float = Field(0.0, ge=0, le=100,
                                  description="渠道级别的价格折扣比例（0-100），用于旧价格折扣系统，计算给渠道的最终金额")
    postback_url: Optional[str] = Field(None, description="Postback URL（可选）")
    postback_method: str = Field('GET', description="Postback请求方式：GET/POST")
    postback_success_check: Optional[str] = Field(None,
                                                  description="转发成功检查配置（JSON格式，用于检查响应内容是否表示成功）")
    client_id: Optional[int] = Field(None, description="关联的客户ID（可选）")
    is_active: bool = Field(True, description="是否激活")


class PublisherCreate(PublisherBase):
    """创建渠道"""
    pass


class PublisherUpdate(BaseModel):
    """更新渠道"""
    publisher_name: Optional[str] = Field(None, max_length=100, description="渠道名称")
    email: Optional[str] = Field(None, max_length=255, description="邮箱")
    price_discount: Optional[float] = Field(None, ge=0, le=100, description="价格折扣比例（0-100），用于旧价格折扣系统")
    postback_url: Optional[str] = Field(None, description="Postback URL")
    postback_method: Optional[str] = Field(None, description="Postback请求方式：GET/POST")
    postback_success_check: Optional[str] = Field(None,
                                                  description="转发成功检查配置（JSON格式，用于检查响应内容是否表示成功）")
    client_id: Optional[int] = Field(None, description="关联的客户ID（可选）")
    is_active: Optional[bool] = Field(None, description="是否激活")


class PublisherResponse(PublisherBase):
    """渠道响应"""
    id: int
    active_advertiser_count: int
    client_id: Optional[int] = None
    client_name: Optional[str] = None  # 客户名称（从关联的Client获取）
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
