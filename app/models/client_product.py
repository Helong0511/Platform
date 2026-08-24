"""
客户、产品、广告数据与产品分配 ORM 模型。
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index, \
    UniqueConstraint, Date, Numeric
from sqlalchemy.orm import relationship

from app.core.utils import get_app_now_naive
from app.models.base import Base

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

class Product(Base):
    """
    产品模型

    客户名下的广告产品，关联广告数据、TB 搜索及分配历史。
    表名: products
    """
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='产品ID')
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    name = Column(String(100), nullable=False, comment='产品名称')
    ecpm_deduct_ratio = Column(
        Numeric(12, 4), nullable=False, default=0, server_default='0', comment='eCPM减扣比例'
    )
    revenue_deduct_ratio = Column(
        Numeric(12, 4), nullable=False, default=0, server_default='0', comment='收益减扣比例'
    )
    cplpo_deduct_ratio = Column(
        Numeric(12, 4), nullable=False, default=0, server_default='0', comment='CPL PO减扣比例 '
    )
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

class AdData(Base):
    """
    广告数据模型

    按日期/国家/广告单元存储展示、点击与收益指标。
    表名: ad_data；含 calculate_rates 自动算率
    """
    __tablename__ = "ad_data"

    id = Column(Integer, primary_key=True, autoincrement=True, comment='广告数据ID')
    date = Column(Date, nullable=False, comment='数据日期（仅日期）')

    # 国家代码（ISO 二字母；无法识别时保留完整原始国名，最长 100 字符）
    country_code = Column(String(100), nullable=True, comment='国家代码（ISO 二字母；未识别时保留原始国名）')

    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, comment='产品ID')
    ad_unit = Column(String(150), nullable=False, default='', server_default='', comment='广告单元')
    request_count = Column(Integer, default=0, comment='请求数')
    match_count = Column(Integer, default=0, comment='匹配数')
    coverage_rate = Column(Numeric(7, 4), nullable=False, default=0, server_default='0.0000', comment='覆盖率（%）')
    display_count = Column(Integer, default=0, comment='展示数')
    display_rate = Column(Numeric(7, 4), nullable=False, default=0, server_default='0.0000', comment='展示率（%）')
    click_count = Column(Integer, default=0, comment='点击数')
    click_rate = Column(Numeric(7, 4), nullable=False, default=0, server_default='0.0000', comment='点击率（%）')
    viewability_rate = Column(Numeric(7, 4), nullable=False, default=0, server_default='0.0000', comment='可见率（%）')
    cpc = Column(Numeric(12, 4), nullable=False, default=0, server_default='0.0000', comment='CPC')
    pageviews = Column(Integer, nullable=False, default=0, server_default='0', comment='PageViews')
    ecpm_before_deduct = Column(Numeric(12, 4), nullable=False, default=0, server_default='0.0000', comment='eCPM未减扣')
    ecpm_after_deduct = Column(Numeric(12, 4), nullable=False, default=0, server_default='0.0000', comment='eCPM已减扣')
    revenue_before_deduct = Column(Numeric(12, 4), nullable=False, default=0, server_default='0.0000', comment='收益未减扣')
    revenue_after_deduct = Column(Numeric(12, 4), nullable=False, default=0, server_default='0.0000', comment='收益已减扣')
    data_source = Column(
        String(32), nullable=False, default='legacy', server_default='legacy',
        comment='数据来源：zhisuo/gam/excel/legacy 等',
    )
    upstream_account = Column(
        String(64), nullable=False, default='', server_default='',
        comment='上游账号标识，如 KE11、leadwin',
    )
    report_type = Column(
        String(16), nullable=False, default='legacy', server_default='legacy',
        comment='报表维度：unit/country/cross/daily/legacy',
    )
    is_deducted = Column(Boolean, nullable=False, default=False, server_default='0', comment='是否已被扣减')
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    __table_args__ = (
        # 日汇总互斥选源子查询：按日期范围 + report_type 取 (product_id, date)
        Index("idx_ad_data_date_report_type", "date", "report_type", "product_id"),
        Index("idx_ad_data_product_date_id", "product_id", "date", "id"),
        Index("idx_ad_data_date_id", "date", "id"),
        Index("idx_ad_data_date_country", "date", "country_code", "product_id"),
        Index("idx_ad_data_date_ad_unit", "date", "ad_unit", "product_id"),
        Index("idx_ad_data_date_source", "date", "data_source", "report_type", "product_id"),
        Index("idx_ad_data_date_account", "date", "upstream_account", "product_id"),
        UniqueConstraint(
            "date", "product_id", "country_code", "ad_unit",
            "data_source", "report_type", "upstream_account",
            name="uq_ad_data_identity",
        ),
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

    def finalize_metrics(self) -> None:
        """入库前计算比率并裁剪到 DECIMAL 合法范围，同步 is_deducted。"""
        from app.core.ad_data_metadata import clamp_ad_data_money, clamp_ad_data_rate

        self.calculate_rates()
        self.coverage_rate = clamp_ad_data_rate(self.coverage_rate)
        self.display_rate = clamp_ad_data_rate(self.display_rate)
        self.click_rate = clamp_ad_data_rate(self.click_rate)
        self.viewability_rate = clamp_ad_data_rate(self.viewability_rate)
        self.cpc = clamp_ad_data_money(self.cpc)
        self.ecpm_before_deduct = clamp_ad_data_money(self.ecpm_before_deduct)
        self.ecpm_after_deduct = clamp_ad_data_money(self.ecpm_after_deduct)
        self.revenue_before_deduct = clamp_ad_data_money(self.revenue_before_deduct)
        self.revenue_after_deduct = clamp_ad_data_money(self.revenue_after_deduct)
        before = float(self.revenue_before_deduct or 0)
        after = float(self.revenue_after_deduct or 0)
        self.is_deducted = abs(before - after) > 0.0001


    # 关系
    product = relationship("Product", back_populates="ad_data")
    country = relationship(
        "CountryInfo",
        primaryjoin="foreign(AdData.country_code) == CountryInfo.alpha_2_code",
        viewonly=True,
    )

class TBSearchData(Base):
    """
    TB 搜索数据模型

    TB 搜索渠道专项指标（redirects/searches/revenue 等）。
    表名: tb_search_data
    """
    __tablename__ = "tb_search_data"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='ID')
    date = Column(Date, nullable=False, comment='日期（仅日期）')
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, comment='产品ID')
    country_code = Column(String(100), nullable=True, comment='国家代码（ISO 二字母；未识别时保留原始国名）')
    redirects = Column(Integer, nullable=False, default=0, server_default='0', comment='REDIRECTS')
    searches = Column(Integer, nullable=False, default=0, server_default='0', comment='SEARCHES')
    monetized = Column(Integer, nullable=False, default=0, server_default='0', comment='MONETIZED')
    clicks = Column(Integer, nullable=False, default=0, server_default='0', comment='CLICKS')

    revenue = Column(Numeric(12, 4), nullable=False, default=0, server_default='0.0000', comment='REVENUE（扣减后）')
    rpm = Column(Numeric(10, 4), nullable=False, default=0, server_default='0.0000', comment='RPM（扣减后）')

    revenue_before_deduct = Column(Numeric(12, 4), nullable=False, default=0, server_default='0.0000', comment='REVENUE（扣减前）')
    rpm_before_deduct = Column(Numeric(10, 4), nullable=False, default=0, server_default='0.0000', comment='RPM（扣减前）')

    created_at = Column(DateTime(6), default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime(6), default=get_app_now_naive, onupdate=get_app_now_naive, comment='更新时间')

    # 关系
    product = relationship("Product", back_populates="tb_search_data")
    country = relationship(
        "CountryInfo",
        primaryjoin="foreign(TBSearchData.country_code) == CountryInfo.alpha_2_code",
        viewonly=True,
    )

    __table_args__ = (
        Index("idx_tb_search_data_product", "product_id"),
        Index("idx_tb_search_data_country_code", "country_code"),
        UniqueConstraint("date", "product_id", "country_code", name="uq_tb_search_data_date_product_country"),
    )

class ProductAssignment(Base):
    """
    产品分配历史

    产品分配给客户的历史区间（start_date/end_date）。
    表名: product_assignments
    """
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
        Index("idx_product_assignments_client", "client_id"),
        Index("idx_product_assignments_start_date", "start_date"),
        Index("idx_product_assignments_end_date", "end_date"),
        # 复合索引：优化常见查询组合
        Index("idx_product_assignments_product_date", "product_id", "start_date", "end_date"),  # 产品 + 开始日期 + 结束日期
        Index("idx_product_assignments_client_date", "client_id", "start_date", "end_date"),  # 客户 + 开始日期 + 结束日期
        Index("idx_product_assignments_product_end_date", "product_id", "end_date"),  # 产品 + 结束日期（用于查询当前有效的分配）
        Index("idx_product_assignments_client_product", "client_id", "product_id"),  # 客户 + 产品
    )

