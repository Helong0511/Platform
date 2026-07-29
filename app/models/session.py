"""
用户会话与 Token 黑名单模型。

功能说明：
- ``UserSession``：跟踪用户活跃登录会话（jti、IP、UA、过期时间等）
- ``TokenBlacklist``：记录已撤销 JWT，配合会话服务实现强制下线

在系统中的位置：
- 被 ``session_service``、认证中间件、``cleanup_expired_sessions`` 定时任务使用

注意事项：
1. 时间字段使用 ``get_app_now_naive()``（北京时间 naive datetime）
2. 撤销会话须同时写黑名单并将 ``is_active=False``，双写保证 token 立即失效
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.models.models import Base
from app.core.utils import get_app_now_naive


class UserSession(Base):
    """
    用户会话模型
    记录用户的活跃登录会话
    """
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='会话ID')
    user_id = Column(Integer, nullable=False, comment='用户ID')
    token_jti = Column(String(64), nullable=False, unique=True, comment='JWT令牌ID（jti）')
    token_type = Column(String(16), nullable=False, default='access', index=True, comment='令牌类型 access/refresh')
    ip_address = Column(String(50), nullable=True, index=True, comment='登录IP地址')
    user_agent = Column(String(500), nullable=True, comment='用户代理（浏览器信息）')
    device_info = Column(String(200), nullable=True, comment='设备信息（移动端/桌面端）')
    location = Column(String(200), nullable=True, comment='登录位置（可选，通过IP解析）')
    is_active = Column(Boolean, default=True, index=True, comment='是否活跃')
    last_activity = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='最后活动时间')
    created_at = Column(DateTime, default=get_app_now_naive, nullable=False, comment='创建时间（登录时间）')
    expires_at = Column(DateTime, nullable=False, index=True, comment='过期时间')

    __table_args__ = (
        Index("idx_session_user_active", "user_id", "is_active"),
        Index("idx_session_expires", "expires_at"),
        Index("ix_user_sessions_token_type", "token_type"),
    )


class TokenBlacklist(Base):
    """
    Token黑名单模型
    记录已撤销的JWT令牌，用于主动撤销token
    """
    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment='黑名单ID')
    token_jti = Column(String(64), nullable=False, unique=True, comment='JWT令牌ID（jti）')
    user_id = Column(Integer, nullable=False, comment='用户ID')
    revoked_at = Column(DateTime, default=get_app_now_naive, nullable=False, index=True, comment='撤销时间')
    expires_at = Column(DateTime, nullable=False, comment='Token过期时间')
    reason = Column(String(200), nullable=True, comment='撤销原因（用户退出、强制退出等）')

    __table_args__ = (
        Index("idx_blacklist_user", "user_id"),
        Index("idx_blacklist_expires", "expires_at"),
    )

