"""
数据模型模块
定义所有数据库表的ORM模型，包括用户、客户、产品、广告数据等核心业务模型

本模块使用SQLAlchemy 2.0+的声明式基类，支持异步操作
所有模型都继承自Base，通过SQLAlchemy ORM映射到数据库表

注意事项：
1. 所有时间字段使用get_app_now_naive()获取北京时间（naive datetime）
2. 密码使用bcrypt加密存储，最大支持72字节
3. 外键关系使用cascade选项控制级联操作
4. 索引优化查询性能，复合索引用于常见查询场景
"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Enum, Text, Index, \
    UniqueConstraint, Date
from sqlalchemy.orm import declarative_base  # SQLAlchemy 2.0+ 推荐方式
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid
from passlib.context import CryptContext
from app.core.utils import get_app_now_naive

# ====== 密码加密配置 ======
# 使用bcrypt算法进行密码哈希
# deprecated="auto"表示自动处理弃用警告
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ====== SQLAlchemy基类 ======
# 所有模型类都继承自Base，用于ORM映射
Base = declarative_base()


# ====== 枚举类型定义 ======

class UserRole(str, enum.Enum):
    """
    用户角色枚举
    
    角色说明：
    - ADMIN: 管理员，拥有所有权限，可以管理用户、客户、产品等
    - CLIENT: 客户，只能查看和操作分配给自己的数据
    
    使用字符串枚举类型，便于数据库存储和序列化
    """
    ADMIN = "admin"      # 管理员角色
    CLIENT = "client"    # 客户角色


# ====== 用户和权限相关模型 ======

class User(Base):
    """
    用户模型
    
    存储系统用户的基本信息，包括登录凭证、角色权限等
    一个用户可以有多个客户（Client），通过一对多关系关联
    
    表名: users
    
    字段说明：
    - id: 用户唯一标识，自增主键
    - username: 登录用户名，唯一且必填，最大50字符
    - hashed_password: 加密后的密码，使用bcrypt算法，最大191字符（MySQL限制）
    - full_name: 用户全名，可选
    - email: 用户邮箱，唯一且可选，用于找回密码等
    - role: 用户角色，枚举类型（ADMIN/CLIENT），默认CLIENT
    - is_active: 是否激活，False时无法登录
    - login_restricted: 是否限制登录，True时显示login_message
    - login_message: 登录限制提示消息，当login_restricted=True时显示
    - created_at: 创建时间，自动设置为当前时间（北京时间）
    - updated_at: 更新时间，每次更新时自动更新为当前时间
    
    关系：
    - clients: 一对多关系，一个用户可以有多个客户
    
    方法：
    - verify_password(password): 验证密码是否正确
    - get_password_hash(password): 获取密码的哈希值
    - set_password(password): 设置用户密码（自动加密）
    """
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
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    clients = relationship("Client", back_populates="user", cascade="all, delete-orphan")

    def verify_password(self, password: str) -> bool:
        """
        验证用户密码是否正确
        
        Args:
            password: 待验证的明文密码
            
        Returns:
            bool: 密码正确返回True，否则返回False
            
        示例:
            if user.verify_password("my_password"):
                # 密码验证成功
                pass
        """
        return pwd_context.verify(password, self.hashed_password)

    def get_password_hash(self, password: str) -> str:
        """
        获取密码的bcrypt哈希值
        
        注意：bcrypt算法最大支持72字节的密码，超过部分会被截断
        这是bcrypt算法的限制，不是bug
        
        Args:
            password: 明文密码
            
        Returns:
            str: 加密后的密码哈希值
            
        示例:
            hashed = user.get_password_hash("my_password")
        """
        # bcrypt算法限制：密码最大72字节，超过部分会被截断
        from app.core.constants import BCRYPT_MAX_PASSWORD_LENGTH
        truncated_password = password.encode('utf-8')[:BCRYPT_MAX_PASSWORD_LENGTH].decode('utf-8', errors='ignore')
        return pwd_context.hash(truncated_password)
    
    def set_password(self, password: str) -> None:
        """
        设置用户密码（自动加密存储）
        
        这是设置密码的推荐方法，会自动调用get_password_hash进行加密
        
        Args:
            password: 明文密码
            
        示例:
            user.set_password("new_password")
            # 密码已自动加密并存储到hashed_password字段
        """
        self.hashed_password = self.get_password_hash(password)


class Client(Base):
    """
    客户模型
    
    代表系统中的客户（公司），一个客户可以有多个产品
    客户通过user_id关联到User模型，实现用户-客户的多对一关系
    
    表名: clients
    
    字段说明：
    - id: 客户唯一标识，自增主键
    - user_id: 关联的用户ID，外键，必填
    - key: 客户唯一标识UUID，用于API访问认证，唯一且必填
    - company_name: 公司名称，必填，最大100字符
    - contact_person: 联系人姓名，可选，最大50字符
    - phone: 联系电话，可选，最大20字符
    - address: 公司地址，可选，文本类型
    - allowed_ips: IP白名单，多个IP用逗号分隔，为空则不限制IP访问
    - is_active: 是否激活，False时客户无法访问系统
    - api_enabled: 是否允许API访问，True时显示API对接菜单并允许通过API查询数据
    - password_change_enabled: 是否允许客户修改密码，True时客户可以修改自己的登录密码
    - created_at: 创建时间，自动设置为当前时间
    - updated_at: 更新时间，每次更新时自动更新
    
    关系：
    - user: 多对一关系，关联到User模型
    - products: 一对多关系，一个客户可以有多个产品，级联删除
    
    索引：
    - idx_client_user: 优化通过user_id查询客户的性能
    """
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
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系定义
    user = relationship("User", back_populates="clients")
    products = relationship("Product", back_populates="client", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_client_user", "user_id"),  # 优化通过user_id查询客户的性能
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
    downstream_postback_success_check = Column(Text, nullable=True, comment='下游转发成功检查配置（JSON格式，用于检查响应内容是否表示成功）')
    notification_address = Column(String(500), nullable=True, comment='通知地址（Telegram Chat ID、邮箱地址、Webhook URL等，用于接收转化通知）')
    is_active = Column(Boolean, default=True, comment='是否激活')
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

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
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

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
    
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive, onupdate=get_app_now_naive, comment='更新时间')

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
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

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
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

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
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True,
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
    platform = Column(String(50), nullable=False, index=True, comment='平台名称：bft等')
    conversion_id = Column(String(255), nullable=False, comment='转化ID（各平台唯一标识，如clk_id）')
    event_name = Column(String(100), nullable=True, index=True, comment='事件名称')
    event_value = Column(Float, nullable=True, comment='事件价值（购买价格等）')
    original_payout = Column(Float, nullable=True, comment='原始支付金额（PO）')
    payout = Column(Float, nullable=True, comment='扣后支付金额（PO(扣)）')

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
    next_retry_time = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='下次重试时间')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='创建时间')

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
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

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
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    product = relationship("Product", foreign_keys=[product_id])

    __table_args__ = (
        Index("idx_product_notification_config_product", "product_id"),
        Index("idx_product_notification_config_enabled", "notification_enabled"),
    )


# 管理员通知配置模型（单例模式，只有一条记录）
class AdminNotificationConfig(Base):
    __tablename__ = "admin_notification_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='配置ID（固定为1）')
    telegram_enabled = Column(Boolean, default=True, comment='是否启用 Telegram 通知')
    telegram_chat_id = Column(String(100), nullable=True, comment='管理员 Telegram Chat ID')
    notify_all_conversions = Column(Boolean, default=True, comment='通知所有转化')
    notify_forward_failure = Column(Boolean, default=True, comment='通知转发失败')
    notify_forward_success = Column(Boolean, default=False, comment='通知转发成功（可选）')
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


# Postback 通知记录模型
class PostbackNotification(Base):
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


# 短链接模型
class ShortLink(Base):
    __tablename__ = "short_links"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='短链接ID')
    short_code = Column(String(20), unique=True, nullable=False, index=True, comment='短链接代码（唯一）')
    original_url = Column(Text, nullable=False, comment='原始URL')
    title = Column(String(200), nullable=True, comment='短链接标题（可选）')
    description = Column(Text, nullable=True, comment='短链接描述（可选）')
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True, comment='创建者用户ID')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的Offer ID')
    channel_id = Column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的渠道ID（Publisher ID）')
    click_count = Column(Integer, default=0, comment='点击次数')
    is_active = Column(Boolean, default=True, comment='是否激活')
    expires_at = Column(DateTime, nullable=True, comment='过期时间（可选）')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    creator = relationship("User", foreign_keys=[created_by])
    offer = relationship("Offer", foreign_keys=[offer_id])
    channel = relationship("Publisher", foreign_keys=[channel_id])

    __table_args__ = (
        Index("idx_short_link_code", "short_code"),
        Index("idx_short_link_created_by", "created_by"),
        Index("idx_short_link_offer_id", "offer_id"),
        Index("idx_short_link_channel_id", "channel_id"),
        Index("idx_short_link_active", "is_active"),
        Index("idx_short_link_created_at", "created_at"),
    )


# ==================== CPL 系统数据模型 ====================

# 广告主模型（上游）
class Advertiser(Base):
    __tablename__ = "advertisers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='广告主ID')
    advertiser_name = Column(String(100), nullable=False, index=True, comment='广告主名称')
    email = Column(String(255), nullable=True, comment='邮箱（可选）')
    mobile = Column(String(20), nullable=True, comment='手机号')
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


# 渠道模型（下游）
class Publisher(Base):
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


# Offer模型（单子）
class Offer(Base):
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


# Offer-渠道分配模型
class OfferPublisherAssignment(Base):
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


# 点击记录模型
class Click(Base):
    __tablename__ = "clicks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='点击记录ID')
    click_id = Column(String(255), unique=True, nullable=False, index=True, comment='点击ID（系统生成，唯一标识）')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的Offer ID')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的渠道ID')
    advertiser_id = Column(Integer, ForeignKey("advertisers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的广告主ID')
    short_link_id = Column(Integer, ForeignKey("short_links.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的短链接ID')
    click_time = Column(DateTime, nullable=False, index=True, comment='点击时间')
    ip = Column(String(50), nullable=True, comment='点击IP地址')
    device = Column(String(100), nullable=True, comment='设备信息（兼容旧字段）')
    country = Column(String(50), nullable=True, comment='国家')
    user_agent = Column(Text, nullable=True, comment='User Agent')
    referer = Column(Text, nullable=True, comment='来源页面')
    conversion_id = Column(Integer, nullable=True, index=True, comment='关联的转化ID（如果已转化）')
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
    device_type = Column(String(20), nullable=True, index=True, comment='设备类型（mobile/tablet/desktop）')
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
        Index("idx_click_id", "click_id"),
        Index("idx_offer_id", "offer_id"),
        Index("idx_publisher_id", "publisher_id"),
        Index("idx_advertiser_id", "advertiser_id"),
        Index("idx_short_link_id", "short_link_id"),
        Index("idx_click_time", "click_time"),
        Index("idx_conversion_id", "conversion_id"),
        # 性能优化索引
        Index("idx_ip", "ip"),  # IP字段索引，用于IP查询优化
        Index("idx_country", "country"),  # 国家字段索引
        # 复合索引：优化常见查询组合（日期范围 + 其他条件）
        Index("idx_click_time_offer", "click_time", "offer_id"),
        Index("idx_click_time_publisher", "click_time", "publisher_id"),
        Index("idx_click_time_offer_publisher", "click_time", "offer_id", "publisher_id"),
    )


# 点击统计模型（轻量级，用于转化统计）
class ClickStats(Base):
    """
    点击统计表（轻量级，用于转化统计）
    只保存有转化的点击记录的核心字段，长期保留，不会被清理
    """
    __tablename__ = "click_stats"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='统计记录ID')
    click_id = Column(String(255), unique=True, nullable=False, index=True, comment='点击ID（系统生成，唯一标识）')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的Offer ID')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的渠道ID')
    advertiser_id = Column(Integer, ForeignKey("advertisers.id", ondelete="SET NULL"), nullable=True, index=True, comment='关联的广告主ID')
    click_time = Column(DateTime, nullable=False, index=True, comment='点击时间')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')
    
    __table_args__ = (
        Index("idx_click_stats_time_offer_publisher", "click_time", "offer_id", "publisher_id"),
        Index("idx_click_stats_offer_publisher", "offer_id", "publisher_id"),
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


# 扣量配置模型
class OfferDiscount(Base):
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


# 上游测试记录模型（已废弃，保留模型定义以兼容现有数据库表）
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
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间')

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

# 转化扣减配置模型
class ConversionDeductionConfig(Base):
    __tablename__ = "conversion_deduction_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='配置ID')
    
    # 配置层级（三选一）
    advertiser_id = Column(Integer, ForeignKey("advertisers.id", ondelete="CASCADE"), nullable=True, index=True, comment='广告主ID（如果配置在广告主级别）')
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=True, index=True, comment='Offer ID（如果配置在Offer级别）')
    publisher_id = Column(Integer, ForeignKey("publishers.id", ondelete="CASCADE"), nullable=True, index=True, comment='渠道ID（如果配置在渠道级别）')
    
    # 扣减类型配置
    volume_deduction_ratio = Column(Float, default=0.0, comment='按比例扣量比例（0-1，如0.10表示扣量10%）')
    amount_deduction_ratio = Column(Float, default=0.0, comment='按比例扣金额比例（0-1，如0.10表示扣金额10%）')
    
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


# 转化扣减执行记录模型
class ConversionDeductionLog(Base):
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
    original_amount = Column(Float, nullable=False, comment='原始转化金额')
    
    # 扣减后数据
    deducted_volume = Column(Integer, default=0, comment='扣减的转化数量')
    deducted_amount = Column(Float, default=0.0, comment='扣减的转化金额')
    final_volume = Column(Integer, default=1, comment='最终转化数量（扣减后）')
    final_amount = Column(Float, nullable=False, comment='最终转化金额（扣减后）')
    
    # 扣减配置信息
    deduction_config_id = Column(Integer, ForeignKey("conversion_deduction_configs.id", ondelete="SET NULL"), nullable=True, index=True, comment='使用的扣减配置ID')
    volume_deduction_ratio = Column(Float, nullable=True, comment='使用的扣量比例')
    amount_deduction_ratio = Column(Float, nullable=True, comment='使用的扣金额比例')
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


# 待确认 Postback 转化记录模型（不在白名单的 IP 发送的转化数据）
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
    event_value = Column(Float, nullable=True, comment='事件价值')
    original_payout = Column(Float, nullable=True, comment='原始支付金额（PO）')
    payout = Column(Float, nullable=True, comment='扣后支付金额（PO(扣)）')
    
    # 设备信息
    devad_id = Column(String(255), nullable=True, comment='设备广告ID')
    os = Column(String(20), nullable=True, comment='操作系统')
    carrier = Column(String(50), nullable=True, comment='用户运营商')
    ip = Column(String(50), nullable=True, comment='IP地址')
    gid = Column(String(100), nullable=True, comment='渠道ID')
    
    # 关联信息
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, comment='关联的产品ID')
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, comment='关联的客户ID')
    click_id = Column(String(255), nullable=True, index=True, comment='关联的Click ID')
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
    )


# Postback IP 白名单模型
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