from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Enum, Text, Index, \
    UniqueConstraint, Date
from sqlalchemy.orm import declarative_base  # SQLAlchemy 2.0+ 推荐方式
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
import uuid
from passlib.context import CryptContext

# 创建密码上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

Base = declarative_base()


# 用户角色枚举
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CLIENT = "client"


# 用户模型
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='用户ID')
    username = Column(String(50), unique=True, index=True, nullable=False, comment='用户名称(登录名称)')
    hashed_password = Column('hashed_password', String(191), nullable=False, comment='用户Hash密码')
    full_name = Column(String(100), comment='用户全名')
    email = Column(String(100), unique=True, index=True, comment='用户邮箱')
    role = Column(Enum(UserRole, values_callable=lambda obj: [e.value for e in UserRole], create_constraint=True), 
                  default=UserRole.CLIENT, nullable=False,
                  comment='用户角色(ADMIN 管理员 / CLIENT 客户)')
    is_active = Column(Boolean, default=True, comment='是否激活')
    login_restricted = Column(Boolean, default=False, comment='是否限制登录')
    login_message = Column(Text, comment='登录提示消息')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    clients = relationship("Client", back_populates="user", cascade="all, delete-orphan")

    def verify_password(self, password: str) -> bool:
        return pwd_context.verify(password, self.hashed_password)

    def get_password_hash(self, password: str) -> str:
        # Truncate password to 72 bytes before hashing
        truncated_password = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
        return pwd_context.hash(password)


# 客户模型
class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='客户ID')
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment='用户ID')
    key = Column(String(36), nullable=False, unique=True, index=True, comment='客户唯一标识UUID')
    company_name = Column(String(100), nullable=False, comment='公司名称')
    contact_person = Column(String(50), comment='联系人')
    phone = Column(String(20), comment='联系电话')
    address = Column(Text, comment='公司地址')
    allowed_ips = Column(Text, comment='IP白名单，多个IP用逗号分隔，为空则不限制')
    is_active = Column(Boolean, default=True, comment='是否激活')
    api_enabled = Column(Boolean, default=False, comment='是否允许API访问（开启后允许客户通过API查询产品和广告数据，并显示API对接菜单）')
    password_change_enabled = Column(Boolean, default=False, comment='是否允许客户修改密码（开启后客户可以修改自己的密码）')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    user = relationship("User", back_populates="clients")
    products = relationship("Product", back_populates="client", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_client_user", "user_id"),  # 优化用户查询
    )


# 产品模型
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='产品ID')
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    name = Column(String(100), nullable=False, comment='产品名称')
    ecpm_deduct_ratio = Column(Float, default=0.0, comment='eCPM减扣比例')
    revenue_deduct_ratio = Column(Float, default=0.0, comment='收益减扣比例')
    downstream_postback_url = Column(String(500), nullable=True, comment='下游 Postback URL（可选，配置后将自动转发转化数据）')
    downstream_postback_method = Column(String(10), default='GET', comment='下游 Postback 请求方式：GET 或 POST（默认GET）')
    notification_address = Column(String(500), nullable=True, comment='通知地址（Telegram Chat ID、邮箱地址、Webhook URL等，用于接收转化通知）')
    is_active = Column(Boolean, default=True, comment='是否激活')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    client = relationship("Client", back_populates="products")
    ad_data = relationship("AdData", back_populates="product")
    assignments = relationship("ProductAssignment", back_populates="product", cascade="all, delete-orphan")
    tb_search_data = relationship("TBSearchData", back_populates="product")

    __table_args__ = (
        Index("idx_product_client", "client_id"),
        Index("idx_product_name", "name"),  # 优化产品名称查询
    )


