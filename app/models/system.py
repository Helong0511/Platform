"""
系统任务、审计日志、国家信息 ORM 模型。
"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Enum, Text, Index, \
    UniqueConstraint, Date, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from app.core.utils import get_app_now_naive
from app.models.base import Base, pwd_context, UserRole

class ScheduledTask(Base):
    """
    定时任务执行记录

    定时任务运行状态与统计，配合 scheduler 分布式锁。
    表名: scheduled_tasks
    """
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='定时任务ID')
    task_name = Column(String(100), nullable=False, unique=True, comment='任务名称（唯一）')
    last_run_time = Column(DateTime, nullable=True, comment='上次开始执行时间')
    last_finish_time = Column(DateTime, nullable=True, comment='上次完成执行时间')
    is_running = Column(Boolean, default=False, comment='是否正在执行')
    last_run_pid = Column(Integer, nullable=True, comment='上次执行的进程ID')
    last_run_host = Column(String(100), nullable=True, comment='上次执行的服务器主机名')
    run_count = Column(Integer, default=0, comment='执行次数')
    success_count = Column(Integer, default=0, comment='成功次数')
    error_count = Column(Integer, default=0, comment='失败次数')
    last_error = Column(Text, nullable=True, comment='最后一次错误信息')
    status = Column(String(20), nullable=False, default='idle', index=True,
                    comment='任务状态 idle/running/success/error')
    retry_count = Column(Integer, default=0, comment='连续失败重试计数')
    last_success_at = Column(DateTime, nullable=True, comment='上次成功完成时间')
    is_active = Column(Boolean, default=True, comment='是否启用')
    cron_expression = Column(String(100), nullable=True, comment='Cron表达式')
    description = Column(Text, nullable=True, comment='任务描述')
    function_path = Column(String(255), nullable=True,
                           comment='执行函数路径（例如：app.scheduler_module.tasks.simple_task.simple_info_task）')
    task_params = Column(JSON, nullable=True, comment='任务扩展参数（JSON）')
    standard_report_type = Column(String(20), nullable=True, comment='标准数据维度（country/cross/unit/daily），用于多维度汇总选源')
    created_at = Column(DateTime, default=get_app_now_naive, comment='创建时间')
    updated_at = Column(DateTime, default=get_app_now_naive,
                        onupdate=get_app_now_naive, comment='更新时间')

    __table_args__ = (
        Index("idx_scheduled_task_is_running", "is_running"),
        Index("idx_scheduled_task_is_active", "is_active"),
        Index("idx_scheduled_task_status", "status"),
    )

class UserAuditLog(Base):
    """
    用户操作审计日志

    用户/API 操作审计日志，含请求上下文与成败状态。
    表名: user_audit_logs
    """
    __tablename__ = "user_audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='日志ID')
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True,
                     comment='用户ID（可为空，记录未登录访问）')
    username = Column(String(50), nullable=True, index=True, comment='用户名（冗余字段，便于查询）')
    action_type = Column(String(50), nullable=False, index=True,
                         comment='操作类型：LOGIN, LOGOUT, CREATE, UPDATE, DELETE, IMPORT, EXPORT, ACTIVATE, DEACTIVATE, TASK_RUN, API_ACCESS, RUNTIME_ERROR, REVOKE_SESSION, REVOKE_ALL_SESSIONS, CSRF_VIOLATION')
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

class CountryInfo(Base):
    """
    国家信息

    ISO 3166-1 国家代码与多语言名称。
    表名: countries
    """
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


class CountryAlias(Base):
    """
    国家英文别名

    上游 API 非标准国名 → ISO alpha-2，可在国家维护界面配置。
    表名: country_aliases
    """
    __tablename__ = "country_aliases"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="ID")
    alias_name = Column(String(150), nullable=False, comment="别名原文")
    alias_normalized = Column(String(150), unique=True, nullable=False, index=True, comment="规范化键")
    alpha_2_code = Column(String(2), nullable=False, index=True, comment="映射 ISO 二字代码")
    remark = Column(String(255), nullable=True, comment="备注")

    __table_args__ = (
        Index("idx_country_alias_alpha2", "alpha_2_code"),
    )

