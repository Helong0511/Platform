"""
第三方上报日志 ORM 模型。
"""
from sqlalchemy import Column, Integer, String, CHAR, Boolean, DateTime, ForeignKey, Enum, Text, Index, CheckConstraint, \
    UniqueConstraint, Date, Numeric, BINARY, text
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
    event_key = Column(
        String(64),
        nullable=False,
        comment='事件幂等键：稳定事件身份字段的 SHA-256（ViewContent 不含后补 conversion_id）',
    )
    conversion_id = Column(String(255), nullable=True, index=True, comment='转化ID')
    # 新事件显式标记身份作用域；历史数据迁移后保持 legacy_unresolved，禁止推断归属。
    platform = Column(String(100, collation="utf8mb4_bin"), nullable=True, comment='Postback 平台标识；非平台事件为 NULL；按二进制规则精确比较')
    identity_scope = Column(
        String(32),
        nullable=False,
        default="legacy_unresolved",
        server_default=text("'legacy_unresolved'"),
        comment="unscoped/platform_scoped/legacy_unresolved",
    )
    # Pixel ID 是非敏感目的地标识；绝不保存 access_token。
    destination_pixel_id = Column(
        String(100),
        nullable=True,
        comment="Meta Pixel 目的地 ID，用于同目的地事件关联与配置变更核验",
    )
    use_hash = Column(Boolean, default=True, nullable=False, comment='是否对email、ip、phone进行哈希处理：True=哈希，False=不哈希')
    email = Column(String(255), nullable=True, comment='邮箱（原始值）')
    ip = Column(String(50), nullable=True, comment='IP地址（原始值）')
    phone = Column(String(50), nullable=True, comment='手机号（原始值）')
    ua = Column(Text, nullable=True, comment='用户代理')
    currency = Column(String(10), nullable=True, comment='货币类型')
    amount = Column(Numeric(12, 4), nullable=True, comment='支付金额')

    # Postback 事务性 Outbox 元数据；只保存配置引用，不保存 Facebook access token。
    outbox_enqueued = Column(
        Boolean, nullable=False, default=False, server_default=text("0"),
        comment="是否由转化事务创建的持久化 Outbox 事件",
    )
    short_link_id = Column(Integer, nullable=True, comment="用于恢复像素配置的短链接 ID（非外键，保留删除后的证据）")
    cloak_name = Column(String(100), nullable=True, comment="斗篷配置名称（仅配置引用）")
    short_code = Column(String(100), nullable=True, comment="短链接短码（仅配置引用）")
    click_time = Column(DateTime, nullable=True, comment="点击发生时间，用于稳定构造 Meta event_time/fbc")
    next_retry_time = Column(DateTime, nullable=True, comment="Outbox 下次可重试时间")
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
    pii_scrubbed_at = Column(DateTime, nullable=True, comment='PII 按保留策略清理时间；保留事件幂等键')
    
    __table_args__ = (
        CheckConstraint(
            "identity_scope IN ('legacy_unresolved', 'unscoped', 'platform_scoped') "
            "AND ((identity_scope = 'platform_scoped' AND platform IS NOT NULL "
            "AND LENGTH(TRIM(platform)) > 0) "
            "OR (identity_scope IN ('unscoped', 'legacy_unresolved') AND platform IS NULL))",
            name="chk_third_party_identity_scope_v1",
        ),
        Index("idx_third_party_source", "source"),
        Index("idx_third_party_adsid", "adsid"),
        Index("idx_third_party_event", "event"),
        Index("idx_third_party_status", "status"),
        Index("idx_third_party_created_at", "created_at"),
        Index("idx_third_party_pii_retention", "pii_scrubbed_at", "created_at", "id"),
        Index("idx_third_party_status_created", "status", "created_at"),
        Index(
            "idx_third_party_scope_due",
            "identity_scope",
            "platform",
            "outbox_enqueued",
            "status",
            "next_retry_time",
            "report_start_time",
            "id",
        ),
        UniqueConstraint('event_key', name='unique_event_key'),
        Index(
            "idx_third_party_outbox_due",
            "outbox_enqueued",
            "status",
            "next_retry_time",
            "report_start_time",
            "id",
        ),
    )

class ThirdPartyReportIdentityLock(Base):
    """跨直接发送与 Postback Outbox 的基础事件身份仲裁锁。

    锁记录永久保留，不按时间清理；删除锁行会使同一身份重新出现不同互斥对象。
    只保存独立 SHA-512 指纹，不持久化广告点击标识等原始身份字段。
    """
    __tablename__ = "third_party_report_identity_locks"

    identity_key = Column(
        CHAR(64, collation="ascii_bin"),
        primary_key=True,
        nullable=False,
        comment="四字段基础事件身份的 SHA-256",
    )
    identity_fingerprint = Column(
        BINARY(64),
        nullable=False,
        comment="基础身份的独立 SHA-512 指纹；不保存原始点击标识",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=get_app_now_naive,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="锁行首次创建时间；锁行永久保留",
    )

