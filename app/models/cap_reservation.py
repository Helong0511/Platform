"""
Cap Redis reservation 持久化账本模型。

该表记录 Redis 计数预留与 Postback 数据库事务之间的跨存储状态。
不设置 Offer/Publisher 外键：账本必须在业务对象删除后仍保留恢复证据。
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, Boolean, CheckConstraint, Index, UniqueConstraint

from app.core.utils import get_app_now_naive
from app.models.base import Base


class CapReservation(Base):
    """单个 Postback 事件在一个 Redis Cap scope 上的预留记录。"""

    __tablename__ = "cap_reservations"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="预留账本主键")
    reservation_key = Column(
        String(64), nullable=False, comment="稳定预留键：正式事件键与 Cap scope 的 SHA-256"
    )
    platform = Column(String(50), nullable=False, comment="Postback 平台")
    conversion_id = Column(String(255), nullable=False, comment="正式转化事件 ID")
    event_name = Column(String(100), nullable=False, default="default", comment="标准化事件名称")
    offer_id = Column(Integer, nullable=False, comment="预留时的 Offer ID 快照")
    publisher_id = Column(Integer, nullable=True, comment="预留时的 Publisher ID 快照；NULL 表示全局渠道范围")
    cap_kind = Column(String(10), nullable=False, comment="Cap 类型：daily 或 total")
    business_date = Column(Date, nullable=True, comment="Daily 业务日期；Total 必须为 NULL")
    redis_counter_key = Column(String(255), nullable=False, comment="Redis 计数器 Key 快照")
    redis_token_key = Column(String(512), nullable=False, comment="Redis reservation token Key 快照")
    redis_reserved = Column(Boolean, nullable=False, default=False, comment="是否确认 Redis Lua 已成功预留；区分 fail-open 无 token 路径")
    redis_token_cleaned = Column(Boolean, nullable=False, default=False, comment="终态后是否已清理 Redis token；清理失败由恢复任务重试")
    state = Column(
        String(24), nullable=False, default="PREPARED",
        comment="状态：PREPARED/RESERVED/COMMITTED/ROLLED_BACK/NEEDS_RECONCILIATION",
    )
    attempts = Column(Integer, nullable=False, default=0, comment="恢复尝试次数")
    lease_owner = Column(String(64), nullable=True, comment="恢复 Worker 租约持有者")
    lease_expires_at = Column(DateTime, nullable=True, comment="恢复 Worker 租约到期时间")
    last_error = Column(Text, nullable=True, comment="最近一次恢复错误摘要")
    prepared_at = Column(DateTime, nullable=False, default=get_app_now_naive, comment="PREPARED 创建时间")
    reserved_at = Column(DateTime, nullable=True, comment="Redis 预留确认时间")
    finalized_at = Column(DateTime, nullable=True, comment="终态确认时间")
    created_at = Column(DateTime, nullable=False, default=get_app_now_naive, comment="创建时间")
    updated_at = Column(
        DateTime, nullable=False, default=get_app_now_naive,
        onupdate=get_app_now_naive, comment="更新时间",
    )

    __table_args__ = (
        # 在数据库层强制账本关键语义，避免绕过 Service 的写入破坏恢复依据。
        CheckConstraint("CHAR_LENGTH(reservation_key) = 64", name="chk_cap_reservation_key_sha256"),
        CheckConstraint("offer_id > 0", name="chk_cap_reservation_offer_positive"),
        CheckConstraint("publisher_id IS NULL OR publisher_id > 0", name="chk_cap_reservation_publisher_positive"),
        CheckConstraint("attempts >= 0", name="chk_cap_reservation_attempts_nonnegative"),
        CheckConstraint(
            "(cap_kind = 'daily' AND business_date IS NOT NULL) OR "
            "(cap_kind = 'total' AND business_date IS NULL)",
            name="chk_cap_reservation_kind_date",
        ),
        CheckConstraint(
            "state IN ('PREPARED', 'RESERVED', 'COMMITTED', 'ROLLED_BACK', 'NEEDS_RECONCILIATION')",
            name="chk_cap_reservation_state",
        ),
        UniqueConstraint("reservation_key", name="uq_cap_reservation_key"),
        Index("idx_cap_reservation_state_updated", "state", "updated_at"),
        Index("idx_cap_reservation_lease", "state", "lease_expires_at"),
        Index("idx_cap_reservation_event", "platform", "conversion_id", "event_name"),
        Index("idx_cap_reservation_scope", "offer_id", "publisher_id", "cap_kind", "business_date"),
    )
