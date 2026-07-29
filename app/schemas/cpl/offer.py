"""Offer（广告活动）Pydantic 数据模型。

定义 Offer 创建/更新/响应的字段校验规则，包括：
- URL 格式校验（预览链接、Tracklink、Postback URL）
- 上游 Tracklink 占位符合法性校验（创建/更新时）
- 按渠道维度的下游 Cap 与扣价配置（PublisherConfig）。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from urllib.parse import urlparse

from pydantic import ConfigDict, Field, field_validator

from app.schemas.base import BaseSchema

from app.core.url.placeholder_validation import (
    format_placeholder_validation_error,
    validate_track_url_placeholders,
)


class OfferBase(BaseSchema):
    """
    Offer 公共字段：名称、上游 ID、Tracklink、Postback、Cap 与点击有效期等。

    校验预览链接、Tracklink、Postback URL 须含合法协议与域名。
    """
    offer_name: str = Field(..., max_length=200, description="Offer名称")
    advertiser_offer_id: Optional[str] = Field(None, max_length=100, description="上游系统中的Offer ID")
    advertiser_id: int = Field(..., description="关联的广告主ID")
    preview_link: Optional[str] = Field(None, description="预览链接")
    payout: Optional[Decimal] = Field(None, ge=0, description="上游支付金额（PO）")
    affiliate_payout: Optional[Decimal] = Field(None, ge=0, description="扣价后给渠道的金额")
    country: Optional[str] = Field(None, max_length=50, description="国家")
    category: Optional[str] = Field(None, max_length=50, description="分类")
    type: Optional[str] = Field(None, max_length=50, description="类型")
    status: str = Field("Active", description="状态：Active/Inactive")
    upstream_cap: Optional[int] = Field(None, ge=0, description="上游转化上限")
    downstream_cap: Optional[int] = Field(None, ge=0, description="下游转化上限")
    advertiser_tracklink: Optional[str] = Field(None, description="上游的Tracklink")
    postback_url: Optional[str] = Field(None, description="Postback URL")
    postback_method: str = Field("GET", description="Postback请求方式：GET/POST")
    click_validity_hours: Optional[int] = Field(720, ge=1, le=8760, description="点击有效期（小时），默认720小时（30天）")
    is_active: bool = Field(True, description="是否激活")

    @field_validator('preview_link', 'advertiser_tracklink', 'postback_url')
    @classmethod
    def validate_url(cls, v):
        """验证URL格式。用于 API 请求/响应序列化与 OpenAPI 文档生成。"""
        if v:
            try:
                parsed = urlparse(v)
                if not parsed.scheme or not parsed.netloc:
                    raise ValueError("URL格式无效，必须包含协议和域名")
            except Exception:
                raise ValueError("URL格式无效")
        return v

class PublisherConfig(BaseSchema):
    """
    单渠道维度的下游 Cap 与扣价（下游 PO）配置。

    转化超 Cap 不再通知渠道；上游金额高于 affiliate_payout 时按下游 PO 结算。
    """
    publisher_id: int = Field(..., description="渠道ID")
    downstream_cap: Optional[int] = Field(None, ge=0,
                                          description="该渠道的下游每天转化个数的限制，如果渠道转化超过了这个值就不通知渠道了。客户登录查看时，也只显示真实的（真实不超过【下游Cap】的）转化")
    affiliate_payout: Optional[Decimal] = Field(None, ge=0,
                                              description="该渠道的转化金额（不是金额的扣减比例）。如果上游通知的金额大于这个金额，就按照【下游PO】的金额通知渠道")


class OfferCreate(OfferBase):
    """创建 Offer 请求；可附带 publisher_configs 批量配置各渠道 Cap/PO。"""
    publisher_configs: Optional[List[PublisherConfig]] = Field(None,
                                                               description="渠道配置列表，每个渠道对应一个下游Cap和下游PO")

    @field_validator('advertiser_tracklink')
    @classmethod
    def validate_advertiser_tracklink_placeholders(cls, v):
        """创建时校验上游 Tracklink 占位符（读取接口不校验，避免历史数据阻断列表）"""
        if not v:
            return v
        ph = validate_track_url_placeholders(v, skip_association_warnings=True)
        if not ph.ok:
            raise ValueError(format_placeholder_validation_error(ph))
        return v


class OfferUpdate(BaseSchema):
    """更新 Offer 请求；字段均可选，支持同步更新渠道配置列表。（详见字段 Field description）。"""
    offer_name: Optional[str] = Field(None, max_length=200, description="Offer名称")
    advertiser_offer_id: Optional[str] = Field(None, max_length=100, description="上游Offer ID")
    advertiser_id: Optional[int] = Field(None, description="广告主ID")
    preview_link: Optional[str] = Field(None, description="预览链接")
    payout: Optional[Decimal] = Field(None, ge=0, description="上游支付金额")
    affiliate_payout: Optional[Decimal] = Field(None, ge=0, description="扣价后金额")
    country: Optional[str] = Field(None, max_length=50, description="国家")
    category: Optional[str] = Field(None, max_length=50, description="分类")
    type: Optional[str] = Field(None, max_length=50, description="类型")
    status: Optional[str] = Field(None, description="状态")
    upstream_cap: Optional[int] = Field(None, ge=0, description="上游Cap")
    downstream_cap: Optional[int] = Field(None, ge=0, description="下游Cap")
    advertiser_tracklink: Optional[str] = Field(None, description="上游Tracklink")
    postback_url: Optional[str] = Field(None, description="Postback URL")
    postback_method: Optional[str] = Field(None, description="Postback方法")
    click_validity_hours: Optional[int] = Field(None, ge=1, le=8760, description="点击有效期（小时）")
    is_active: Optional[bool] = Field(None, description="是否激活")
    publisher_configs: Optional[List[PublisherConfig]] = Field(None,
                                                               description="渠道配置列表，每个渠道对应一个下游Cap和下游PO")

    @field_validator('preview_link', 'advertiser_tracklink', 'postback_url')
    @classmethod
    def validate_url(cls, v):
        """更新时可选；有值则校验 URL 含协议与域名（详见字段 Field description）。"""
        if v:
            try:
                parsed = urlparse(v)
                if not parsed.scheme or not parsed.netloc:
                    raise ValueError("URL格式无效，必须包含协议和域名")
            except Exception:
                raise ValueError("URL格式无效")
        return v

    @field_validator('advertiser_tracklink')
    @classmethod
    def validate_advertiser_tracklink_placeholders(cls, v):
        """更新时校验上游 Tracklink 占位符合法性（详见字段 Field description）。"""
        if not v:
            return v
        ph = validate_track_url_placeholders(v, skip_association_warnings=True)
        if not ph.ok:
            raise ValueError(format_placeholder_validation_error(ph))
        return v


class OfferResponse(OfferBase):
    """Offer响应。用于 API 请求/响应序列化与 OpenAPI 文档生成。"""
    id: int
    downstream_tracklink: Optional[str] = None
    click_validity_hours: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    # 关联信息
    advertiser_name: Optional[str] = None
    assigned_publishers: Optional[list[dict]] = None

    model_config = ConfigDict(from_attributes=True)
