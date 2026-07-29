"""扣量（Discount）配置 Pydantic 数据模型。

定义按 Offer 或渠道维度的转化扣量比例（0-100%），
用于控制向下游渠道通知的转化数量。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import Field, ConfigDict

from app.schemas.base import BaseSchema


class OfferDiscountBase(BaseSchema):
    """
    扣量配置基础模型
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    discount_type: str = Field(..., description="扣量类型：offer/channel")
    offer_id: Optional[int] = Field(None, description="Offer ID（如果是offer类型）")
    publisher_id: int = Field(..., description="渠道ID")
    discount_ratio: Decimal = Field(..., ge=0, le=100, description="扣量比例（0-100）")
    is_active: bool = Field(True, description="是否激活")


class OfferDiscountCreate(OfferDiscountBase):
    """
    创建扣量配置
    
    创建请求体：包含新建记录所需字段，提交前由 Pydantic 自动校验类型与取值范围。
    """
    pass


class OfferDiscountUpdate(BaseSchema):
    """
    更新扣量配置
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    discount_type: Optional[str] = Field(None, description="扣量类型")
    offer_id: Optional[int] = Field(None, description="Offer ID")
    publisher_id: Optional[int] = Field(None, description="渠道ID")
    discount_ratio: Optional[Decimal] = Field(None, ge=0, le=100, description="扣量比例")
    is_active: Optional[bool] = Field(None, description="是否激活")


class OfferDiscountResponse(OfferDiscountBase):
    """
    扣量配置响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    id: int
    created_at: datetime
    updated_at: datetime
    # 关联信息
    offer_name: Optional[str] = None
    publisher_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
