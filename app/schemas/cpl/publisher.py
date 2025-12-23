"""
渠道 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PublisherBase(BaseModel):
    """渠道基础模型"""
    publisher_name: str = Field(..., max_length=100, description="渠道名称")
    email: Optional[str] = Field(None, max_length=255, description="邮箱（可选）")
    price_discount: float = Field(0.0, ge=0, le=100, description="渠道级别的价格扣量比例（0-100）")
    postback_url: Optional[str] = Field(None, description="Postback URL（可选）")
    postback_method: str = Field('GET', description="Postback请求方式：GET/POST")
    is_active: bool = Field(True, description="是否激活")


class PublisherCreate(PublisherBase):
    """创建渠道"""
    pass


class PublisherUpdate(BaseModel):
    """更新渠道"""
    publisher_name: Optional[str] = Field(None, max_length=100, description="渠道名称")
    email: Optional[str] = Field(None, max_length=255, description="邮箱")
    price_discount: Optional[float] = Field(None, ge=0, le=100, description="扣量比例")
    postback_url: Optional[str] = Field(None, description="Postback URL")
    postback_method: Optional[str] = Field(None, description="Postback请求方式：GET/POST")
    is_active: Optional[bool] = Field(None, description="是否激活")


class PublisherResponse(PublisherBase):
    """渠道响应"""
    id: int
    active_advertiser_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

