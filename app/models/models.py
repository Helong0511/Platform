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
        # Truncate password to 72 characters as per bcrypt's example
        truncated_password = password[:72]
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
    is_active = Column(Boolean, default=True, comment='是否激活')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment='更新时间')

    # 关系
    client = relationship("Client", back_populates="products")
    ad_data = relationship("AdData", back_populates="product")
    assignments = relationship("ProductAssignment", back_populates="product", cascade="all, delete-orphan")

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
