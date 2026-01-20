"""
广告主 Schema
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class AdvertiserBase(BaseModel):
    """广告主基础模型"""
    advertiser_name: str = Field(..., max_length=100, description="广告主名称")
    email: Optional[str] = Field(None, max_length=255, description="邮箱（可选）")
    mobile: Optional[str] = Field(None, max_length=20, description="手机号")
    advertiser_params: Optional[str] = Field(None, description="广告主参数")
    is_active: bool = Field(True, description="是否激活")


class AdvertiserCreate(AdvertiserBase):
    """创建广告主"""
    pass


class AdvertiserUpdate(BaseModel):
    """更新广告主"""
    advertiser_name: Optional[str] = Field(None, max_length=100, description="广告主名称")
    email: Optional[str] = Field(None, max_length=255, description="邮箱")
    mobile: Optional[str] = Field(None, max_length=20, description="手机号")
    advertiser_params: Optional[str] = Field(None, description="广告主参数")
    is_active: Optional[bool] = Field(None, description="是否激活")


class AdvertiserResponse(AdvertiserBase):
    """广告主响应"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

