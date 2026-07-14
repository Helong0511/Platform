"""
CPL 广告主、渠道、Offer、Cap、扣量 ORM 模型。
"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Enum, Text, Index, \
    UniqueConstraint, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from app.core.utils import get_app_now_naive
from app.models.base import Base, pwd_context, UserRole

class Advertiser(Base):
    """
    广告主（上游）

    CPL 广告主，旗下多个 Offer。
    表名: advertisers
    """
    __tablename__ = "advertisers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='广告主ID')
    advertiser_name = Column(String(100), nullable=False, index=True, comment='广告主名称')
    email = Column(String(255), nullable=True, comment='邮箱（可选）')
    mobile = Column(String(20), nullable=True, comment='手机号')
    advertiser_params = Column(Text, nullable=True, comment='广告主参数')
    is_active = Column(Boolean, default=True, index=True, comment='是否激活')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    offers = relationship("Offer", back_populates="advertiser", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_advertiser_name", "advertiser_name"),
        Index("idx_is_active", "is_active"),
    )

class Publisher(Base):
    """
    渠道（下游）

    CPL 渠道/商户，可配置 Postback 与折扣。
    表名: publishers
    """
    __tablename__ = "publishers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='渠道ID')
    publisher_name = Column(String(100), nullable=False, index=True, comment='渠道名称')
    email = Column(String(255), nullable=True, comment='邮箱（可选）')
    price_discount = Column(Float, default=0.0, comment='渠道级别的价格折扣比例（0-100），用于旧价格折扣系统，计算给渠道的最终金额（affiliate_payout）')
    postback_url = Column(Text, nullable=True, comment='Postback URL（渠道的Postback配置）')
    postback_method = Column(String(10), default='GET', comment='Postback请求方式：GET/POST')
    postback_success_check = Column(Text, nullable=True, comment='转发成功检查配置（JSON格式，用于检查响应内容是否表示成功）')
    active_advertiser_count = Column(Integer, default=0, comment='活跃的广告主数量')
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的客户ID')
    is_active = Column(Boolean, default=True, index=True, comment='是否激活')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    offer_assignments = relationship("OfferPublisherAssignment", back_populates="publisher", cascade="all, delete-orphan")
    clicks = relationship("Click", back_populates="publisher")
    discounts = relationship("OfferDiscount", back_populates="publisher", cascade="all, delete-orphan")
    client = relationship("Client", foreign_keys=[client_id])

    __table_args__ = (
        Index("idx_publisher_name", "publisher_name"),
        Index("idx_is_active", "is_active"),
    )

class Offer(Base):
    """
    Offer 单子

    CPL Offer，关联广告主与渠道分配。
    表名: offers
    """
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='Offer ID（主键）')
    offer_name = Column(String(200), nullable=False, comment='Offer名称')
    advertiser_offer_id = Column(String(100), nullable=True, comment='上游系统中的Offer ID（ADV Offer ID）')
    advertiser_id = Column(Integer, ForeignKey("advertisers.id", ondelete="RESTRICT"), nullable=False, index=True, comment='关联的广告主ID')
    preview_link = Column(Text, nullable=True, comment='预览链接')
    payout = Column(Float, nullable=True, comment='上游支付金额（PO）')
    affiliate_payout = Column(Float, nullable=True, comment='扣价后给渠道的金额（PO扣价后）')
    country = Column(String(50), nullable=True, index=True, comment='国家')
    category = Column(String(50), nullable=True, comment='分类')
    type = Column(String(50), nullable=True, comment='类型')
    status = Column(String(20), default='Active', index=True, comment='状态：Active/Inactive')
    upstream_cap = Column(Integer, nullable=True, comment='上游转化上限')
    downstream_cap = Column(Integer, nullable=True, comment='下游转化上限')
    advertiser_tracklink = Column(Text, nullable=True, comment='上游的Tracklink（不显示给下游，建立单子时配置我们的参数）')
    downstream_tracklink = Column(Text, nullable=True, comment='生成给下游的Tracklink')
    postback_url = Column(Text, nullable=True, comment='Postback URL（配置我们的参数）')
    postback_method = Column(String(10), default='GET', comment='Postback请求方式：GET/POST')
    click_validity_hours = Column(Integer, default=720, comment='点击有效期（小时），默认720小时（30天）')
    is_active = Column(Boolean, default=True, index=True, comment='是否激活')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    advertiser = relationship("Advertiser", back_populates="offers")
    offer_assignments = relationship("OfferPublisherAssignment", back_populates="offer", cascade="all, delete-orphan")
    clicks = relationship("Click", back_populates="offer")
    caps = relationship("OfferCap", back_populates="offer", cascade="all, delete-orphan")
    discounts = relationship("OfferDiscount", back_populates="offer", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_advertiser_id", "advertiser_id"),
        Index("idx_status", "status"),
        Index("idx_is_active", "is_active"),
        Index("idx_country", "country"),
    )

class OfferPublisherAssignment(Base):
    """
    Offer-渠道分配

    Offer 与渠道的分配关系及渠道专属 Cap/PO。
    表名: offer_publisher_assignments
    """
    __tablename__ = "offer_publisher_assignments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='分配ID')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True, comment='Offer ID')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False, index=True, comment='渠道ID')
    downstream_cap = Column(Integer, nullable=True, comment='该渠道的下游每天转化个数的限制，如果渠道转化超过了这个值就不通知渠道了。客户登录查看时，也只显示真实的（真实不超过【下游Cap】的）转化')
    affiliate_payout = Column(Float, nullable=True, comment='该渠道的转化金额（不是金额的扣减比例）。如果上游通知的金额大于这个金额，就按照【下游PO】的金额通知渠道')
    is_active = Column(Boolean, default=True, index=True, comment='是否激活')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    offer = relationship("Offer", back_populates="offer_assignments")
    publisher = relationship("Publisher", back_populates="offer_assignments")

    __table_args__ = (
        UniqueConstraint("offer_id", "publisher_id", name="uq_offer_publisher"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_is_active", "is_active"),
    )

class Click(Base):
    """
    点击记录

    点击追踪主表，存储设备/UA/URL 参数等归因信息。
    表名: clicks
    """
    __tablename__ = "clicks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='点击记录ID')
    click_id = Column(String(255), unique=True, nullable=False, comment='点击ID（系统生成，唯一标识）')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="SET NULL"), nullable=True, comment='关联的Offer ID')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True, comment='关联的渠道ID')
    advertiser_id = Column(Integer, ForeignKey("advertisers.id", ondelete="SET NULL"), nullable=True, comment='关联的广告主ID')
    short_link_id = Column(Integer, ForeignKey("short_links.id", ondelete="SET NULL"), nullable=True, comment='关联的短链接ID')
    click_time = Column(DateTime, nullable=False, comment='点击时间')
    ip = Column(String(50), nullable=True, comment='点击IP地址')
    device = Column(String(100), nullable=True, comment='设备信息（兼容旧字段）')
    country = Column(String(50), nullable=True, comment='国家')
    user_agent = Column(Text, nullable=True, comment='User Agent')
    referer = Column(Text, nullable=True, comment='来源页面')
    conversion_id = Column(Integer, nullable=True, comment='关联的转化ID（如果已转化）')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')

    # 软件信息
    os = Column(String(50), nullable=True, comment='操作系统名称')
    os_version = Column(String(50), nullable=True, comment='操作系统版本')
    browser = Column(String(50), nullable=True, comment='浏览器名称')
    browser_version = Column(String(50), nullable=True, comment='浏览器版本')
    accept_language = Column(String(200), nullable=True, comment='接受的语言')
    accept_encoding = Column(String(200), nullable=True, comment='接受的编码')
    is_bot = Column(Boolean, default=False, nullable=False, comment='是否为机器人/爬虫')
    
    # 硬件信息
    device_type = Column(String(20), nullable=True, comment='设备类型（mobile/tablet/desktop）')
    device_brand = Column(String(50), nullable=True, comment='设备品牌')
    device_model = Column(String(100), nullable=True, comment='设备型号')
    
    # URL参数和请求头（JSON格式存储）
    url_params = Column(Text, nullable=True, comment='URL参数（JSON格式）')
    all_headers = Column(Text, nullable=True, comment='所有请求头（JSON格式）')
    
    # URL记录
    original_request_url = Column(Text, nullable=True, comment='原始点击URL（用户访问的短链接URL）')
    final_redirect_url = Column(Text, nullable=True, comment='最终跳转URL（系统重定向后的URL）')

    # 关系
    offer = relationship("Offer", back_populates="clicks")
    publisher = relationship("Publisher", back_populates="clicks")
    advertiser = relationship("Advertiser", foreign_keys=[advertiser_id])
    short_link = relationship("ShortLink", foreign_keys=[short_link_id])

    __table_args__ = (
        Index("idx_offer_id", "offer_id"),
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_advertiser_id", "advertiser_id"),
        Index("idx_short_link_id", "short_link_id"),
        Index("idx_click_time", "click_time"),
        Index("idx_conversion_id", "conversion_id"),
        Index("idx_ip", "ip"),
        Index("idx_country", "country"),
        Index("idx_clicks_time_offer", "click_time", "offer_id"),
        Index("idx_click_time_publisher", "click_time", "publisher_id"),
        Index("idx_clicks_time_offer_publisher", "click_time", "offer_id", "publisher_id"),
        Index("idx_clicks_offer_publisher_time", "offer_id", "publisher_id", "click_time"),
        Index("idx_safe_delete", "advertiser_id", "offer_id", "publisher_id", "created_at"),
        Index("idx_clicks_created_at_id", "created_at", "id"),
    )

class OfferCap(Base):
    """
    Offer Cap 配置

    Offer 日/总 Cap 及当前计数。
    表名: offer_caps
    """
    __tablename__ = "offer_caps"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='Cap配置ID')
    cap_type = Column(String(50), nullable=False, index=True, comment='Cap类型：advertiser_offer/offer')
    advertiser_id = Column(Integer, ForeignKey("advertisers.id", ondelete="CASCADE"), nullable=True, index=True, comment='广告主ID（如果是advertiser_offer类型）')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True, comment='Offer ID')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="CASCADE"), nullable=True, index=True, comment='渠道ID（如果为空，表示所有渠道）')
    daily_cap = Column(Integer, nullable=True, comment='每日Cap')
    total_cap = Column(Integer, nullable=True, comment='总Cap')
    current_daily_count = Column(Integer, default=0, comment='当前每日计数')
    current_total_count = Column(Integer, default=0, comment='当前总计数')
    cap_start_date = Column(DateTime, nullable=True, comment='Cap开始日期（用于Total Cap）')
    is_active = Column(Boolean, default=True, index=True, comment='是否激活')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    offer = relationship("Offer", back_populates="caps")
    advertiser = relationship("Advertiser", foreign_keys=[advertiser_id])
    publisher = relationship("Publisher", foreign_keys=[publisher_id])

    __table_args__ = (
        Index("idx_cap_type", "cap_type"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_advertiser_id", "advertiser_id"),
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_is_active", "is_active"),
    )

class OfferDiscount(Base):
    """
    Offer 扣量配置

    Offer 或渠道级别的价格扣量比例。
    表名: offer_discounts
    """
    __tablename__ = "offer_discounts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='扣量配置ID')
    discount_type = Column(String(50), nullable=False, index=True, comment='扣量类型：offer/channel')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=True, index=True, comment='Offer ID（如果是offer类型）')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False, index=True, comment='渠道ID')
    discount_ratio = Column(Float, nullable=False, comment='扣量比例（0-100）')
    is_active = Column(Boolean, default=True, index=True, comment='是否激活')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    offer = relationship("Offer", back_populates="discounts")
    publisher = relationship("Publisher", back_populates="discounts")

    __table_args__ = (
        Index("idx_discount_type", "discount_type"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_is_active", "is_active"),
    )

class AdvertiserTest(Base):
    """
    上游测试记录（已废弃）

    上游 Offer 测试记录，表已废弃，保留 ORM 兼容。
    表名: advertiser_tests
    """
    __tablename__ = "advertiser_tests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='测试记录ID')
    advertiser_id = Column(Integer, ForeignKey("advertisers.id", ondelete="CASCADE"), nullable=False, index=True, comment='广告主ID')
    advertiser_name = Column(String(100), nullable=True, comment='广告主名称')
    advertiser_offer_id = Column(String(100), nullable=True, comment='上游系统中的Offer ID')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True, comment='平台内的Offer ID')
    offer_name = Column(String(200), nullable=True, comment='Offer名称')
    price = Column(Float, nullable=True, comment='价格')
    country = Column(String(50), nullable=True, comment='国家')
    click_id = Column(String(255), nullable=True, comment='测试生成的Click ID')
    click_url = Column(Text, nullable=True, comment='测试生成的Click Url')
    test_time = Column(DateTime, nullable=True, index=True, comment='测试时间')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')

    # 关系
    advertiser = relationship("Advertiser", foreign_keys=[advertiser_id])
    offer = relationship("Offer", foreign_keys=[offer_id])

    __table_args__ = (
        Index("idx_advertiser_id", "advertiser_id"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_test_time", "test_time"),
    )

class AffiliateTest(Base):
    """
    下游测试记录

    向下游发送测试 Postback 的记录。
    表名: affiliate_tests
    """
    __tablename__ = "affiliate_tests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='测试记录ID')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False, index=True, comment='渠道ID')
    click_id = Column(String(255), nullable=False, index=True, comment='下游提供的Click ID')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True, comment='Offer ID')
    offer_name = Column(String(200), nullable=True, comment='Offer名称')
    price = Column(Float, nullable=True, comment='价格')
    country = Column(String(50), nullable=True, comment='国家')
    platform = Column(String(50), nullable=True, comment='平台')
    postback_time = Column(DateTime, nullable=True, index=True, comment='Postback发送时间')
    status = Column(String(50), nullable=True, index=True, comment='发送状态：Send Success/Failed')
    affiliate_return_content = Column(Text, nullable=True, comment='渠道返回内容')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')

    # 关系
    publisher = relationship("Publisher", foreign_keys=[publisher_id])
    offer = relationship("Offer", foreign_keys=[offer_id])

    __table_args__ = (
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_click_id", "click_id"),
        Index("idx_status", "status"),
        Index("idx_postback_time", "postback_time"),
    )


# ==================== CPL扣减系统模型 ====================