# 广告数据模型
class AdData(Base):
    __tablename__ = "ad_data"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='广告数据ID')
    date = Column(DateTime, nullable=False, comment='数据日期')

    # 国家代码字段（ISO 3166-1 二字母代码）
    country_code = Column(String(2), ForeignKey("countries.alpha_2_code", ondelete="SET NULL", onupdate="CASCADE"), nullable=True, comment='国家代码（ISO 3166-1 二字母代码）')

    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, comment='产品ID')
    request_count = Column(Integer, default=0, comment='请求数')
    match_count = Column(Integer, default=0, comment='匹配数')
    coverage_rate = Column(Float, default=0.0, comment='覆盖率（%）')
    display_count = Column(Integer, default=0, comment='展示数')
    display_rate = Column(Float, default=0.0, comment='展示率（%）')
    click_count = Column(Integer, default=0, comment='点击数')
    click_rate = Column(Float, default=0.0, comment='点击率（%）')
    viewability_rate = Column(Float, default=0.0, comment='可见率（%）')
    cpc = Column(Float, default=0.0, comment='CPC')
    pageviews = Column(Integer, default=0, comment='PageViews')
    ecpm_before_deduct = Column(Float, default=0.0, comment='eCPM未减扣')
    ecpm_after_deduct = Column(Float, default=0.0, comment='eCPM已减扣')
    revenue_before_deduct = Column(Float, default=0.0, comment='收益未减扣')
    revenue_after_deduct = Column(Float, default=0.0, comment='收益已减扣')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    __table_args__ = (
        Index("idx_ad_data_date", "date"),  # 优化日期范围查询
        Index("idx_ad_data_product", "product_id"),  # 优化产品查询
        Index("idx_ad_data_date_product", "date", "product_id"),  # 复合索引，优化常见查询
        # 唯一性约束：确保同一日期、产品和国家代码只能有一条记录
        UniqueConstraint("date", "product_id", "country_code", name="uq_ad_data_date_product_country"),
    )

    # 辅助方法：计算并更新比率字段（用于数据插入/更新时自动计算）
    def calculate_rates(self) -> None:
        """
        计算并更新覆盖率、展示率、点击率
        在数据插入或更新时调用此方法，确保这些字段始终是最新的
        """
        # 覆盖率 = 匹配数 / 请求数 * 100
        self.coverage_rate = round(
            (self.match_count / self.request_count * 100) if self.request_count > 0 else 0.0,
            2
        )
        # 展示率 = 展示数 / 匹配数 * 100
        self.display_rate = round(
            (self.display_count / self.match_count * 100) if self.match_count > 0 else 0.0,
            2
        )
        # 点击率 = 点击数 / 展示数 * 100
        self.click_rate = round(
            (self.click_count / self.display_count * 100) if self.display_count > 0 else 0.0,
            2
        )


    # 关系
    product = relationship("Product", back_populates="ad_data")
    country = relationship("CountryInfo", foreign_keys=[country_code])


# TB搜索数据模型
class TBSearchData(Base):
    __tablename__ = "tb_search_data"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='ID')
    date = Column(DateTime, nullable=False, comment='日期')
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, comment='产品ID')
    country_code = Column(String(2), ForeignKey("countries.alpha_2_code", ondelete="SET NULL", onupdate="CASCADE"), nullable=True, comment='国家代码')
    redirects = Column(Integer, default=0, comment='REDIRECTS')
    searches = Column(Integer, default=0, comment='SEARCHES')
    monetized = Column(Integer, default=0, comment='MONETIZED')
    clicks = Column(Integer, default=0, comment='CLICKS')

    revenue = Column(Float, default=0.0, comment='REVENUE（扣减后）')
    rpm = Column(Float, default=0.0, comment='RPM（扣减后）')
    
    revenue_before_deduct = Column(Float, default=0.0, comment='REVENUE（扣减前）')
    rpm_before_deduct = Column(Float, default=0.0, comment='RPM（扣减前）')
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    product = relationship("Product", back_populates="tb_search_data")
    country = relationship("CountryInfo", foreign_keys=[country_code])

    __table_args__ = (
        Index("idx_tb_search_data_date", "date"),
        Index("idx_tb_search_data_product", "product_id"),
        Index("idx_tb_search_data_date_product", "date", "product_id"),
        # 唯一性约束
        UniqueConstraint("date", "product_id", "country_code", name="uq_tb_search_data_date_product_country"),
    )


