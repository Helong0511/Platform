"""广告数据查询缓存 Generation 与持久化失效 Outbox 模型。"""
from sqlalchemy import (
    BigInteger,
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)

from app.core.utils import get_app_now_naive
from app.models.base import Base


class CacheNamespaceGeneration(Base):
    """数据库权威缓存版本；业务数据与版本必须在同一事务提交。"""

    __tablename__ = "cache_namespace_generations"

    namespace = Column(String(64), primary_key=True, nullable=False, comment="缓存命名空间")
    generation = Column(BigInteger, nullable=False, default=1, comment="单调递增版本号")
    updated_at = Column(
        DateTime,
        nullable=False,
        default=get_app_now_naive,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="版本更新时间",
    )


class CacheInvalidationOutbox(Base):
    """持久化缓存失效任务；不保存业务载荷或敏感信息。"""

    __tablename__ = "cache_invalidation_outbox"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_key = Column(CHAR(64, collation="ascii_bin"), nullable=False, comment="命名空间与版本的 SHA-256 幂等键")
    namespace = Column(String(64), nullable=False, comment="缓存命名空间")
    generation = Column(BigInteger, nullable=False, comment="对应的数据库权威版本")
    status = Column(String(16), nullable=False, default="pending", server_default=text("'pending'"))
    attempt_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    max_attempts = Column(Integer, nullable=False, default=12, server_default=text("12"))
    next_retry_time = Column(DateTime, nullable=False, default=get_app_now_naive)
    locked_by = Column(String(128), nullable=True)
    lease_token = Column(CHAR(32, collation="ascii_bin"), nullable=True)
    lease_until = Column(DateTime, nullable=True)
    last_error_type = Column(String(128), nullable=True, comment="仅记录异常类型，不保存异常原文")
    created_at = Column(DateTime, nullable=False, default=get_app_now_naive, server_default=text("CURRENT_TIMESTAMP"))
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("event_key", name="uq_cache_invalidation_event_key"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'success', 'failed')",
            name="chk_cache_invalidation_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 AND generation > 0",
            name="chk_cache_invalidation_counters",
        ),
        Index(
            "idx_cache_invalidation_due",
            "status",
            "next_retry_time",
            "lease_until",
            "id",
        ),
        Index(
            "idx_cache_invalidation_namespace_generation",
            "namespace",
            "generation",
        ),
    )


class OfferCacheInvalidationOutbox(Base):
    """Offer 热点缓存两阶段失效事件；事件与 Offer 业务事务原子提交。"""

    __tablename__ = "offer_cache_invalidation_outbox"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    event_key = Column(CHAR(64, collation="ascii_bin"), nullable=False, comment="随机 SHA-256 格式幂等标识")
    offer_id = Column(Integer, nullable=False, comment="Offer 主键快照；不建立外键以允许删除后清理")
    phase = Column(String(8), nullable=False, comment="first 或 second")
    status = Column(String(16), nullable=False, default="pending", server_default=text("'pending'"))
    attempt_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    max_attempts = Column(Integer, nullable=False, default=12, server_default=text("12"))
    run_at = Column(DateTime, nullable=False, default=get_app_now_naive)
    locked_by = Column(String(128), nullable=True)
    lease_token = Column(CHAR(32, collation="ascii_bin"), nullable=True)
    lease_until = Column(DateTime, nullable=True)
    last_error_type = Column(String(128), nullable=True, comment="仅记录异常类型，不保存异常原文")
    created_at = Column(DateTime, nullable=False, default=get_app_now_naive, server_default=text("CURRENT_TIMESTAMP"))
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("event_key", name="uq_offer_cache_invalidation_event_key"),
        CheckConstraint(
            "phase IN ('first', 'second')",
            name="chk_offer_cache_invalidation_phase",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'success', 'failed')",
            name="chk_offer_cache_invalidation_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 AND offer_id > 0",
            name="chk_offer_cache_invalidation_attempts",
        ),
        Index(
            "idx_offer_cache_invalidation_due",
            "status",
            "run_at",
            "lease_until",
            "id",
        ),
        Index(
            "idx_offer_cache_invalidation_offer",
            "offer_id",
            "phase",
            "status",
        ),
    )
