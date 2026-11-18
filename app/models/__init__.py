"""
数据模型统一导出模块。

聚合各域 ORM 子模块，确保 Alembic 与 SQLAlchemy 能发现全部表。
"""
from app.models.base import Base, pwd_context, UserRole
from app.models.user import User
from app.models.client_product import (
    Client,
    Product,
    AdData,
    TBSearchData,
    ProductAssignment,
)
from app.models.ad_data_health import (
    AdDataDayBaseline,
    AdDataHealthAlert,
    AdDataHealthSettings,
)
from app.models.system import ScheduledTask, UserAuditLog, CountryInfo, CountryAlias
from app.models.postback import (
    PostbackConversion,
    PostbackForwardLog,
    PostbackForwardQueue,
    ClientNotificationConfig,
    ProductNotificationConfig,
    AdminNotificationConfig,
    CloakConfig,
    PostbackNotification,
    ShortLink,
    PendingPostbackConversion,
)
from app.models.cpl import (
    Advertiser,
    Publisher,
    Offer,
    OfferPublisherAssignment,
    Click,
    OfferCap,
    OfferDiscount,
    AdvertiserTest,
    AffiliateTest,
)
from app.models.cap_reservation import CapReservation
from app.models.deduction import ConversionDeductionConfig, ConversionDeductionLog
from app.models.security import (
    SensitivePathProbeLog,
    SensitiveBlockedIP,
    PostbackIpWhitelist,
)
from app.models.third_party import ThirdPartyReportLog
from app.models.session import UserSession, TokenBlacklist

__all__ = [
    "Base",
    "pwd_context",
    "UserRole",
    "User",
    "Client",
    "Product",
    "AdData",
    "TBSearchData",
    "ProductAssignment",
    "AdDataDayBaseline",
    "AdDataHealthAlert",
    "AdDataHealthSettings",
    "ScheduledTask",
    "UserAuditLog",
    "CountryInfo",
    "CountryAlias",
    "PostbackConversion",
    "PostbackForwardLog",
    "PostbackForwardQueue",
    "ClientNotificationConfig",
    "ProductNotificationConfig",
    "AdminNotificationConfig",
    "CloakConfig",
    "PostbackNotification",
    "ShortLink",
    "PendingPostbackConversion",
    "Advertiser",
    "Publisher",
    "Offer",
    "OfferPublisherAssignment",
    "Click",
    "OfferCap",
    "OfferDiscount",
    "AdvertiserTest",
    "AffiliateTest",
    "CapReservation",
    "ConversionDeductionConfig",
    "ConversionDeductionLog",
    "SensitivePathProbeLog",
    "SensitiveBlockedIP",
    "PostbackIpWhitelist",
    "ThirdPartyReportLog",
    "UserSession",
    "TokenBlacklist",
]
