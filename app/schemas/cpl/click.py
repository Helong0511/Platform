"""
点击记录 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ClickResponse(BaseModel):
    """点击记录响应"""
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

    class Config:
        from_attributes = True

