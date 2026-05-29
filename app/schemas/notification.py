"""
通知配置和通知记录的 Schema
"""
import json
import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, ConfigDict


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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


# ==================== 管理员通知配置 ====================

class AdminNotificationConfigBase(BaseModel):
    """管理员通知配置基础模型"""
    telegram_enabled: bool = Field(True, description="是否启用 Telegram 通知")
    telegram_chat_id: Optional[str] = Field(None, max_length=100, description="管理员 Telegram Chat ID")
    notify_all_conversions: bool = Field(True, description="通知所有转化")
    notify_forward_failure: bool = Field(True, description="通知转发失败")
    notify_forward_success: bool = Field(False, description="通知转发成功（可选）")
    notify_system_errors: bool = Field(True, description="通知系统异常")
    notify_statistics: bool = Field(False, description="定时统计通知")
    statistics_frequency: str = Field("hourly", description="统计频率：hourly, daily")

    @field_validator('statistics_frequency')
    @classmethod
    def validate_statistics_frequency(cls, v):
        """验证统计频率"""
        valid_frequencies = ['hourly', 'daily']
        if v not in valid_frequencies:
            raise ValueError(f"statistics_frequency 必须是: {valid_frequencies}")
        return v

    @field_validator('telegram_chat_id')
    @classmethod
    def validate_telegram_chat_id(cls, v):
        """验证 Telegram Chat ID 格式"""
        if v is None or v == "":
            return v
        # Chat ID 可以是数字或负数（群组ID通常是负数）
        if not re.match(r'^-?\d+$', v):
            raise ValueError("Telegram Chat ID 必须是数字（可以是负数）")
        return v


class AdminNotificationConfigCreate(AdminNotificationConfigBase):
    """创建管理员通知配置"""
    pass


class AdminNotificationConfigUpdate(AdminNotificationConfigBase):
    """更新管理员通知配置"""
    pass


class AdminNotificationConfigResponse(AdminNotificationConfigBase):
    """管理员通知配置响应模型"""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ==================== 管理员通知测试请求 ====================

class TestConnectionRequest(BaseModel):
    """测试连接请求模型"""
    telegram_chat_id: str = Field(..., description="Telegram Chat ID", max_length=100)

    @field_validator('telegram_chat_id')
    @classmethod
    def validate_telegram_chat_id(cls, v):
        """验证 Telegram Chat ID 格式"""
        if not v or not v.strip():
            raise ValueError("telegram_chat_id 不能为空")
        # Chat ID 可以是数字或负数（群组ID通常是负数）
        if not re.match(r'^-?\d+$', v):
            raise ValueError("Telegram Chat ID 必须是数字（可以是负数）")
        return v.strip()


class TestMessageRequest(BaseModel):
    """测试消息请求模型"""
    telegram_chat_id: str = Field(..., description="Telegram Chat ID", max_length=100)
    message_type: str = Field("conversion", description="消息类型：conversion, forward_failure, system_error")

    @field_validator('telegram_chat_id')
    @classmethod
    def validate_telegram_chat_id(cls, v):
        """验证 Telegram Chat ID 格式"""
        if not v or not v.strip():
            raise ValueError("telegram_chat_id 不能为空")
        # Chat ID 可以是数字或负数（群组ID通常是负数）
        if not re.match(r'^-?\d+$', v):
            raise ValueError("Telegram Chat ID 必须是数字（可以是负数）")
        return v.strip()

    @field_validator('message_type')
    @classmethod
    def validate_message_type(cls, v):
        """验证消息类型"""
        valid_types = ['conversion', 'forward_failure', 'system_error']
        if v not in valid_types:
            raise ValueError(f"message_type 必须是: {valid_types}")
        return v


# ==================== 通知记录 ====================

class PostbackNotificationResponse(BaseModel):
    """通知记录响应"""
    id: int
    conversion_id: Optional[int] = None  # 汇总通知时为 None
    client_id: Optional[int] = None
    product_id: Optional[int] = None
    publisher_id: Optional[int] = None
    notification_type: Optional[str] = None  # conversion, high_value, error, forward, summary_hourly, summary_daily
    notification_channel: str
    notification_status: str
    notification_message: Optional[str] = None
    error_message: Optional[str] = None
    auto_notify: bool = False
    postback_url: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PostbackNotificationListResponse(BaseModel):
    """通知记录列表响应"""
    data: List[PostbackNotificationResponse]
    total: int
    page: int
    page_size: int
