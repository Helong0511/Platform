"""
数据模型统一导出模块。

功能说明：
- 聚合导出 ``models.py`` 与 ``session.py`` 中全部 ORM 模型
- 确保 SQLAlchemy ``Base.metadata`` 能发现所有表（含 CPL、Postback、会话）

在系统中的位置：
- 被 ``app.main`` 初始化数据库、Alembic/迁移脚本、各服务层 import 使用

注意事项：
1. 新增模型须在 ``models.py`` 或独立文件定义后在本文件加入 ``__all__``
2. ``Base`` 必须来自 ``models.py``，勿重复声明 declarative_base
"""
# 导入基础模型（必须首先导入）
from app.models.models import (
    Base, User, Client, Product, AdData, ProductAssignment, ScheduledTask, 
    UserAuditLog, PostbackConversion, PostbackForwardLog,
    ClientNotificationConfig, ProductNotificationConfig, PostbackNotification,
    ShortLink, CloakConfig,
    # CPL 系统模型
    Advertiser, Publisher, Offer, OfferPublisherAssignment, Click,
    OfferCap, OfferDiscount, AffiliateTest,
    # Postback 相关模型
    PendingPostbackConversion, PostbackIpWhitelist
)

# 导入会话模型
from app.models.session import UserSession, TokenBlacklist

# 导出所有模型，确保SQLAlchemy能够发现所有表
__all__ = [
    "Base",
    "User",
    "Client", 
    "Product",
    "AdData",
    "ProductAssignment",
    "ScheduledTask",
    "UserAuditLog",
    "PostbackConversion",
    "PostbackForwardLog",
    "ClientNotificationConfig",
    "ProductNotificationConfig",
    "PostbackNotification",
    "ShortLink",
    "CloakConfig",
    # CPL 系统模型
    "Advertiser",
    "Publisher",
    "Offer",
    "OfferPublisherAssignment",
    "Click",
    "OfferCap",
    "OfferDiscount",
    "AffiliateTest",
    # Postback 相关模型
    "PendingPostbackConversion",
    "PostbackIpWhitelist",
    "UserSession",
    "TokenBlacklist",
]
