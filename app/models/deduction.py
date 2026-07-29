"""
转化扣减配置与日志 ORM 模型。
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Text, Index, \
    UniqueConstraint, Date, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from app.core.utils import get_app_now_naive
from app.models.base import Base, pwd_context, UserRole

class ConversionDeductionConfig(Base):
    """
    转化扣减配置

    广告主/Offer/渠道三级扣量扣金额配置。
    表名: conversion_deduction_configs
    """
    __tablename__ = "conversion_deduction_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='配置ID')
    
    # 配置层级（三选一）
    advertiser_id = Column(Integer, ForeignKey("advertisers.id", ondelete="CASCADE"), nullable=True, index=True, comment='广告主ID（如果配置在广告主级别）')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=True, index=True, comment='Offer ID（如果配置在Offer级别）')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="CASCADE"), nullable=True, index=True, comment='渠道ID（如果配置在渠道级别）')
    
    # 扣减类型配置
    volume_deduction_ratio = Column(
        Numeric(5, 4), nullable=True, default=0, server_default='0.0000',
        comment='按比例扣量比例（0-1，如0.10表示扣量10%）',
    )
    amount_deduction_ratio = Column(
        Numeric(5, 4), nullable=True, default=0, server_default='0.0000',
        comment='按比例扣金额比例（0-1，如0.10表示扣金额10%）',
    )
    
    # 扣减策略配置
    deduction_strategy = Column(String(50), default='random', comment='扣减策略：random（随机）/proportional（按比例）/round_robin（轮询）')
    enable_volume_deduction = Column(Boolean, default=False, comment='是否启用按比例扣量')
    enable_amount_deduction = Column(Boolean, default=False, comment='是否启用按比例扣金额')
    
    # 优先级配置
    priority = Column(Integer, default=0, comment='优先级（数字越大优先级越高）')
    
    # 状态
    is_active = Column(Boolean, default=True, index=True, comment='是否激活')
    
    # 时间戳
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    advertiser = relationship("Advertiser", foreign_keys=[advertiser_id])
    offer = relationship("Offer", foreign_keys=[offer_id])
    publisher = relationship("Publisher", foreign_keys=[publisher_id])

    __table_args__ = (
        Index("idx_advertiser_id", "advertiser_id"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_is_active", "is_active"),
        Index("idx_priority", "priority"),
    )

class ConversionDeductionLog(Base):
    """
    转化扣减执行记录

    单次转化扣减执行明细与前后金额。
    表名: conversion_deduction_logs
    """
    __tablename__ = "conversion_deduction_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='记录ID')
    
    # 关联信息
    conversion_id = Column(Integer, ForeignKey("postback_conversions.id", ondelete="SET NULL"), nullable=True, index=True, comment='转化记录ID（关联postback_conversions.id，可为NULL因为扣量的转化可能不保存）')
    click_id = Column(String(255), nullable=True, index=True, comment='点击ID')
    advertiser_id = Column(Integer, ForeignKey("advertisers.id", ondelete="SET NULL"), nullable=True, index=True, comment='广告主ID')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="SET NULL"), nullable=True, index=True, comment='Offer ID')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True, index=True, comment='渠道ID')
    
    # 扣减前数据
    original_volume = Column(Integer, default=1, comment='原始转化数量（通常为1）')
    original_amount = Column(Numeric(10, 2), nullable=False, comment='原始转化金额')
    
    # 扣减后数据
    deducted_volume = Column(Integer, default=0, comment='扣减的转化数量')
    deducted_amount = Column(Numeric(10, 2), nullable=True, default=0, server_default='0.00', comment='扣减的转化金额')
    final_volume = Column(Integer, default=1, comment='最终转化数量（扣减后）')
    final_amount = Column(Numeric(10, 2), nullable=False, comment='最终转化金额（扣减后）')
    
    # 扣减配置信息
    deduction_config_id = Column(Integer, ForeignKey("conversion_deduction_configs.id", ondelete="SET NULL"), nullable=True, index=True, comment='使用的扣减配置ID')
    volume_deduction_ratio = Column(Numeric(5, 4), nullable=True, comment='使用的扣量比例')
    amount_deduction_ratio = Column(Numeric(5, 4), nullable=True, comment='使用的扣金额比例')
    deduction_strategy = Column(String(50), nullable=True, comment='使用的扣减策略')
    
    # 扣减原因
    deduction_reason = Column(Text, nullable=True, comment='扣减原因说明')
    
    # 时间戳
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')

    # 关系
    conversion = relationship("PostbackConversion", foreign_keys=[conversion_id])
    advertiser = relationship("Advertiser", foreign_keys=[advertiser_id])
    offer = relationship("Offer", foreign_keys=[offer_id])
    publisher = relationship("Publisher", foreign_keys=[publisher_id])
    deduction_config = relationship("ConversionDeductionConfig", foreign_keys=[deduction_config_id])

    __table_args__ = (
        Index("idx_conversion_id", "conversion_id"),
        Index("idx_click_id", "click_id"),
        Index("idx_advertiser_id", "advertiser_id"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_created_at", "created_at"),
        Index("idx_deduction_config_id", "deduction_config_id"),
    )


# ====== Postback 待确认与白名单 ======

