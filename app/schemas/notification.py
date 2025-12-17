"""
通知配置和通知记录的 Schema
"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import List, Optional
import json


# ==================== 客户通知配置 ====================

class ClientNotificationConfigBase(BaseModel):
    """客户通知配置基础模型"""
    notification_enabled: bool = Field(True, description="是否启用通知")
    notify_on_conversion: bool = Field(True, description="转化时通知")
    notify_on_high_value: bool = Field(False, description="高价值转化通知")
    high_value_threshold: Optional[float] = Field(None, ge=0, description="高价值阈值")
    notify_channels: Optional[str] = Field(None, description="通知渠道（JSON格式：[\"telegram\", \"email\", \"sms\"]）")
    telegram_chat_id: Optional[str] = Field(None, max_length=100, description="Telegram Chat ID")
    email_address: Optional[str] = Field(None, max_length=255, description="邮箱地址")
    phone_number: Optional[str] = Field(None, max_length=20, description="手机号")
    notification_frequency: str = Field("realtime", description="通知频率：realtime, hourly, daily")

    @field_validator('notify_channels')
    @classmethod
    def validate_notify_channels(cls, v):
        """验证通知渠道格式"""
        if v is None:
            return v
        try:
            channels = json.loads(v) if isinstance(v, str) else v
            if not isinstance(channels, list):
                raise ValueError("notify_channels 必须是数组格式")
            valid_channels = ['telegram', 'email', 'sms']
            for channel in channels:
                if channel not in valid_channels:
                    raise ValueError(f"不支持的通知渠道: {channel}，支持: {valid_channels}")
            return json.dumps(channels) if isinstance(v, str) else json.dumps(channels)
        except json.JSONDecodeError:
            raise ValueError("notify_channels 必须是有效的 JSON 格式")

    @field_validator('notification_frequency')
    @classmethod
    def validate_notification_frequency(cls, v):
        """验证通知频率"""
        valid_frequencies = ['realtime', 'hourly', 'daily']
        if v not in valid_frequencies:
            raise ValueError(f"notification_frequency 必须是: {valid_frequencies}")
        return v


class ClientNotificationConfigCreate(ClientNotificationConfigBase):
    """创建客户通知配置"""
    client_id: int = Field(..., description="客户ID")


class ClientNotificationConfigUpdate(ClientNotificationConfigBase):
    """更新客户通知配置"""
    pass


class ClientNotificationConfigResponse(ClientNotificationConfigBase):
    """客户通知配置响应"""
    id: int
    client_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== 产品通知配置 ====================

class ProductNotificationConfigBase(BaseModel):
    """产品通知配置基础模型"""
    notification_enabled: bool = Field(True, description="是否启用通知")
    notify_on_conversion: bool = Field(True, description="转化时通知")
    notify_on_high_value: bool = Field(False, description="高价值转化通知")
    high_value_threshold: Optional[float] = Field(None, ge=0, description="高价值阈值")
    notify_channels: Optional[str] = Field(None, description="通知渠道（JSON格式：[\"telegram\", \"email\", \"sms\"]）")
    telegram_chat_id: Optional[str] = Field(None, max_length=100, description="Telegram Chat ID")
    email_address: Optional[str] = Field(None, max_length=255, description="邮箱地址")
    phone_number: Optional[str] = Field(None, max_length=20, description="手机号")
    notification_frequency: str = Field("realtime", description="通知频率：realtime, hourly, daily")

    @field_validator('notify_channels')
    @classmethod
    def validate_notify_channels(cls, v):
        """验证通知渠道格式"""
        if v is None:
            return v
        try:
            channels = json.loads(v) if isinstance(v, str) else v
            if not isinstance(channels, list):
                raise ValueError("notify_channels 必须是数组格式")
            valid_channels = ['telegram', 'email', 'sms']
            for channel in channels:
                if channel not in valid_channels:
                    raise ValueError(f"不支持的通知渠道: {channel}，支持: {valid_channels}")
            return json.dumps(channels) if isinstance(v, str) else json.dumps(channels)
        except json.JSONDecodeError:
            raise ValueError("notify_channels 必须是有效的 JSON 格式")

    @field_validator('notification_frequency')
    @classmethod
    def validate_notification_frequency(cls, v):
        """验证通知频率"""
        valid_frequencies = ['realtime', 'hourly', 'daily']
        if v not in valid_frequencies:
            raise ValueError(f"notification_frequency 必须是: {valid_frequencies}")
        return v


class ProductNotificationConfigCreate(ProductNotificationConfigBase):
    """创建产品通知配置"""
    product_id: int = Field(..., description="产品ID")


class ProductNotificationConfigUpdate(ProductNotificationConfigBase):
    """更新产品通知配置"""
    pass


class ProductNotificationConfigResponse(ProductNotificationConfigBase):
    """产品通知配置响应"""
    id: int
    product_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== 通知记录 ====================

class PostbackNotificationResponse(BaseModel):
    """通知记录响应"""
    id: int
    conversion_id: int
    client_id: Optional[int] = None
    product_id: Optional[int] = None
    notification_type: Optional[str] = None
    notification_channel: str
    notification_status: str
    notification_message: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PostbackNotificationListResponse(BaseModel):
    """通知记录列表响应"""
    data: List[PostbackNotificationResponse]
    total: int
    page: int
    page_size: int

