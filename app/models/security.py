"""
敏感路径探测、IP 白名单 ORM 模型。
"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Enum, Text, Index, \
    UniqueConstraint, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from app.core.utils import get_app_now_naive
from app.models.base import Base, pwd_context, UserRole

class SensitivePathProbeLog(Base):
    """
    敏感路径探测拦截日志。

    记录扫描 .env、phpMyAdmin 等敏感 URI 的请求，供安全审计与自动封 IP。
    表名: sensitive_path_probe_logs
    """
    __tablename__ = "sensitive_path_probe_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="主键ID")
    request_path = Column(String(1024), nullable=False, comment="请求路径")
    method = Column(String(16), nullable=True, index=True, comment="请求方法")
    client_ip = Column(String(64), nullable=True, index=True, comment="客户端IP")
    user_agent = Column(String(512), nullable=True, comment="用户代理")
    query_string = Column(String(2048), nullable=True, comment="查询字符串")
    matched_rule = Column(String(255), nullable=True, index=True, comment="命中规则")
    severity_level = Column(
        Integer,
        nullable=False,
        default=2,
        index=True,
        comment="预警等级：1低危 2中危 3高危 4危急",
    )
    action_taken = Column(String(64), nullable=True, comment="处置动作：blocked_404/auto_blocked_ip等")
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment="创建时间")

    __table_args__ = (
        Index("idx_sensitive_probe_created_at", "created_at"),
        Index("idx_sensitive_probe_ip_created", "client_ip", "created_at"),
        Index("idx_sensitive_probe_severity_created", "severity_level", "created_at"),
    )

class SensitiveBlockedIP(Base):
    """
    敏感路径防护 IP 黑名单。

    命中高危规则或累计探测次数后自动写入，Middleware 拦截后续请求。
    表名: sensitive_blocked_ips
    """
    __tablename__ = "sensitive_blocked_ips"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="主键ID")
    blocked_ip = Column(String(64), nullable=False, unique=True, index=True, comment="封禁IP")
    reason = Column(String(255), nullable=True, comment="封禁原因")
    is_active = Column(Boolean, default=True, nullable=False, index=True, comment="是否启用")
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=get_app_now_naive,
        onupdate=get_app_now_naive,
        nullable=False,
        comment="更新时间"
    )

    __table_args__ = (
        Index("idx_sensitive_blocked_ip_active", "is_active", "created_at"),
    )

class PostbackIpWhitelist(Base):
    """
    Postback IP 白名单模型
    
    用于存储允许接收 postback 数据的 IP 地址列表
    只有白名单中的 IP 地址发送的 postback 数据才会被处理并记录
    非白名单 IP 的数据会被视为测试数据，不进行记录
    
    表名: postback_ip_whitelist
    """
    __tablename__ = "postback_ip_whitelist"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='白名单ID')
    ip_address = Column(String(45), nullable=False, unique=True, index=True, comment='IP地址（支持IPv4和IPv6）')
    description = Column(String(255), nullable=True, comment='IP地址描述/备注')
    is_active = Column(Boolean, default=True, nullable=False, index=True, comment='是否启用')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive, onupdate=get_app_now_naive, nullable=False, comment='更新时间')
    
    __table_args__ = (
        Index("idx_ip_address", "ip_address"),
        Index("idx_is_active", "is_active"),
    )


# ====== 第三方广告平台上报 ======

