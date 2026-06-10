"""
第三方上报日志 ORM 模型。
"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Enum, Text, Index, \
    UniqueConstraint, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from app.core.utils import get_app_now_naive
from app.models.base import Base, pwd_context, UserRole

class ThirdPartyReportLog(Base):
    """
    第三方上报日志模型
    
    用于记录所有第三方广告上报的详细信息，包括成功和失败的情况
    支持高并发写入，包含完整的上报参数、状态和时间信息
    
    表名: third_party_report_logs
    """
    __tablename__ = "third_party_report_logs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='日志ID')
    
    # 上报来源
    source = Column(String(50), nullable=False, index=True, comment='上报来源：short_link/斗篷点击, postback/转化回调')
    
    # 上报参数
    adsid = Column(String(500), nullable=False, index=True, comment='广告事件ID')
    event = Column(String(50), nullable=False, index=True, comment='事件类型：ViewContent, Purchase')
    conversion_id = Column(String(255), nullable=True, index=True, comment='转化ID')
    use_hash = Column(Boolean, default=True, nullable=False, comment='是否对email、ip、phone进行哈希处理：True=哈希，False=不哈希')
    email = Column(String(255), nullable=True, comment='邮箱（原始值）')
    ip = Column(String(50), nullable=True, comment='IP地址（原始值）')
    phone = Column(String(50), nullable=True, comment='手机号（原始值）')
    ua = Column(Text, nullable=True, comment='用户代理')
    currency = Column(String(10), nullable=True, comment='货币类型')
    amount = Column(Float, nullable=True, comment='支付金额')
    report_params = Column(Text, nullable=True, comment='完整上报参数（JSON格式）')

    
    # 上报状态
    status = Column(String(20), nullable=False, index=True, comment='上报状态：pending, success, failed')
    attempt_count = Column(Integer, default=0, comment='尝试次数')
    max_attempts = Column(Integer, default=3, comment='最大尝试次数')
    
    # 响应信息
    response_status = Column(Integer, nullable=True, comment='响应状态码')
    response_body = Column(Text, nullable=True, comment='响应内容')
    log_id = Column(String(100), nullable=True, comment='第三方返回的logId')
    error_message = Column(Text, nullable=True, comment='错误信息（如果失败）')
    
    # 时间信息
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='创建时间')
    report_start_time = Column(DateTime, nullable=True, comment='上报开始时间')
    report_success_time = Column(DateTime, nullable=True, comment='上报成功时间')
    completed_at = Column(DateTime, nullable=True, comment='完成时间')
    
    __table_args__ = (
        Index("idx_third_party_source", "source"),
        Index("idx_third_party_adsid", "adsid"),
        Index("idx_third_party_event", "event"),
        Index("idx_third_party_status", "status"),
        Index("idx_third_party_created_at", "created_at"),
        Index("idx_third_party_status_created", "status", "created_at"),
        UniqueConstraint('source', 'adsid', name='unique_source_adsid'),
    )