# 产品分配历史模型
class ProductAssignment(Base):
    __tablename__ = "product_assignments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='分配记录ID')
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, comment='产品ID')
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, comment='客户ID')
    start_date = Column(Date, nullable=False, comment='分配开始日期')
    end_date = Column(Date, nullable=True, comment='分配结束日期（NULL表示当前有效）')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    product = relationship("Product", back_populates="assignments")
    client = relationship("Client")

    __table_args__ = (
        Index("idx_product_assignments_product", "product_id"),
        Index("idx_product_assignments_client", "client_id"),
        Index("idx_product_assignments_date", "product_id", "start_date", "end_date"),
        Index("idx_product_assignments_active", "product_id", "end_date"),
    )


# 定时任务执行记录表（用于多进程环境下确保任务只执行一次）
class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='定时任务ID')
    task_name = Column(String(100), nullable=False, unique=True, index=True, comment='任务名称（唯一）')
    last_run_time = Column(DateTime, nullable=True, comment='上次执行时间')
    is_running = Column(Boolean, default=False, comment='是否正在执行')
    last_run_pid = Column(Integer, nullable=True, comment='上次执行的进程ID')
    last_run_host = Column(String(100), nullable=True, comment='上次执行的服务器主机名')
    run_count = Column(Integer, default=0, comment='执行次数')
    success_count = Column(Integer, default=0, comment='成功次数')
    error_count = Column(Integer, default=0, comment='失败次数')
    last_error = Column(Text, nullable=True, comment='最后一次错误信息')
    is_active = Column(Boolean, default=True, comment='是否启用')
    cron_expression = Column(String(100), nullable=True, comment='Cron表达式')
    description = Column(Text, nullable=True, comment='任务描述')
    function_path = Column(String(255), nullable=True,
                           comment='执行函数路径（例如：app.scheduler_module.tasks.simple_task.simple_info_task）')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    __table_args__ = (
        Index("idx_scheduled_task_name", "task_name"),
        Index("idx_scheduled_task_is_running", "is_running"),
        Index("idx_scheduled_task_is_active", "is_active"),
    )


# 用户操作日志表（审计日志）
class UserAuditLog(Base):
    __tablename__ = "user_audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='日志ID')
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True,
                     comment='用户ID（可为空，记录未登录访问）')
    username = Column(String(50), nullable=True, index=True, comment='用户名（冗余字段，便于查询）')
    action_type = Column(String(50), nullable=False, index=True,
                         comment='操作类型：LOGIN, LOGOUT, CREATE, UPDATE, DELETE, VIEW, ACCESS等')
    resource_type = Column(String(50), nullable=True, index=True,
                           comment='资源类型：USER, CLIENT, PRODUCT, AD_DATA, SCHEDULED_TASK等')
    resource_id = Column(Integer, nullable=True, comment='资源ID')
    resource_name = Column(String(255), nullable=True, comment='资源名称（冗余字段，便于查询）')
    ip_address = Column(String(50), nullable=True, index=True, comment='IP地址')
    user_agent = Column(String(500), nullable=True, comment='用户代理（浏览器信息）')
    request_method = Column(String(10), nullable=True, comment='HTTP请求方法')
    request_path = Column(String(500), nullable=True, index=True, comment='请求路径')
    request_params = Column(Text, nullable=True, comment='请求参数（JSON格式，不包含敏感信息）')
    status_code = Column(Integer, nullable=True, comment='HTTP状态码')
    success = Column(Boolean, default=True, index=True, comment='操作是否成功')
    error_message = Column(Text, nullable=True, comment='错误信息（如果失败）')
    details = Column(Text, nullable=True, comment='详细信息（JSON格式）')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True,
                        comment='创建时间')

    # 关系
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_audit_log_user_action", "user_id", "action_type"),
        Index("idx_audit_log_created_at", "created_at"),
        Index("idx_audit_log_resource", "resource_type", "resource_id"),
    )


