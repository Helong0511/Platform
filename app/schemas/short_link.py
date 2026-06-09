"""短链接 Pydantic 数据模型。

定义短链接创建/更新/响应的字段校验，包括原始 URL、
自定义短码、Offer/渠道关联、过期时间及 Facebook 像素配置。
创建/更新时校验 URL 格式与 Tracklink 占位符合法性。

说明：请求/响应 JSON 结构定义，供 FastAPI 校验与 OpenAPI 文档生成。"""
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
    """
    短链接公共字段：原始 URL、自定义短码、Offer/渠道关联、过期与 Facebook 像素配置。

    创建/更新时校验 URL 协议、短码字符集及 API 版本格式。
    """
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
        """验证 URL 格式。用于 API 请求/响应序列化与 OpenAPI 文档生成。"""
        if not v:
            raise ValueError("原始 URL 不能为空")
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("URL 格式无效，必须包含协议（http://或 https://）和域名")
        return v

    @field_validator('short_code')
    @classmethod
    def validate_short_code(cls, v):
        """验证短链接代码格式。用于 API 请求/响应序列化与 OpenAPI 文档生成。"""
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
        """验证 Facebook API 版本格式（详见字段 Field description）。"""
        if v:
            if not re.match(r'^v\d+\.\d+$', v):
                raise ValueError("Facebook API 版本格式不正确，应为 v21.0 格式")
        return v

class ShortLinkCreate(ShortLinkBase):
    """创建短链接请求；额外校验 Tracklink 占位符与 Offer/渠道关联一致性。"""

    @model_validator(mode="after")
    def validate_url_placeholders(self):
        """创建时校验原始 URL 中 Tracklink 占位符是否合法（详见字段 Field description）。"""
        ph = validate_track_url_placeholders(
            self.original_url,
            offer_id=self.offer_id,
            channel_id=self.channel_id,
        )
        if not ph.ok:
            raise ValueError(format_placeholder_validation_error(ph))
        return self


class ShortLinkUpdate(BaseModel):
    """更新短链接请求；字段均可选，修改 original_url 时重新校验占位符。"""
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
        """验证 URL 格式。用于 API 请求/响应序列化与 OpenAPI 文档生成。"""
        if v:
            parsed = urlparse(v)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("URL 格式无效，必须包含协议（http://或 https://）和域名")
        return v
    
    @field_validator('facebook_api_version')
    @classmethod
    def validate_api_version(cls, v):
        """验证 Facebook API 版本格式（详见字段 Field description）。"""
        if v:
            if not re.match(r'^v\d+\.\d+$', v):
                raise ValueError("Facebook API 版本格式不正确，应为 v21.0 格式")
        return v

    @model_validator(mode="after")
    def validate_url_placeholders(self):
        """更新 original_url 时校验占位符；未改 URL 则跳过（详见字段 Field description）。"""
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
    """
    短链接详情响应。

    含点击/展示计数、创建者、渠道名称、完整 short_url 及像素配置快照。
    """
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
    """短链接分页列表响应：含 data 数组与 total/page/page_size。"""
    data: list[ShortLinkResponse]
    total: int
    page: int
    page_size: int


class ShortLinkStatsResponse(BaseModel):
    """短链接统计响应。用于 API 请求/响应序列化与 OpenAPI 文档生成。"""
    total_links: int
    total_clicks: int
    active_links: int
    expired_links: int
