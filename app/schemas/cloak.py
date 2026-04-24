"""
斗篷配置相关 Schema
"""
import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CloakConfigBase(BaseModel):
    """斗篷配置基础模型"""
    cloak_name: str = Field(..., min_length=1, max_length=100, description="斗篷名称（如 master）")
    pixel_id: str = Field(..., min_length=1, max_length=50, description="主像素ID")
    access_token: str = Field(..., min_length=1, max_length=500, description="主像素Token")
    backup_pixel_id: Optional[str] = Field(None, max_length=50, description="备份像素ID")
    backup_access_token: Optional[str] = Field(None, max_length=500, description="备份像素Token")
    is_enabled: bool = Field(True, description="是否启用")

    @field_validator("cloak_name")
    @classmethod
    def validate_cloak_name(cls, value: str) -> str:
        value = value.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", value):
            raise ValueError("斗篷名称仅支持字母、数字、下划线和中划线")
        return value

    @field_validator("pixel_id")
    @classmethod
    def validate_pixel_id(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit():
            raise ValueError("像素ID必须为数字")
        return value

    @field_validator("backup_pixel_id")
    @classmethod
    def validate_backup_pixel_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if value == "":
            return None
        if not value.isdigit():
            raise ValueError("备份像素ID必须为数字")
        return value

    @field_validator("access_token", "backup_access_token")
    @classmethod
    def trim_tokens(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CloakConfigCreate(CloakConfigBase):
    """创建斗篷配置"""
    pass


class CloakConfigUpdate(BaseModel):
    """更新斗篷配置"""
    cloak_name: Optional[str] = Field(None, min_length=1, max_length=100, description="斗篷名称（如 master）")
    pixel_id: Optional[str] = Field(None, min_length=1, max_length=50, description="主像素ID")
    access_token: Optional[str] = Field(None, min_length=1, max_length=500, description="主像素Token")
    backup_pixel_id: Optional[str] = Field(None, max_length=50, description="备份像素ID")
    backup_access_token: Optional[str] = Field(None, max_length=500, description="备份像素Token")
    is_enabled: Optional[bool] = Field(None, description="是否启用")

    @field_validator("cloak_name")
    @classmethod
    def validate_cloak_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", value):
            raise ValueError("斗篷名称仅支持字母、数字、下划线和中划线")
        return value

    @field_validator("pixel_id")
    @classmethod
    def validate_pixel_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value.isdigit():
            raise ValueError("像素ID必须为数字")
        return value

    @field_validator("backup_pixel_id")
    @classmethod
    def validate_backup_pixel_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if value == "":
            return None
        if not value.isdigit():
            raise ValueError("备份像素ID必须为数字")
        return value

    @field_validator("access_token", "backup_access_token")
    @classmethod
    def trim_tokens(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CloakConfigResponse(CloakConfigBase):
    """斗篷配置响应"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TestCloakReportRequest(BaseModel):
    """测试上报请求"""
    event: str = Field("ViewContent", description="事件类型")
    adsid: str = Field("test-fbclid-123456", min_length=1, max_length=500, description="测试广告事件ID")
    email: str = Field("test@example.com", min_length=1, max_length=255, description="测试邮箱")
    phone: str = Field("13800138000", min_length=1, max_length=50, description="测试手机号")
    ip: str = Field("127.0.0.1", min_length=1, max_length=50, description="测试IP地址")
    ua: str = Field("Mozilla/5.0", min_length=1, description="测试UA")
    use_hash: bool = Field(True, description="是否使用哈希")