# 国家信息模型（ISO 3166-1标准）
class CountryInfo(Base):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='ID')
    alpha_2_code = Column(String(2), unique=True, nullable=False, index=True, comment='国家二字代码')
    alpha_3_code = Column(String(3), unique=True, nullable=False, index=True, comment='国家三字代码')
    numeric_code = Column(String(3), nullable=False, comment='国家数字代码')
    country_name_zh = Column(String(100), nullable=False, index=True, comment='国家中文名称')
    country_name_en = Column(String(100), nullable=False, index=True, comment='国家英文名称')
    official_name_zh = Column(String(150), nullable=True, comment='官方中文名称')
    official_name_en = Column(String(150), nullable=True, comment='官方英文名称')
    independent_status = Column(Boolean, default=True, comment='是否独立国家')
    continent = Column(String(50), nullable=True, index=True, comment='所属大洲')
    subregion = Column(String(50), nullable=True, index=True, comment='所属地区')

    __table_args__ = (
        Index("idx_alpha_2_code", "alpha_2_code"),
        Index("idx_alpha_3_code", "alpha_3_code"),
        Index("idx_numeric_code", "numeric_code"),
        Index("idx_country_name_zh", "country_name_zh"),
        Index("idx_country_name_en", "country_name_en"),
        Index("idx_continent", "continent"),
        Index("idx_subregion", "subregion"),
    )
    
    # 为了向后兼容，提供属性别名
    @property
    def iso_code_2(self) -> str:
        """向后兼容属性：返回 alpha_2_code"""
        return self.alpha_2_code
    
    @property
    def iso_code_3(self) -> str:
        """向后兼容属性：返回 alpha_3_code"""
        return self.alpha_3_code
    
    @property
    def iso_code_numeric(self) -> str:
        """向后兼容属性：返回 numeric_code"""
        return self.numeric_code
    
    @property
    def name_en(self) -> str:
        """向后兼容属性：返回 country_name_en"""
        return self.country_name_en
    
    @property
    def name_zh(self) -> str:
        """向后兼容属性：返回 country_name_zh"""
        return self.country_name_zh


# Postback 转化事件模型
class PostbackConversion(Base):
    __tablename__ = "postback_conversions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='转化记录ID')
    platform = Column(String(50), nullable=False, index=True, comment='平台名称：macan, addermobi等')
    conversion_id = Column(String(255), nullable=False, comment='转化ID（各平台唯一标识，如clk_id）')
    event_name = Column(String(100), nullable=True, index=True, comment='事件名称')
    event_value = Column(Float, nullable=True, comment='事件价值（购买价格等）')
    payout = Column(Float, nullable=True, comment='支付金额（确认的广告单元价格）')

    # 设备信息
    devad_id = Column(String(255), nullable=True, comment='设备广告ID（IDFA或GAID）')
    os = Column(String(20), nullable=True, comment='操作系统（IOS或Android）')
    carrier = Column(String(50), nullable=True, comment='用户运营商')
    ip = Column(String(50), nullable=True, comment='点击IP地址')
    gid = Column(String(100), nullable=True, comment='渠道ID（Channel ID）')

    # 关联信息
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, comment='关联的产品ID')
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, comment='关联的客户ID')
    
    # CPL 系统字段
    click_id = Column(String(255), nullable=True, index=True, comment='关联的Click ID')
    click_time = Column(DateTime, nullable=True, comment='点击时间')
    conversion_status = Column(String(20), default='Pending', index=True, comment='转化状态：Approved/Pending')

    # 原始数据（JSON格式，保存完整回调数据）
    raw_data = Column(Text, nullable=True, comment='原始回调数据（JSON格式）')

    # 元数据
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True, comment='创建时间')

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
        Index("idx_postback_click_id", "click_id"),
        Index("idx_postback_conversion_status", "conversion_status"),
        # 唯一性约束：同一平台的同一转化ID只能有一条记录（防止重复处理）
        UniqueConstraint("platform", "conversion_id", "event_name", name="uq_postback_platform_conversion_event"),
    )


