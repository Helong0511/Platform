"""点击记录 Pydantic 响应模型。

序列化 clicks 表数据及关联的 Offer、渠道、广告主名称，
供管理端点击日志列表与详情展示使用。

说明：CPL 业务字段模型，与数据库表及前端表单校验保持一致。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ClickResponse(BaseModel):
    """
    点击记录响应
    
    继承 BaseModel。单条或列表项的 API 响应数据结构。
    """
    id: int
    click_id: str
    offer_id: Optional[int] = None
    publisher_id: Optional[int] = None
    advertiser_id: Optional[int] = None
    click_time: datetime
    ip: Optional[str] = None
    device: Optional[str] = None
    country: Optional[str] = None
    conversion_id: Optional[int] = None
    created_at: datetime
    # 关联信息
    offer_name: Optional[str] = None
    publisher_name: Optional[str] = None
    advertiser_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
