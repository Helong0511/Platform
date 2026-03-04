"""
扣量配置 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class OfferDiscountBase(BaseModel):
    """扣量配置基础模型"""
    discount_type: str = Field(..., description="扣量类型：offer/channel")
    offer_id: Optional[int] = Field(None, description="Offer ID（如果是offer类型）")
    publisher_id: int = Field(..., description="渠道ID")
    discount_ratio: float = Field(..., ge=0, le=100, description="扣量比例（0-100）")
    is_active: bool = Field(True, description="是否激活")


class OfferDiscountCreate(OfferDiscountBase):
    """创建扣量配置"""
    pass


class OfferDiscountUpdate(BaseModel):
    """更新扣量配置"""
    discount_type: Optional[str] = Field(None, description="扣量类型")
    offer_id: Optional[int] = Field(None, description="Offer ID")
    publisher_id: Optional[int] = Field(None, description="渠道ID")
    discount_ratio: Optional[float] = Field(None, ge=0, le=100, description="扣量比例")
    is_active: Optional[bool] = Field(None, description="是否激活")


class OfferDiscountResponse(OfferDiscountBase):
    """扣量配置响应"""
    id: int
    created_at: datetime
    updated_at: datetime
    # 关联信息
    offer_name: Optional[str] = None
    publisher_name: Optional[str] = None

    class Config:
        from_attributes = True