# Postback 下游转发日志模型
class PostbackForwardLog(Base):
    __tablename__ = "postback_forward_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='转发日志ID')
    conversion_id = Column(Integer, ForeignKey("postback_conversions.id", ondelete="CASCADE"), nullable=False, index=True, comment='关联的转化记录ID')
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True, comment='产品ID')
    downstream_url = Column(String(500), nullable=False, comment='下游URL')
    request_method = Column(String(10), nullable=False, comment='请求方式：GET 或 POST')
    request_data = Column(Text, nullable=True, comment='请求数据（JSON格式，用于POST请求）')
    request_params = Column(Text, nullable=True, comment='请求参数（URL参数，用于GET请求）')
    response_status = Column(Integer, nullable=True, comment='响应状态码')
    response_body = Column(Text, nullable=True, comment='响应内容')
    success = Column(Boolean, default=False, index=True, comment='是否转发成功')
    error_message = Column(Text, nullable=True, comment='错误信息（如果转发失败）')
    retry_count = Column(Integer, default=0, comment='重试次数')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True, comment='创建时间')
    completed_at = Column(DateTime, nullable=True, comment='完成时间')

    # 关系
    conversion = relationship("PostbackConversion", foreign_keys=[conversion_id])
    product = relationship("Product", foreign_keys=[product_id])

    __table_args__ = (
        Index("idx_forward_log_conversion", "conversion_id"),
        Index("idx_forward_log_product", "product_id"),
        Index("idx_forward_log_created_at", "created_at"),
        Index("idx_forward_log_success", "success"),
    )


# Postback 转发队列模型
class PostbackForwardQueue(Base):
    __tablename__ = "postback_forward_queue"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='队列ID')
    conversion_id = Column(Integer, ForeignKey("postback_conversions.id", ondelete="CASCADE"), nullable=False, index=True, comment='关联的转化记录ID')
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True, comment='产品ID')
    downstream_url = Column(String(500), nullable=False, comment='下游URL')
    request_method = Column(String(10), nullable=False, comment='请求方式：GET 或 POST')
    request_data = Column(Text, nullable=True, comment='请求数据（JSON格式，用于POST请求）')
    request_params = Column(Text, nullable=True, comment='请求参数（URL参数，用于GET请求）')
    retry_count = Column(Integer, default=0, comment='已重试次数')
    next_retry_time = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True, comment='下次重试时间')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True, comment='创建时间')

    # 关系
    conversion = relationship("PostbackConversion", foreign_keys=[conversion_id])
    product = relationship("Product", foreign_keys=[product_id])

    __table_args__ = (
        Index("idx_forward_queue_time", "next_retry_time"),
        Index("idx_forward_queue_conversion", "conversion_id"),
    )


# 客户通知配置模型
class ClientNotificationConfig(Base):
    __tablename__ = "client_notification_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='通知配置ID')
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True, comment='客户ID')
    notification_enabled = Column(Boolean, default=True, comment='是否启用通知')
    notify_on_conversion = Column(Boolean, default=True, comment='转化时通知')
    notify_on_high_value = Column(Boolean, default=False, comment='高价值转化通知')
    high_value_threshold = Column(Float, nullable=True, comment='高价值阈值')
    notify_channels = Column(Text, nullable=True, comment='通知渠道（JSON格式：["telegram", "email", "sms"]）')
    telegram_chat_id = Column(String(100), nullable=True, comment='Telegram Chat ID')
    email_address = Column(String(255), nullable=True, comment='邮箱地址')
    phone_number = Column(String(20), nullable=True, comment='手机号')
    notification_frequency = Column(String(20), default='realtime', comment='通知频率：realtime, hourly, daily')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    client = relationship("Client", foreign_keys=[client_id])

    __table_args__ = (
        Index("idx_client_notification_config_client", "client_id"),
        Index("idx_client_notification_config_enabled", "notification_enabled"),
    )


# 产品通知配置模型
class ProductNotificationConfig(Base):
    __tablename__ = "product_notification_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='通知配置ID')
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, unique=True, index=True, comment='产品ID')
    notification_enabled = Column(Boolean, default=True, comment='是否启用通知')
    notify_on_conversion = Column(Boolean, default=True, comment='转化时通知')
    notify_on_high_value = Column(Boolean, default=False, comment='高价值转化通知')
    high_value_threshold = Column(Float, nullable=True, comment='高价值阈值')
    notify_channels = Column(Text, nullable=True, comment='通知渠道（JSON格式：["telegram", "email", "sms"]）')
    telegram_chat_id = Column(String(100), nullable=True, comment='Telegram Chat ID')
    email_address = Column(String(255), nullable=True, comment='邮箱地址')
    phone_number = Column(String(20), nullable=True, comment='手机号')
    notification_frequency = Column(String(20), default='realtime', comment='通知频率：realtime, hourly, daily')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    product = relationship("Product", foreign_keys=[product_id])

    __table_args__ = (
        Index("idx_product_notification_config_product", "product_id"),
        Index("idx_product_notification_config_enabled", "notification_enabled"),
    )


