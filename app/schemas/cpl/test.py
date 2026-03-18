"""
测试记录 Schema
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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
