"""Postback 回调 IP 白名单 Schema。

用于限制仅允许白名单内 IP 向平台发送转化 Postback，支持单条与批量创建。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
import ipaddress
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PostbackIpWhitelistCreate(BaseModel):
    """创建单条 Postback IP 白名单（详见字段 Field description）。"""
    ip_address: str = Field(..., description="IP地址（支持IPv4和IPv6）")
    description: Optional[str] = Field(None, max_length=255, description="IP地址描述/备注")
    is_active: bool = Field(True, description="是否启用")

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, v):
        """校验 IPv4/IPv6 地址格式（详见字段 Field description）。"""
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError as e:
            raise ValueError(f"无效的 IP 地址格式: {v}") from e


class PostbackIpWhitelistUpdate(BaseModel):
    """
    更新 Postback IP 白名单条目。

    ip_address、description、is_active 均可选；更新 IP 时重新校验 IPv4/IPv6 格式。
    """
    ip_address: Optional[str] = Field(None, description="IP地址（支持IPv4和IPv6）")
    description: Optional[str] = Field(None, max_length=255, description="IP地址描述/备注")
    is_active: Optional[bool] = Field(None, description="是否启用")

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, v):
        """更新时可选；有值则校验 IP 格式（详见字段 Field description）。"""
        if v is None:
            return v
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError as e:
            raise ValueError(f"无效的 IP 地址格式: {v}") from e


class PostbackIpWhitelistResponse(BaseModel):
    """白名单条目 API 响应，含 id、IP、备注、启用状态及创建/更新时间。（详见字段 Field description）。"""
    id: int
    ip_address: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PostbackIpWhitelistBatchCreate(BaseModel):
    """批量创建白名单（最多 100 个 IP，自动去重）（详见字段 Field description）。"""
    ip_addresses: List[str] = Field(..., description="IP地址列表")
    description: Optional[str] = Field(None, max_length=255)
    is_active: bool = Field(True)

    @field_validator("ip_addresses")
    @classmethod
    def validate_ip_addresses(cls, v):
        """批量校验、去重，单次最多 100 个有效 IP（详见字段 Field description）。"""
        if not v:
            raise ValueError("IP地址列表不能为空")
        if len(v) > 100:
            raise ValueError("一次最多只能添加100个IP地址")
        validated = []
        for ip in v:
            trimmed = (ip or "").strip()
            if not trimmed:
                continue
            ipaddress.ip_address(trimmed)
            validated.append(trimmed)
        if not validated:
            raise ValueError("没有有效的IP地址")
        return list(dict.fromkeys(validated))


class PostbackIpWhitelistBatchCreateResponse(BaseModel):
    """
    批量创建白名单结果。

    返回 success_count/failed_count、已成功创建的 created_items 及失败明细 failed_items。
    """
    success_count: int
    failed_count: int
    total_count: int
    created_items: List[PostbackIpWhitelistResponse]
    failed_items: List[dict] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
