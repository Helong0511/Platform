"""
Postback 相关的 Schema 定义
用于统一处理各平台的 postback 回调数据
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


# ====== 请求模型 ======
class PostbackRequest(BaseModel):
    """通用 Postback 请求模型（用于POST请求）"""
    # 基础字段（各平台通用）
    conversion_id: Optional[str] = Field(None, description="转化ID（各平台唯一标识）")
    event_name: Optional[str] = Field(None, description="事件名称")
    event_value: Optional[float] = Field(None, description="事件价值")
    payout: Optional[float] = Field(None, description="支付金额")
    
    # 设备信息
    devad_id: Optional[str] = Field(None, description="设备广告ID")
    os: Optional[str] = Field(None, description="操作系统")
    carrier: Optional[str] = Field(None, description="运营商")
    ip: Optional[str] = Field(None, description="IP地址")
    gid: Optional[str] = Field(None, description="渠道ID")
    
    # 关联信息
    product_id: Optional[int] = Field(None, description="产品ID")
    client_id: Optional[int] = Field(None, description="客户ID")
    
    # 允许其他字段（用于存储平台特定的字段）
    class Config:
        extra = "allow"


# ====== 响应模型 ======
class PostbackResponse(BaseModel):
    """Postback 响应模型"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    conversion_id: Optional[str] = Field(None, description="转化ID")
    platform: Optional[str] = Field(None, description="平台名称")


# ====== 查询和统计模型 ======
class PostbackConversionResponse(BaseModel):
    """Postback 转化记录响应模型"""
    id: int
    platform: str
    conversion_id: str
    event_name: Optional[str]
    event_value: Optional[float]
    original_payout: Optional[float] = Field(None, description="原始支付金额（PO）")
    payout: Optional[float] = Field(None, description="扣后支付金额（PO(扣)），考虑下游PO限制后的实际转发金额")
    devad_id: Optional[str]
    os: Optional[str]
    carrier: Optional[str]
    ip: Optional[str]
    gid: Optional[str]
    product_id: Optional[int]
    client_id: Optional[int]
    product_name: Optional[str] = Field(None, description="产品名称")
    client_name: Optional[str] = Field(None, description="客户名称")
    # 点击记录关联信息（通过 conversion_id = clicks.click_id 关联）
    click_id: Optional[str] = Field(None, description="关联的Click ID（等于conversion_id）")
    click_offer_id: Optional[int] = Field(None, description="点击记录的Offer ID")
    click_publisher_id: Optional[int] = Field(None, description="点击记录的渠道ID")
    click_advertiser_id: Optional[int] = Field(None, description="点击记录的广告主ID")
    click_offer_name: Optional[str] = Field(None, description="点击记录的Offer名称")
    click_publisher_name: Optional[str] = Field(None, description="点击记录的渠道名称")
    click_advertiser_name: Optional[str] = Field(None, description="点击记录的广告主名称")
    click_time: Optional[datetime] = Field(None, description="点击时间")
    # gid 关联的渠道信息（gid 字段是渠道ID）
    gid_publisher_id: Optional[int] = Field(None, description="gid字段关联的渠道ID")
    gid_publisher_name: Optional[str] = Field(None, description="gid字段关联的渠道名称")
    created_at: datetime
    notification_count: Optional[int] = Field(0, description="成功发送的通知记录数量（只统计 status='sent' 的记录）")
    
    class Config:
        from_attributes = True


class PostbackStatsResponse(BaseModel):
    """Postback 统计响应模型"""
    platform: str = Field(..., description="平台名称")
    total_conversions: int = Field(..., description="总转化数")
    total_original_payout: Optional[float] = Field(None, description="原始总支付金额（PO）")
    total_payout: float = Field(..., description="扣后总支付金额（PO(扣)）")
    total_event_value: float = Field(..., description="总事件价值")
    unique_events: int = Field(..., description="唯一事件数")
    date_range: Optional[Dict[str, str]] = Field(None, description="日期范围")


class PostbackQueryParams(BaseModel):
    """Postback 查询参数模型"""
    platform: Optional[str] = Field(None, description="平台名称")
    product_id: Optional[int] = Field(None, description="产品ID")
    client_id: Optional[int] = Field(None, description="客户ID")
    event_name: Optional[str] = Field(None, description="事件名称")
    start_date: Optional[str] = Field(None, description="起始日期（YYYY-MM-DD）")
    end_date: Optional[str] = Field(None, description="结束日期（YYYY-MM-DD）")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


class PostbackForwardLogResponse(BaseModel):
    """Postback 下游转发日志响应模型"""
    id: int
    conversion_id: int
    product_id: Optional[int]
    publisher_id: Optional[int] = Field(None, description="渠道ID（转发到渠道时使用）")
    downstream_url: str
    request_method: str
    request_data: Optional[str]
    request_params: Optional[str]
    response_status: Optional[int]
    response_body: Optional[str]
    success: bool
    error_message: Optional[str]
    retry_count: int
    created_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True

