"""Postback IP 白名单 Schema。"""
import ipaddress
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, validator, ConfigDict


class PostbackIpWhitelistCreate(BaseModel):
    ip_address: str = Field(..., description="IP地址（支持IPv4和IPv6）")
    description: Optional[str] = Field(None, max_length=255, description="IP地址描述/备注")
    is_active: bool = Field(True, description="是否启用")

    @validator("ip_address")
    def validate_ip_address(cls, v):
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError as e:
            raise ValueError(f"无效的 IP 地址格式: {v}") from e


class PostbackIpWhitelistUpdate(BaseModel):
    ip_address: Optional[str] = Field(None, description="IP地址（支持IPv4和IPv6）")
    description: Optional[str] = Field(None, max_length=255, description="IP地址描述/备注")
    is_active: Optional[bool] = Field(None, description="是否启用")

    @validator("ip_address")
    def validate_ip_address(cls, v):
        if v is None:
            return v
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError as e:
            raise ValueError(f"无效的 IP 地址格式: {v}") from e


class PostbackIpWhitelistResponse(BaseModel):
    id: int
    ip_address: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PostbackIpWhitelistBatchCreate(BaseModel):
    ip_addresses: List[str] = Field(..., description="IP地址列表")
    description: Optional[str] = Field(None, max_length=255)
    is_active: bool = Field(True)

    @validator("ip_addresses")
    def validate_ip_addresses(cls, v):
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
    success_count: int
    failed_count: int
    total_count: int
    created_items: List[PostbackIpWhitelistResponse]
    failed_items: List[dict] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