# Postback 通知记录模型
class PostbackNotification(Base):
    __tablename__ = "postback_notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='通知记录ID')
    conversion_id = Column(Integer, ForeignKey("postback_conversions.id", ondelete="CASCADE"), nullable=False, index=True, comment='转化记录ID')
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True, comment='客户ID')
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True, comment='产品ID')
    notification_type = Column(String(50), nullable=True, comment='通知类型：conversion, high_value, error')
    notification_channel = Column(String(50), nullable=False, comment='通知渠道：telegram, email, sms')
    notification_status = Column(String(20), default='pending', index=True, comment='通知状态：sent, failed, pending')
    notification_message = Column(Text, nullable=True, comment='通知消息内容')
    error_message = Column(Text, nullable=True, comment='错误信息（如果失败）')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True, comment='创建时间')

    # 关系
    conversion = relationship("PostbackConversion", foreign_keys=[conversion_id])
    client = relationship("Client", foreign_keys=[client_id])
    product = relationship("Product", foreign_keys=[product_id])

    __table_args__ = (
        Index("idx_postback_notification_conversion", "conversion_id"),
        Index("idx_postback_notification_client", "client_id"),
        Index("idx_postback_notification_product", "product_id"),
        Index("idx_postback_notification_status", "notification_status"),
        Index("idx_postback_notification_created_at", "created_at"),
    )


# 短链接模型
class ShortLink(Base):
    __tablename__ = "short_links"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='短链接ID')
    short_code = Column(String(20), unique=True, nullable=False, index=True, comment='短链接代码（唯一）')
    original_url = Column(Text, nullable=False, comment='原始URL')
    title = Column(String(200), nullable=True, comment='短链接标题（可选）')
    description = Column(Text, nullable=True, comment='短链接描述（可选）')
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True, comment='创建者用户ID')
    click_count = Column(Integer, default=0, comment='点击次数')
    is_active = Column(Boolean, default=True, comment='是否激活')
    expires_at = Column(DateTime, nullable=True, comment='过期时间（可选）')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True, comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("idx_short_link_code", "short_code"),
        Index("idx_short_link_created_by", "created_by"),
        Index("idx_short_link_active", "is_active"),
        Index("idx_short_link_created_at", "created_at"),
    )


# ==================== CPL 系统数据模型 ====================

# 广告主模型（上游）
class Advertiser(Base):
    __tablename__ = "advertisers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='广告主ID')
    advertiser_id = Column(String(50), unique=True, nullable=False, index=True, comment='广告主ID（系统生成，唯一标识）')
    advertiser_name = Column(String(100), nullable=False, index=True, comment='广告主名称')
    email = Column(String(255), nullable=True, comment='邮箱（可选）')
    mobile = Column(String(20), nullable=True, comment='手机号')
    is_active = Column(Boolean, default=True, index=True, comment='是否激活')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    offers = relationship("Offer", back_populates="advertiser", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_advertiser_id", "advertiser_id"),
        Index("idx_advertiser_name", "advertiser_name"),
        Index("idx_is_active", "is_active"),
    )


# 渠道模型（下游）
class Publisher(Base):
    __tablename__ = "publishers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='渠道ID')
    publisher_id = Column(String(50), unique=True, nullable=False, index=True, comment='渠道ID（系统生成，唯一标识）')
    publisher_name = Column(String(100), nullable=False, index=True, comment='渠道名称')
    email = Column(String(255), nullable=True, comment='邮箱（可选）')
    price_discount = Column(Float, default=0.0, comment='渠道级别的价格扣量比例（0-100）')
    postback_url = Column(Text, nullable=True, comment='Postback URL（渠道的Postback配置）')
    postback_method = Column(String(10), default='GET', comment='Postback请求方式：GET/POST')
    active_advertiser_count = Column(Integer, default=0, comment='活跃的广告主数量')
    is_active = Column(Boolean, default=True, index=True, comment='是否激活')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    offer_assignments = relationship("OfferPublisherAssignment", back_populates="publisher", cascade="all, delete-orphan")
    clicks = relationship("Click", back_populates="publisher")
    discounts = relationship("OfferDiscount", back_populates="publisher", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_publisher_name", "publisher_name"),
        Index("idx_is_active", "is_active"),
    )


