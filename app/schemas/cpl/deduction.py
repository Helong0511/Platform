"""
转化扣减配置 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ConversionDeductionConfigBase(BaseModel):
    """扣减配置基础模型"""
    level: str = Field(..., description="配置层级：advertiser/offer/publisher")
    target_id: int = Field(..., description="配置对象ID（广告主ID/Offer ID/渠道ID）")
    enable_volume_deduction: bool = Field(False, description="是否启用按比例扣量")
    volume_deduction_ratio: float = Field(0.0, ge=0, le=1, description="按比例扣量比例（0-1，如0.10表示扣量10%）")
    deduction_strategy: str = Field("random", description="扣减策略：random/proportional/round_robin")
    enable_amount_deduction: bool = Field(False, description="是否启用按比例扣金额")
    amount_deduction_ratio: float = Field(0.0, ge=0, le=1, description="按比例扣金额比例（0-1，如0.10表示扣金额10%）")
    priority: int = Field(0, ge=0, description="优先级（数字越大优先级越高）")
    is_active: bool = Field(True, description="是否激活")


class ConversionDeductionConfigCreate(ConversionDeductionConfigBase):
    """创建扣减配置"""
    pass


class ConversionDeductionConfigUpdate(BaseModel):
    """更新扣减配置"""
    level: Optional[str] = Field(None, description="配置层级")
    target_id: Optional[int] = Field(None, description="配置对象ID")
    enable_volume_deduction: Optional[bool] = Field(None, description="是否启用按比例扣量")
    volume_deduction_ratio: Optional[float] = Field(None, ge=0, le=1, description="按比例扣量比例")
    deduction_strategy: Optional[str] = Field(None, description="扣减策略")
    enable_amount_deduction: Optional[bool] = Field(None, description="是否启用按比例扣金额")
    amount_deduction_ratio: Optional[float] = Field(None, ge=0, le=1, description="按比例扣金额比例")
    priority: Optional[int] = Field(None, ge=0, description="优先级")
    is_active: Optional[bool] = Field(None, description="是否激活")


class ConversionDeductionConfigResponse(ConversionDeductionConfigBase):
    """扣减配置响应"""
    id: int
    advertiser_id: Optional[int] = None
    offer_id: Optional[int] = None
    publisher_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    # 关联信息
    target_name: Optional[str] = None
    advertiser_name: Optional[str] = None
    offer_name: Optional[str] = None
    publisher_name: Optional[str] = None

    class Config:
        from_attributes = True


class ConversionDeductionLogResponse(BaseModel):
    """扣减日志响应"""
    id: int
    conversion_id: Optional[int] = None
    click_id: Optional[str] = None
    advertiser_id: Optional[int] = None
    offer_id: Optional[int] = None
    publisher_id: Optional[int] = None
    original_volume: int
    original_amount: float
    deducted_volume: int
    deducted_amount: float
    final_volume: int
    final_amount: float
    deduction_config_id: Optional[int] = None
    volume_deduction_ratio: Optional[float] = None
    amount_deduction_ratio: Optional[float] = None
    deduction_strategy: Optional[str] = None
    deduction_reason: Optional[str] = None
    created_at: datetime
    # 关联信息
    advertiser_name: Optional[str] = None
    offer_name: Optional[str] = None
    publisher_name: Optional[str] = None

    class Config:
        from_attributes = True


class DeductionStatsResponse(BaseModel):
    """扣减统计响应"""
    original_volume: int = 0
    deducted_volume: int = 0
    final_volume: int = 0
    volume_deduction_ratio: float = 0.0
    original_amount: float = 0.0
    deducted_amount: float = 0.0
    final_amount: float = 0.0
    amount_deduction_ratio: float = 0.0
    items: list = []

