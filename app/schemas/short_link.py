"""
短链接 Schema
"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse


class ShortLinkBase(BaseModel):
    """短链接基础模型"""
    original_url: str = Field(..., description="原始URL")
    title: Optional[str] = Field(None, max_length=200, description="短链接标题（可选）")
    description: Optional[str] = Field(None, description="短链接描述（可选）")
    short_code: Optional[str] = Field(None, max_length=20, description="自定义短链接代码（可选，不填则自动生成）")
    offer_id: Optional[int] = Field(None, description="关联的Offer ID（可选）")
    expires_at: Optional[datetime] = Field(None, description="过期时间（可选）")
    is_active: bool = Field(True, description="是否激活")

    @field_validator('original_url')
    @classmethod
    def validate_url(cls, v):
        """验证URL格式"""
        if not v:
            raise ValueError("原始URL不能为空")
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("URL格式无效，必须包含协议（http://或https://）和域名")
        return v

    @field_validator('short_code')
    @classmethod
    def validate_short_code(cls, v):
        """验证短链接代码格式"""
        if v:
            # 只允许字母、数字、连字符和下划线
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', v):
                raise ValueError("短链接代码只能包含字母、数字、连字符和下划线")
            if len(v) < 3:
                raise ValueError("短链接代码至少需要3个字符")
            if len(v) > 20:
                raise ValueError("短链接代码最多20个字符")
        return v


class ShortLinkCreate(ShortLinkBase):
    """创建短链接"""
    pass


class ShortLinkUpdate(BaseModel):
    """更新短链接"""
    original_url: Optional[str] = Field(None, description="原始URL")
    title: Optional[str] = Field(None, max_length=200, description="短链接标题")
    description: Optional[str] = Field(None, description="短链接描述")
    offer_id: Optional[int] = Field(None, description="关联的Offer ID")
    is_active: Optional[bool] = Field(None, description="是否激活")
    expires_at: Optional[datetime] = Field(None, description="过期时间")

    @field_validator('original_url')
    @classmethod
    def validate_url(cls, v):
        """验证URL格式"""
        if v:
            parsed = urlparse(v)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("URL格式无效，必须包含协议（http://或https://）和域名")
        return v


class ShortLinkResponse(ShortLinkBase):
    """短链接响应"""
    id: int
    click_count: int
    created_by: Optional[int] = None
    creator_name: Optional[str] = None  # 创建者用户名
    offer_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    short_url: Optional[str] = None  # 完整的短链接URL

    class Config:
        from_attributes = True


class ShortLinkListResponse(BaseModel):
    """短链接列表响应"""
    data: list[ShortLinkResponse]
    total: int
    page: int
    page_size: int


class ShortLinkStatsResponse(BaseModel):
    """短链接统计响应"""
    total_links: int
    total_clicks: int
    active_links: int
    expired_links: int

