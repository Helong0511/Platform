"""
数据模型模块
统一导出所有模型，确保SQLAlchemy能够发现所有表
"""
# 导入基础模型（必须首先导入）
from app.models.models import (
    Base, User, Client, Product, AdData, ProductAssignment, ScheduledTask, 
    UserAuditLog, PostbackConversion, PostbackForwardLog,
    ClientNotificationConfig, ProductNotificationConfig, PostbackNotification,
    ShortLink,
    # CPL 系统模型
    Advertiser, Publisher, Offer, OfferPublisherAssignment, Click, ClickStats,
    OfferCap, OfferDiscount, AdvertiserTest, AffiliateTest
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
    # CPL 系统模型
    "Advertiser",
    "Publisher",
    "Offer",
    "OfferPublisherAssignment",
    "Click",
    "ClickStats",
    "OfferCap",
    "OfferDiscount",
    "AdvertiserTest",
    "AffiliateTest",
    "UserSession",
    "TokenBlacklist",
]

