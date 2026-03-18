"""
Offer Schema
"""
from datetime import datetime
from typing import Optional, List
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class OfferBase(BaseModel):
    """Offer基础模型"""
    offer_name: str = Field(..., max_length=200, description="Offer名称")
    advertiser_offer_id: Optional[str] = Field(None, max_length=100, description="上游系统中的Offer ID")
    advertiser_id: int = Field(..., description="关联的广告主ID")
    preview_link: Optional[str] = Field(None, description="预览链接")
    payout: Optional[float] = Field(None, ge=0, description="上游支付金额（PO）")
    affiliate_payout: Optional[float] = Field(None, ge=0, description="扣价后给渠道的金额")
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
        """验证URL格式"""
        if v:
            try:
                parsed = urlparse(v)
                if not parsed.scheme or not parsed.netloc:
                    raise ValueError("URL格式无效，必须包含协议和域名")
            except Exception:
                raise ValueError("URL格式无效")
        return v


class PublisherConfig(BaseModel):
    """渠道配置"""
    publisher_id: int = Field(..., description="渠道ID")
    downstream_cap: Optional[int] = Field(None, ge=0,
                                          description="该渠道的下游每天转化个数的限制，如果渠道转化超过了这个值就不通知渠道了。客户登录查看时，也只显示真实的（真实不超过【下游Cap】的）转化")
    affiliate_payout: Optional[float] = Field(None, ge=0,
                                              description="该渠道的转化金额（不是金额的扣减比例）。如果上游通知的金额大于这个金额，就按照【下游PO】的金额通知渠道")


class OfferCreate(OfferBase):
    """创建Offer"""
    publisher_ids: Optional[list[int]] = Field(None, description="分配的渠道ID列表（已废弃，使用publisher_configs）")
    publisher_configs: Optional[List[PublisherConfig]] = Field(None,
                                                               description="渠道配置列表，每个渠道对应一个下游Cap和下游PO")


class OfferUpdate(BaseModel):
    """更新Offer"""
    offer_name: Optional[str] = Field(None, max_length=200, description="Offer名称")
    advertiser_offer_id: Optional[str] = Field(None, max_length=100, description="上游Offer ID")
    advertiser_id: Optional[int] = Field(None, description="广告主ID")
    preview_link: Optional[str] = Field(None, description="预览链接")
    payout: Optional[float] = Field(None, ge=0, description="上游支付金额")
    affiliate_payout: Optional[float] = Field(None, ge=0, description="扣价后金额")
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
    publisher_ids: Optional[list[int]] = Field(None, description="分配的渠道ID列表（已废弃，使用publisher_configs）")
    publisher_configs: Optional[List[PublisherConfig]] = Field(None,
                                                               description="渠道配置列表，每个渠道对应一个下游Cap和下游PO")


class OfferResponse(OfferBase):
    """Offer响应"""
    id: int
    downstream_tracklink: Optional[str] = None
    click_validity_hours: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    # 关联信息
    advertiser_name: Optional[str] = None
    assigned_publishers: Optional[list[dict]] = None

    class Config:
        from_attributes = True
