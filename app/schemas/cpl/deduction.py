"""
转化扣减配置 Schema

重构说明:
- 添加更详细的字段验证
- 改进文档字符串
- 添加示例值
"""
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ConversionDeductionConfigBase(BaseModel):
    """
    扣减配置基础模型
    
    支持三种配置层级:
    - advertiser: 广告主级别配置（适用于该广告主下所有Offer）
    - offer: Offer级别配置（适用于特定Offer，优先级最高）
    - publisher: 渠道级别配置（适用于该渠道的所有转化，优先级最低）
    
    扣减策略:
    - random: 随机扣减，确保总体比例准确
    - proportional: 按固定间隔扣量（每N个扣1个）
    - round_robin: 轮询方式扣量
    """
    level: Literal['advertiser', 'offer', 'publisher'] = Field(
        ...,
        description="配置层级：advertiser（广告主）/offer（Offer）/publisher（渠道）",
        examples=['offer']
    )
    target_id: int = Field(
        ...,
        ge=1,
        description="配置对象ID（广告主ID/Offer ID/渠道ID）",
        examples=[100]
    )
    enable_volume_deduction: bool = Field(
        False,
        description="是否启用按比例扣量（扣量后转化不保存到主表）",
        examples=[True]
    )
    volume_deduction_ratio: float = Field(
        0.0,
        ge=0,
        le=1,
        description="按比例扣量比例（0-1，如0.10表示扣量10%）",
        examples=[0.1]
    )
    deduction_strategy: Literal['random', 'proportional', 'round_robin'] = Field(
        "random",
        description="扣减策略：random（随机）/proportional（按比例）/round_robin（轮询）",
        examples=['random']
    )
    enable_amount_deduction: bool = Field(
        False,
        description="是否启用按比例扣金额（扣金额后转化仍保存到主表）",
        examples=[True]
    )
    amount_deduction_ratio: float = Field(
        0.0,
        ge=0,
        le=1,
        description="按比例扣金额比例（0-1，如0.10表示扣金额10%）",
        examples=[0.05]
    )
    priority: int = Field(
        0,
        ge=0,
        description="优先级（数字越大优先级越高，同一层级内使用）",
        examples=[0]
    )
    is_active: bool = Field(
        True,
        description="是否激活（只有激活的配置才会被使用）",
        examples=[True]
    )

    @field_validator('volume_deduction_ratio', 'amount_deduction_ratio')
    @classmethod
    def validate_ratio(cls, v: float) -> float:
        """验证比例值"""
        if v < 0 or v > 1:
            raise ValueError('比例必须在0-1之间')
        return v


class ConversionDeductionConfigCreate(ConversionDeductionConfigBase):
    """
    创建扣减配置
    
    注意:
    - 至少需要启用一种扣减方式（扣量或扣金额）
    - 同一层级同一对象只能有一个激活的配置
    - 如果启用扣量，volume_deduction_ratio必须大于0
    - 如果启用扣金额，amount_deduction_ratio必须大于0
    """

    @model_validator(mode='after')
    def validate_at_least_one_enabled(self):
        """验证至少启用一种扣减方式"""
        if not self.enable_volume_deduction and not self.enable_amount_deduction:
            raise ValueError('请至少启用一种扣减方式（扣量或扣金额）')

        # 验证如果启用扣量，比例必须大于0
        if self.enable_volume_deduction and self.volume_deduction_ratio <= 0:
            raise ValueError('启用扣量时，扣量比例必须大于0')

        # 验证如果启用扣金额，比例必须大于0
        if self.enable_amount_deduction and self.amount_deduction_ratio <= 0:
            raise ValueError('启用扣金额时，扣金额比例必须大于0')

        return self


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


class BatchUpdateStatusRequest(BaseModel):
    """批量更新状态请求"""
    config_ids: list[int] = Field(..., min_length=1, description="配置ID列表")
    is_active: bool = Field(..., description="是否激活")


class BatchDeleteRequest(BaseModel):
    """批量删除请求"""
    config_ids: list[int] = Field(..., min_length=1, description="配置ID列表")