# Offer模型（单子）
class Offer(Base):
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='Offer ID（主键）')
    offer_id = Column(String(50), unique=True, nullable=False, index=True, comment='Offer ID（系统生成的唯一标识）')
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    advertiser = relationship("Advertiser", back_populates="offers")
    offer_assignments = relationship("OfferPublisherAssignment", back_populates="offer", cascade="all, delete-orphan")
    clicks = relationship("Click", back_populates="offer")
    caps = relationship("OfferCap", back_populates="offer", cascade="all, delete-orphan")
    discounts = relationship("OfferDiscount", back_populates="offer", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_offer_id", "offer_id"),
        Index("idx_advertiser_id", "advertiser_id"),
        Index("idx_status", "status"),
        Index("idx_is_active", "is_active"),
        Index("idx_country", "country"),
    )


# Offer-渠道分配模型
class OfferPublisherAssignment(Base):
    __tablename__ = "offer_publisher_assignments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='分配ID')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True, comment='Offer ID')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False, index=True, comment='渠道ID')
    is_active = Column(Boolean, default=True, index=True, comment='是否激活')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    offer = relationship("Offer", back_populates="offer_assignments")
    publisher = relationship("Publisher", back_populates="offer_assignments")

    __table_args__ = (
        UniqueConstraint("offer_id", "publisher_id", name="uq_offer_publisher"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_is_active", "is_active"),
    )


# 点击记录模型
class Click(Base):
    __tablename__ = "clicks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='点击记录ID')
    click_id = Column(String(255), unique=True, nullable=False, index=True, comment='点击ID（系统生成，唯一标识）')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的Offer ID')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的渠道ID')
    advertiser_id = Column(Integer, ForeignKey("advertisers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的广告主ID')
    click_time = Column(DateTime, nullable=False, index=True, comment='点击时间')
    ip = Column(String(50), nullable=True, comment='点击IP地址')
    device = Column(String(100), nullable=True, comment='设备信息')
    country = Column(String(50), nullable=True, comment='国家')
    user_agent = Column(Text, nullable=True, comment='User Agent')
    referer = Column(Text, nullable=True, comment='来源页面')
    conversion_id = Column(Integer, nullable=True, index=True, comment='关联的转化ID（如果已转化）')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, comment='创建时间')

    # 关系
    offer = relationship("Offer", back_populates="clicks")
    publisher = relationship("Publisher", back_populates="clicks")
    advertiser = relationship("Advertiser", foreign_keys=[advertiser_id])

    __table_args__ = (
        Index("idx_click_id", "click_id"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_advertiser_id", "advertiser_id"),
        Index("idx_click_time", "click_time"),
        Index("idx_conversion_id", "conversion_id"),
    )


# Cap配置模型
class OfferCap(Base):
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

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


# 扣量配置模型
class OfferDiscount(Base):
    __tablename__ = "offer_discounts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='扣量配置ID')
    discount_type = Column(String(50), nullable=False, index=True, comment='扣量类型：offer/channel')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=True, index=True, comment='Offer ID（如果是offer类型）')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False, index=True, comment='渠道ID')
    discount_ratio = Column(Float, nullable=False, comment='扣量比例（0-100）')
    is_active = Column(Boolean, default=True, index=True, comment='是否激活')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    offer = relationship("Offer", back_populates="discounts")
    publisher = relationship("Publisher", back_populates="discounts")

    __table_args__ = (
        Index("idx_discount_type", "discount_type"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_is_active", "is_active"),
    )


# 上游测试记录模型
class AdvertiserTest(Base):
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, comment='创建时间')

    # 关系
    advertiser = relationship("Advertiser", foreign_keys=[advertiser_id])
    offer = relationship("Offer", foreign_keys=[offer_id])

    __table_args__ = (
        Index("idx_advertiser_id", "advertiser_id"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_test_time", "test_time"),
    )


# 下游测试记录模型
class AffiliateTest(Base):
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, comment='创建时间')

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