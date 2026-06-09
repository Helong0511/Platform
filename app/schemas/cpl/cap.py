"""Cap（转化上限）配置 Pydantic 数据模型。

支持按广告主+Offer 或单 Offer 维度设置每日/总转化上限，
可进一步细化到指定渠道。用于控制上游与下游的转化放量。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class OfferCapBase(BaseModel):
    """
    Cap配置基础模型
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    cap_type: str = Field(..., description="Cap类型：advertiser_offer/offer")
    advertiser_id: Optional[int] = Field(None, description="广告主ID（如果是advertiser_offer类型）")
    offer_id: int = Field(..., description="Offer ID")
    publisher_id: Optional[int] = Field(None, description="渠道ID（如果为空，表示所有渠道）")
    daily_cap: Optional[int] = Field(None, ge=0, description="每日Cap")
    total_cap: Optional[int] = Field(None, ge=0, description="总Cap")
    is_active: bool = Field(True, description="是否激活")


class OfferCapCreate(OfferCapBase):
    """
    创建Cap配置
    
    创建请求体：包含新建记录所需字段，提交前由 Pydantic 自动校验类型与取值范围。
    """
    pass


class OfferCapUpdate(BaseModel):
    """
    更新Cap配置
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    cap_type: Optional[str] = Field(None, description="Cap类型")
    advertiser_id: Optional[int] = Field(None, description="广告主ID")
    offer_id: Optional[int] = Field(None, description="Offer ID")
    publisher_id: Optional[int] = Field(None, description="渠道ID")
    daily_cap: Optional[int] = Field(None, ge=0, description="每日Cap")
    total_cap: Optional[int] = Field(None, ge=0, description="总Cap")
    is_active: Optional[bool] = Field(None, description="是否激活")


class OfferCapResponse(OfferCapBase):
    """
    Cap配置响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    id: int
    current_daily_count: int
    current_total_count: int
    cap_start_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # 关联信息
    offer_name: Optional[str] = None
    advertiser_name: Optional[str] = None
    publisher_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
