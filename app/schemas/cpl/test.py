"""
测试记录 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AdvertiserTestBase(BaseModel):
    """上游测试基础模型"""
    advertiser_id: int = Field(..., description="广告主ID")
    offer_id: int = Field(..., description="平台内的Offer ID")


class AdvertiserTestCreate(AdvertiserTestBase):
    """创建上游测试记录"""
    pass


class AdvertiserTestResponse(AdvertiserTestBase):
    """上游测试响应"""
    id: int
    advertiser_name: Optional[str] = None
    advertiser_offer_id: Optional[str] = None
    offer_name: Optional[str] = None
    price: Optional[float] = None
    country: Optional[str] = None
    click_id: Optional[str] = None
    click_url: Optional[str] = None
    test_time: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AffiliateTestBase(BaseModel):
    """下游测试基础模型"""
    publisher_id: int = Field(..., description="渠道ID")
    click_id: str = Field(..., description="下游提供的Click ID")
    offer_id: int = Field(..., description="Offer ID")


class AffiliateTestCreate(AffiliateTestBase):
    """创建下游测试记录"""
    pass


class AffiliateTestResponse(AffiliateTestBase):
    """下游测试响应"""
    id: int
    offer_name: Optional[str] = None
    price: Optional[float] = None
    country: Optional[str] = None
    platform: Optional[str] = None
    postback_time: Optional[datetime] = None
    status: Optional[str] = None
    affiliate_return_content: Optional[str] = None
    created_at: datetime
    # 关联信息
    publisher_name: Optional[str] = None

    class Config:
        from_attributes = True

