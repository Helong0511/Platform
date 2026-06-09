"""广告主（上游）Pydantic 数据模型。

定义广告主创建/更新/响应的字段校验，包括名称、联系方式、
自定义参数及激活状态等基础信息。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class AdvertiserBase(BaseModel):
    """
    广告主基础模型
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    advertiser_name: str = Field(..., max_length=100, description="广告主名称")
    email: Optional[str] = Field(None, max_length=255, description="邮箱（可选）")
    mobile: Optional[str] = Field(None, max_length=20, description="手机号")
    advertiser_params: Optional[str] = Field(None, description="广告主参数")
    is_active: bool = Field(True, description="是否激活")


class AdvertiserCreate(AdvertiserBase):
    """
    创建广告主
    
    创建请求体：包含新建记录所需字段，提交前由 Pydantic 自动校验类型与取值范围。
    """
    pass


class AdvertiserUpdate(BaseModel):
    """
    更新广告主
    
    更新请求体：字段均为可选，客户端仅提交需要修改的列。
    """
    advertiser_name: Optional[str] = Field(None, max_length=100, description="广告主名称")
    email: Optional[str] = Field(None, max_length=255, description="邮箱")
    mobile: Optional[str] = Field(None, max_length=20, description="手机号")
    advertiser_params: Optional[str] = Field(None, description="广告主参数")
    is_active: Optional[bool] = Field(None, description="是否激活")


class AdvertiserResponse(AdvertiserBase):
    """
    广告主响应
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
