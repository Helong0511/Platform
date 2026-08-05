"""
广告数据健康巡检相关 ORM：日标准快照、告警、配置。

标准粒度（方案 B）：stat_date + product_id + data_source。
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from app.models.base import Base
from app.core.utils import get_app_now_naive


class AdDataDayBaseline(Base):
    """日标准快照：日切后冻结，供倒扣对比。"""

    __tablename__ = "ad_data_day_baseline"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False, comment="标准日")
    product_id = Column(Integer, nullable=False, comment="产品ID")
    data_source = Column(String(32), nullable=False, comment="数据来源")
    request_count = Column(Integer, nullable=False, default=0, server_default="0")
    revenue_before = Column(
        Numeric(14, 4), nullable=False, default=0, server_default="0.0000"
    )
    row_count = Column(Integer, nullable=False, default=0, server_default="0")
    frozen_at = Column(DateTime, nullable=False, default=get_app_now_naive)
    freeze_batch_id = Column(String(64), nullable=False, default="", server_default="")

    __table_args__ = (
        UniqueConstraint(
            "stat_date",
            "product_id",
            "data_source",
            name="uq_ad_data_day_baseline",
        ),
        Index("idx_baseline_stat_date", "stat_date"),
        Index("idx_baseline_product", "product_id"),
    )


class AdDataHealthAlert(Base):
    """健康巡检告警落库。"""

    __tablename__ = "ad_data_health_alert"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    alert_type = Column(String(32), nullable=False)
    stat_date = Column(Date, nullable=False)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(100), nullable=False, default="", server_default="")
    data_source = Column(String(32), nullable=False, default="", server_default="")
    metric = Column(String(32), nullable=False, default="", server_default="")
    baseline_value = Column(Numeric(14, 4), nullable=True)
    current_value = Column(Numeric(14, 4), nullable=True)
    drop_ratio = Column(Numeric(10, 6), nullable=True)
    detail = Column(Text, nullable=True)
    batch_id = Column(String(64), nullable=False, default="", server_default="")
    notified = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, nullable=False, default=get_app_now_naive)

    __table_args__ = (
        Index("idx_health_alert_date_type", "stat_date", "alert_type"),
        Index("idx_health_alert_created", "created_at"),
        Index("idx_health_alert_product", "product_id"),
    )


class AdDataHealthSettings(Base):
    """健康巡检配置（单行 id=1）。"""

    __tablename__ = "ad_data_health_settings"

    id = Column(Integer, primary_key=True, default=1)
    drop_ratio = Column(Numeric(8, 4), nullable=False, default=0.02, server_default="0.0200")
    request_floor = Column(Integer, nullable=False, default=100, server_default="100")
    revenue_floor = Column(
        Numeric(12, 4), nullable=False, default=1, server_default="1.0000"
    )
    enable_baseline_drop = Column(Boolean, nullable=False, default=True, server_default="1")
    enable_missing = Column(Boolean, nullable=False, default=True, server_default="1")
    enable_streak = Column(Boolean, nullable=False, default=True, server_default="1")
    enable_today_gap = Column(Boolean, nullable=False, default=True, server_default="1")
    enable_dod_drop = Column(Boolean, nullable=False, default=True, server_default="1")
    enable_telegram = Column(Boolean, nullable=False, default=True, server_default="1")
    cooldown_hours = Column(Integer, nullable=False, default=24, server_default="24")
    updated_at = Column(
        DateTime, nullable=False, default=get_app_now_naive, onupdate=get_app_now_naive
    )
