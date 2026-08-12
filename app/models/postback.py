"""
Postback 转化、转发、通知、短链、斗篷 ORM 模型。
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Text, Index, \
    UniqueConstraint, Date, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from app.core.utils import get_app_now_naive
from app.models.base import Base, pwd_context, UserRole

class PostbackConversion(Base):
    """
    Postback 转化事件

    S2S Postback 转化记录，含扣减字段与 CPL 归因快照。
    表名: postback_conversions
    """
    __tablename__ = "postback_conversions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='转化记录ID')
    platform = Column(String(50), nullable=False, index=True, comment='平台名称：bft等')
    conversion_id = Column(String(255), nullable=False, comment='转化ID（各平台唯一标识，如clk_id）')
    transaction_id = Column(String(255), nullable=True, unique=True, comment='上游事务ID（幂等）')
    request_id = Column(String(128), nullable=True, unique=True, comment='请求防重放ID')
    event_name = Column(String(100), nullable=True, index=True, comment='事件名称')
    event_value = Column(Numeric(12, 4), nullable=True, comment='事件价值（购买价格等）')
    original_payout = Column(Numeric(12, 4), nullable=True, comment='原始支付金额（PO）')
    payout = Column(Numeric(12, 4), nullable=True, comment='扣后支付金额（PO(扣)）')

    # 设备信息
    devad_id = Column(String(255), nullable=True, comment='设备广告ID（IDFA或GAID）')
    os = Column(String(20), nullable=True, comment='操作系统（IOS或Android）')
    carrier = Column(String(50), nullable=True, comment='用户运营商')
    ip = Column(String(50), nullable=True, comment='点击IP地址')
    gid = Column(String(100), nullable=True, comment='渠道ID（Channel ID）')

    # 关联信息
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, comment='关联的产品ID')
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, comment='关联的客户ID')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="SET NULL"), nullable=True, index=True, comment='Offer ID（转化时快照）')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True, index=True, comment='渠道 ID（转化时快照）')
    advertiser_id = Column(Integer, ForeignKey("advertisers.id", ondelete="SET NULL"), nullable=True, index=True, comment='广告主 ID（转化时快照）')

    # CPL 系统字段
    click_id = Column(String(255), nullable=True, index=True, comment='关联的Click ID')
    click_time = Column(DateTime, nullable=True, comment='点击时间')
    conversion_status = Column(String(20), default='Pending', index=True, comment='转化状态：Pending(待处理-默认)/Approved(已批准)/CapReached(达到上限)/OfferInactive(Offer关闭)/ClickExpired(点击过期)')

    # 原始数据（JSON格式，保存完整回调数据）
    raw_data = Column(Text, nullable=True, comment='原始回调数据（JSON格式）')

    # 扣减相关字段
    is_deducted = Column(Boolean, default=False, index=True, comment='是否已被扣减')
    deduction_type = Column(String(20), nullable=True, index=True, comment='扣减类型：volume（扣量）/amount（扣金额）/both（两者）')
    original_volume = Column(Integer, default=1, comment='原始转化数量')
    deducted_volume = Column(Integer, default=0, comment='扣减的转化数量')

    # 元数据
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='创建时间')

    # 关系（用于通过 ORM 访问关联对象，例如：conversion.product.name）
    # 注意：当前查询接口未使用这些关系，但保留以备将来扩展使用（如返回产品名称、客户名称等）
    product = relationship("Product", foreign_keys=[product_id])
    client = relationship("Client", foreign_keys=[client_id])

    __table_args__ = (
        Index("idx_postback_platform_conversion", "platform", "conversion_id"),
        Index("idx_postback_product", "product_id"),
        Index("idx_postback_client", "client_id"),
        Index("idx_postback_created_at", "created_at"),
        Index("idx_postback_platform_event", "platform", "event_name"),
        Index("idx_click_id", "click_id"),
        Index("idx_conversion_status", "conversion_status"),
        Index("idx_postback_conversion_id", "conversion_id"),
        Index("idx_postback_offer_id", "offer_id"),
        Index("idx_postback_publisher_id", "publisher_id"),
        Index("idx_postback_advertiser_id", "advertiser_id"),
        Index("idx_is_deducted", "is_deducted"),
        Index("idx_deduction_type", "deduction_type"),
        Index("idx_postback_created_at_click_id", "created_at", "click_id"),
        Index("idx_postback_created_at_platform", "created_at", "platform"),
        Index("idx_postback_created_at_status", "created_at", "conversion_status"),
        UniqueConstraint("platform", "conversion_id", "event_name", name="uq_postback_platform_conversion_event"),
    )

class PostbackForwardLog(Base):
    """
    Postback 下游转发日志

    转化向下游渠道转发的请求与响应日志。
    表名: postback_forward_logs
    """
    __tablename__ = "postback_forward_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='转发日志ID')
    conversion_id = Column(Integer, ForeignKey("postback_conversions.id", ondelete="CASCADE"), nullable=False, index=True, comment='关联的转化记录ID')
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True, comment='产品ID')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True, index=True, comment='渠道ID（转发到渠道时使用）')
    downstream_url = Column(String(500), nullable=False, comment='下游URL')
    request_method = Column(String(10), nullable=False, comment='请求方式：GET 或 POST')
    request_data = Column(Text, nullable=True, comment='请求数据（JSON格式，用于POST请求）')
    request_params = Column(Text, nullable=True, comment='请求参数（URL参数，用于GET请求）')
    response_status = Column(Integer, nullable=True, comment='响应状态码')
    response_body = Column(Text, nullable=True, comment='响应内容')
    success = Column(Boolean, default=False, index=True, comment='是否转发成功')
    error_message = Column(Text, nullable=True, comment='错误信息（如果转发失败）')
    retry_count = Column(Integer, default=0, comment='重试次数')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='创建时间')
    completed_at = Column(DateTime, nullable=True, comment='完成时间')

    # 关系
    conversion = relationship("PostbackConversion", foreign_keys=[conversion_id])
    product = relationship("Product", foreign_keys=[product_id])
    publisher = relationship("Publisher", foreign_keys=[publisher_id])

    __table_args__ = (
        Index("idx_forward_log_conversion", "conversion_id"),
        Index("idx_forward_log_product", "product_id"),
        Index("idx_forward_log_publisher", "publisher_id"),
        Index("idx_forward_log_created_at", "created_at"),
        Index("idx_forward_log_success", "success"),
    )

class PostbackForwardQueue(Base):
    """
    Postback 转发重试队列

    转发失败后的延迟重试队列。
    表名: postback_forward_queue
    """
    __tablename__ = "postback_forward_queue"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='队列ID')
    conversion_id = Column(Integer, ForeignKey("postback_conversions.id", ondelete="CASCADE"), nullable=False, index=True, comment='关联的转化记录ID')
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True, comment='产品ID（产品级转发时使用）')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True, index=True, comment='渠道ID（渠道级转发时使用）')
    downstream_url = Column(String(500), nullable=False, comment='下游URL')
    request_method = Column(String(10), nullable=False, comment='请求方式：GET 或 POST')
    request_data = Column(Text, nullable=True, comment='请求数据（JSON格式，用于POST请求）')
    request_params = Column(Text, nullable=True, comment='请求参数（URL参数，用于GET请求）')
    retry_count = Column(Integer, default=0, comment='已重试次数')
    next_retry_time = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='下次重试时间')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='创建时间')

    # 关系
    conversion = relationship("PostbackConversion", foreign_keys=[conversion_id])
    product = relationship("Product", foreign_keys=[product_id])

    __table_args__ = (
        Index("idx_forward_queue_time", "next_retry_time"),
        Index("idx_forward_queue_conversion", "conversion_id"),
        Index("idx_forward_queue_publisher", "publisher_id"),
    )

class ClientNotificationConfig(Base):
    """
    客户通知配置

    客户级转化/Telegram 等通知偏好。
    表名: client_notification_configs
    """
    __tablename__ = "client_notification_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='通知配置ID')
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True, comment='客户ID')
    notification_enabled = Column(Boolean, default=True, comment='是否启用通知')
    notify_on_conversion = Column(Boolean, default=True, comment='转化时通知')
    notify_on_high_value = Column(Boolean, default=False, comment='高价值转化通知')
    high_value_threshold = Column(Numeric(12, 4), nullable=True, comment='高价值阈值')
    notify_channels = Column(Text, nullable=True, comment='通知渠道（JSON格式：["telegram", "email", "sms"]）')
    telegram_chat_id = Column(String(100), nullable=True, comment='Telegram Chat ID')
    email_address = Column(String(255), nullable=True, comment='邮箱地址')
    phone_number = Column(String(20), nullable=True, comment='手机号')
    notification_frequency = Column(String(20), default='realtime', comment='通知频率：realtime, hourly, daily')
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    client = relationship("Client", foreign_keys=[client_id])

    __table_args__ = (
        Index("idx_client_notification_config_client", "client_id"),
        Index("idx_client_notification_config_enabled", "notification_enabled"),
    )

class ProductNotificationConfig(Base):
    """
    产品通知配置

    产品级通知渠道与阈值配置。
    表名: product_notification_configs
    """
    __tablename__ = "product_notification_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='通知配置ID')
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, unique=True, comment='产品ID')
    notification_enabled = Column(Boolean, default=True, comment='是否启用通知')
    notify_on_conversion = Column(Boolean, default=True, comment='转化时通知')
    notify_on_high_value = Column(Boolean, default=False, comment='高价值转化通知')
    high_value_threshold = Column(Numeric(12, 4), nullable=True, comment='高价值阈值')
    notify_channels = Column(Text, nullable=True, comment='通知渠道（JSON格式：["telegram", "email", "sms"]）')
    telegram_chat_id = Column(String(100), nullable=True, comment='Telegram Chat ID')
    email_address = Column(String(255), nullable=True, comment='邮箱地址')
    phone_number = Column(String(20), nullable=True, comment='手机号')
    notification_frequency = Column(String(20), default='realtime', comment='通知频率：realtime, hourly, daily')
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    product = relationship("Product", foreign_keys=[product_id])

    __table_args__ = (
        Index("idx_product_notification_config_enabled", "notification_enabled"),
    )

class AdminNotificationConfig(Base):
    """
    管理员通知配置

    管理员全局通知开关（单例，应用层保证 id=1）。
    表名: admin_notification_configs
    """
    __tablename__ = "admin_notification_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='配置ID（固定为1）')
    telegram_enabled = Column(Boolean, default=True, comment='是否启用 Telegram 通知')
    telegram_chat_id = Column(String(100), nullable=True, comment='管理员 Telegram Chat ID')
    notify_all_conversions = Column(Boolean, default=True, comment='通知所有转化')
    notify_forward_failure = Column(Boolean, default=True, comment='通知转发失败')
    notify_forward_success = Column(Boolean, default=True, comment='通知转发成功')
    notify_system_errors = Column(Boolean, default=True, comment='通知系统异常')
    notify_statistics = Column(Boolean, default=False, comment='定时统计通知')
    statistics_frequency = Column(String(20), default='hourly', comment='统计频率：hourly, daily')
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    __table_args__ = (
        # 注意：单例模式，应用层确保只有一条记录（id=1）
        # MySQL 的 CheckConstraint 支持有限，不在数据库层强制
    )

class CloakConfig(Base):
    """
    斗篷像素配置表（cloak_configs）。

    一条记录对应一个 cloak_name（与磁盘桥页 {cloak_name}.html、投放链接 dp 参数一致），
    存储主/备 Facebook Pixel、三阶段 CAPI 上报开关与事件参数。
    管理端通过 app/api_v1/system/cloak_configs.py 维护；运行时由 cloak_pixel_mapping 读取。
    """
    __tablename__ = "cloak_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='配置ID')
    cloak_name = Column(String(100), nullable=False, unique=True, index=True, comment='斗篷名称（如 master）')
    pixel_id = Column(String(50), nullable=False, comment='主像素ID')
    access_token = Column(String(500), nullable=False, comment='主像素Token')
    backup_pixel_id = Column(String(50), nullable=True, comment='备份像素ID')
    backup_access_token = Column(String(500), nullable=True, comment='备份像素Token')
    report_event = Column(
        String(64),
        nullable=False,
        default='ViewContent',
        comment=(
            '桥页按钮点击时服务端 CAPI 的 event_name：'
            'Meta 官方标准事件（如 ViewContent、Purchase、Lead）或自定义名（如 Click）；'
            '含义与可选值见 app/schemas/cloak.py 中 FACEBOOK_STANDARD_EVENT_NAMES / 自定义命名规则'
        ),
    )
    report_value = Column(Numeric(12, 4), nullable=True, comment='购物类事件金额（Purchase 等需配合 report_currency）')
    report_currency = Column(
        String(10),
        nullable=True,
        default='USD',
        comment='购物类事件货币代码（如 USD）',
    )
    click_report_enabled = Column(
        Boolean,
        default=True,
        nullable=False,
        comment='桥页按钮跳转是否向 Facebook 上报（对应 report_event）',
    )
    load_report_enabled = Column(
        Boolean,
        default=False,
        nullable=False,
        comment='桥页加载完成是否向 Facebook 上报',
    )
    load_report_event = Column(
        String(64),
        nullable=False,
        default='PageView',
        comment='加载完成时 CAPI event_name',
    )
    load_report_value = Column(Numeric(12, 4), nullable=True, comment='加载上报为 Purchase 时的金额')
    load_report_currency = Column(
        String(10),
        nullable=True,
        default='USD',
        comment='加载上报为 Purchase 时的货币',
    )
    postback_report_enabled = Column(
        Boolean,
        default=False,
        nullable=False,
        comment='postback 转化是否按本行配置上报；False 时仍按原逻辑发 Purchase+payout',
    )
    postback_report_event = Column(
        String(64),
        nullable=False,
        default='Purchase',
        comment='postback 转化时 CAPI event_name（需点击记录 url_params 含 dp=斗篷名）',
    )
    postback_report_value = Column(
        Numeric(12, 4),
        nullable=True,
        comment='postback 为 Purchase 时固定金额；NULL 则用 postback 的 payout',
    )
    postback_report_currency = Column(
        String(10),
        nullable=True,
        default='USD',
        comment='postback Purchase 货币',
    )
    is_enabled = Column(Boolean, default=True, nullable=False, index=True, comment='是否启用')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, nullable=False, comment='更新时间')

    __table_args__ = (
        Index("idx_cloak_name", "cloak_name"),
        Index("idx_cloak_enabled", "is_enabled"),
    )

class PostbackNotification(Base):
    """
    Postback 通知记录

    Postback 相关通知的发送记录与状态。
    表名: postback_notifications
    """
    __tablename__ = "postback_notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='通知记录ID')
    conversion_id = Column(Integer, ForeignKey("postback_conversions.id", ondelete="CASCADE"), nullable=True, index=True, comment='转化记录ID（汇总通知时为NULL）')
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True, comment='客户ID')
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True, comment='产品ID')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True, index=True, comment='渠道ID（转发通知时使用）')
    notification_type = Column(String(50), nullable=True, comment='通知类型：conversion, high_value, error, forward, summary_hourly, summary_daily')
    notification_channel = Column(String(50), nullable=False, comment='通知渠道：telegram, email, sms, webhook')
    notification_status = Column(String(20), default='pending', index=True, comment='通知状态：sent, failed, pending')
    notification_message = Column(Text, nullable=True, comment='通知消息内容')
    error_message = Column(Text, nullable=True, comment='错误信息（如果失败）')
    auto_notify = Column(Boolean, default=False, index=True, comment='是否自动通知（True=自动通知，False=手动通知）')
    postback_url = Column(Text, nullable=True, comment='Postback URL（转发通知时使用）')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='创建时间')

    # 关系
    conversion = relationship("PostbackConversion", foreign_keys=[conversion_id])
    client = relationship("Client", foreign_keys=[client_id])
    product = relationship("Product", foreign_keys=[product_id])
    publisher = relationship("Publisher", foreign_keys=[publisher_id])

    __table_args__ = (
        Index("idx_postback_notification_conversion", "conversion_id"),
        Index("idx_postback_notification_client", "client_id"),
        Index("idx_postback_notification_product", "product_id"),
        Index("idx_postback_notification_publisher", "publisher_id"),
        Index("idx_postback_notification_status", "notification_status"),
        Index("idx_postback_notification_auto_notify", "auto_notify"),
        Index("idx_postback_notification_created_at", "created_at"),
    )

class ShortLink(Base):
    """
    短链接

    短链接实体，可绑定 Offer/渠道与 Facebook 像素。
    表名: short_links
    """
    __tablename__ = "short_links"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='短链接 ID')
    short_code = Column(String(20), unique=True, nullable=False, comment='短链接代码（唯一）')
    original_url = Column(Text, nullable=False, comment='原始 URL')
    title = Column(String(200), nullable=True, comment='短链接标题（可选）')
    description = Column(Text, nullable=True, comment='短链接描述（可选）')
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True, comment='创建者用户 ID')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的 Offer ID')
    channel_id = Column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的渠道 ID（Publisher ID）')
    click_count = Column(Integer, default=0, comment='点击次数')
    show_count = Column(Integer, default=0, comment='展示次数')
    is_active = Column(Boolean, default=True, comment='是否激活')
    expires_at = Column(DateTime, nullable=True, comment='过期时间（可选）')
    
    # Facebook 像素配置字段
    facebook_pixel_id = Column(String(50), nullable=True, comment='Facebook 像素 ID')
    facebook_access_token = Column(String(500), nullable=True, comment='Facebook 访问令牌')
    facebook_api_version = Column(String(20), nullable=True, comment='Facebook API 版本')

    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    creator = relationship("User", foreign_keys=[created_by])
    offer = relationship("Offer", foreign_keys=[offer_id])
    channel = relationship("Publisher", foreign_keys=[channel_id])

    __table_args__ = (
        Index("idx_short_link_created_by", "created_by"),
        Index("idx_short_link_offer_id", "offer_id"),
        Index("idx_short_link_channel_id", "channel_id"),
        Index("idx_short_link_active", "is_active"),
        Index("idx_short_link_created_at", "created_at"),
    )


# ==================== CPL 系统数据模型 ====================

class PendingPostbackConversion(Base):
    """
    待确认 Postback 转化记录模型
    
    用于存储不在白名单中的 IP 发送的 postback 数据，等待管理员确认是否保存
    表名: pending_postback_conversions
    """
    __tablename__ = "pending_postback_conversions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='待确认记录ID')
    platform = Column(String(50), nullable=False, index=True, comment='平台名称')
    conversion_id = Column(String(255), nullable=False, comment='转化ID')
    event_name = Column(String(100), nullable=True, comment='事件名称')
    event_value = Column(Numeric(12, 4), nullable=True, comment='事件价值')
    original_payout = Column(Numeric(12, 4), nullable=True, comment='原始支付金额（PO）')
    payout = Column(Numeric(12, 4), nullable=True, comment='扣后支付金额（PO(扣)）')
    
    # 设备信息
    devad_id = Column(String(255), nullable=True, comment='设备广告ID')
    os = Column(String(20), nullable=True, comment='操作系统')
    carrier = Column(String(50), nullable=True, comment='用户运营商')
    ip = Column(String(50), nullable=True, comment='IP地址')
    gid = Column(String(100), nullable=True, comment='渠道ID')
    
    # 关联信息
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, comment='关联的产品ID')
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, comment='关联的客户ID')
    click_id = Column(String(255), nullable=True, comment='关联的Click ID')
    click_time = Column(DateTime, nullable=True, comment='点击时间')
    
    # 原始数据（JSON格式）
    raw_data = Column(Text, nullable=True, comment='原始回调数据（JSON格式）')
    
    # 状态信息
    request_ip = Column(String(50), nullable=False, index=True, comment='请求IP地址（不在白名单）')
    status = Column(String(20), default='pending', index=True, comment='状态：pending(待确认)/approved(已批准)/rejected(已拒绝)')
    telegram_message_id = Column(Integer, nullable=True, comment='Telegram 消息ID（用于更新消息）')
    telegram_chat_id = Column(String(50), nullable=True, comment='Telegram Chat ID')
    
    # 时间戳
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive, onupdate=get_app_now_naive, nullable=False, comment='更新时间')
    approved_at = Column(DateTime, nullable=True, comment='批准时间')
    rejected_at = Column(DateTime, nullable=True, comment='拒绝时间')
    
    __table_args__ = (
        Index("idx_status", "status"),
        Index("idx_request_ip", "request_ip"),
        Index("idx_created_at", "created_at"),
        Index("idx_pending_click_id", "click_id"),
    )

