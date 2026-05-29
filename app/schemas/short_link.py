"""
短链接 Schema
"""
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from app.core.url.placeholder_validation import (
    format_placeholder_validation_error,
    validate_track_url_placeholders,
)


class ShortLinkBase(BaseModel):
    """短链接基础模型"""
    original_url: str = Field(..., description="原始 URL")
    title: Optional[str] = Field(None, max_length=200, description="短链接标题（可选）")
    description: Optional[str] = Field(None, description="短链接描述（可选）")
    short_code: Optional[str] = Field(None, max_length=20, description="自定义短链接代码（可选，不填则自动生成）")
    offer_id: Optional[int] = Field(None, description="关联的 Offer ID（可选）")
    channel_id: Optional[int] = Field(None, description="关联的渠道 ID（可选）")
    expires_at: Optional[datetime] = Field(None, description="过期时间（可选）")
    is_active: bool = Field(True, description="是否激活")
    
    # Facebook 像素配置字段（可选，不设置则使用全局配置）
    facebook_pixel_id: Optional[str] = Field(None, max_length=50, description="Facebook Pixel ID（可选，不设置则使用全局配置）")
    facebook_access_token: Optional[str] = Field(None, max_length=500, description="Facebook Access Token（可选，不设置则使用全局配置）")
    facebook_api_version: Optional[str] = Field("v21.0", max_length=20, description="Facebook API 版本（可选，默认 v21.0）")

    @field_validator('original_url')
    @classmethod
    def validate_url(cls, v):
        """验证 URL 格式"""
        if not v:
            raise ValueError("原始 URL 不能为空")
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("URL 格式无效，必须包含协议（http://或 https://）和域名")
        return v

    @field_validator('short_code')
    @classmethod
    def validate_short_code(cls, v):
        """验证短链接代码格式"""
        if v:
            # 只允许字母、数字、连字符和下划线
            if not re.match(r'^[a-zA-Z0-9_-]+$', v):
                raise ValueError("短链接代码只能包含字母、数字、连字符和下划线")
            if len(v) < 3:
                raise ValueError("短链接代码至少需要 3 个字符")
            if len(v) > 20:
                raise ValueError("短链接代码最多 20 个字符")
        return v
    
    @field_validator('facebook_api_version')
    @classmethod
    def validate_api_version(cls, v):
        """验证 Facebook API 版本格式"""
        if v:
            if not re.match(r'^v\d+\.\d+$', v):
                raise ValueError("Facebook API 版本格式不正确，应为 v21.0 格式")
        return v

class ShortLinkCreate(ShortLinkBase):
    """创建短链接"""

    @model_validator(mode="after")
    def validate_url_placeholders(self):
        ph = validate_track_url_placeholders(
            self.original_url,
            offer_id=self.offer_id,
            channel_id=self.channel_id,
        )
        if not ph.ok:
            raise ValueError(format_placeholder_validation_error(ph))
        return self


class ShortLinkUpdate(BaseModel):
    """更新短链接"""
    original_url: Optional[str] = Field(None, description="原始 URL")
    title: Optional[str] = Field(None, max_length=200, description="短链接标题")
    description: Optional[str] = Field(None, description="短链接描述")
    offer_id: Optional[int] = Field(None, description="关联的 Offer ID")
    channel_id: Optional[int] = Field(None, description="关联的渠道 ID")
    is_active: Optional[bool] = Field(None, description="是否激活")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    
    # Facebook 像素配置字段（可选）
    facebook_pixel_id: Optional[str] = Field(None, max_length=50, description="Facebook Pixel ID（可选，不设置则使用全局配置）")
    facebook_access_token: Optional[str] = Field(None, max_length=500, description="Facebook Access Token（可选，不设置则使用全局配置）")
    facebook_api_version: Optional[str] = Field(None, max_length=20, description="Facebook API 版本（可选）")

    @field_validator('original_url')
    @classmethod
    def validate_url(cls, v):
        """验证 URL 格式"""
        if v:
            parsed = urlparse(v)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("URL 格式无效，必须包含协议（http://或 https://）和域名")
        return v
    
    @field_validator('facebook_api_version')
    @classmethod
    def validate_api_version(cls, v):
        """验证 Facebook API 版本格式"""
        if v:
            if not re.match(r'^v\d+\.\d+$', v):
                raise ValueError("Facebook API 版本格式不正确，应为 v21.0 格式")
        return v

    @model_validator(mode="after")
    def validate_url_placeholders(self):
        if not self.original_url:
            return self
        ph = validate_track_url_placeholders(
            self.original_url,
            offer_id=self.offer_id,
            channel_id=self.channel_id,
        )
        if not ph.ok:
            raise ValueError(format_placeholder_validation_error(ph))
        return self


class ShortLinkResponse(ShortLinkBase):
    """短链接响应"""
    id: int
    click_count: int
    show_count: int
    created_by: Optional[int] = None
    creator_name: Optional[str] = None  # 创建者用户名
    offer_id: Optional[int] = None
    channel_id: Optional[int] = None
    channel_name: Optional[str] = None  # 渠道名称
    created_at: datetime
    updated_at: datetime
    short_url: Optional[str] = None  # 完整的短链接 URL
    # Facebook 像素配置字段（响应中包含）
    facebook_pixel_id: Optional[str] = None
    facebook_access_token: Optional[str] = None
    facebook_api_version: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


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
