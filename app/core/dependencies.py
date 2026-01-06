"""
依赖注入配置
统一管理FastAPI依赖项，包括服务、仓储等
"""
from functools import lru_cache
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import User

# 服务依赖
async def get_user_service(db: AsyncSession = Depends(get_db)):
    """获取用户服务实例"""
    from app.services.user_service import UserService
    return UserService(db)

async def get_product_service(db: AsyncSession = Depends(get_db)):
    """获取产品服务实例"""
    from app.services.product_service import ProductService
    return ProductService(db)

async def get_advertiser_service(db: AsyncSession = Depends(get_db)):
    """获取广告主服务实例"""
    from app.services.cpl.advertiser_service import AdvertiserService
    return AdvertiserService(db)

async def get_publisher_service(db: AsyncSession = Depends(get_db)):
    """获取渠道服务实例"""
    from app.services.cpl.publisher_service import PublisherService
    return PublisherService(db)

async def get_offer_service(db: AsyncSession = Depends(get_db)):
    """获取Offer服务实例"""
    from app.services.cpl.offer_service import OfferService
    return OfferService(db)

async def get_conversion_service(db: AsyncSession = Depends(get_db)):
    """获取转化服务实例"""
    from app.services.cpl.conversion_service import ConversionService
    return ConversionService(db)

async def get_client_service(db: AsyncSession = Depends(get_db)):
    """获取客户服务实例"""
    from app.services.client_service import ClientService
    return ClientService(db)

async def get_short_link_service(db: AsyncSession = Depends(get_db)):
    """获取短链接服务实例"""
    from app.services.short_link_service import ShortLinkService
    return ShortLinkService(db)

async def get_ad_data_service(db: AsyncSession = Depends(get_db)):
    """获取广告数据服务实例"""
    from app.services.ad_data_service import AdDataService
    return AdDataService(db)

async def get_cap_service(db: AsyncSession = Depends(get_db)):
    """获取Cap服务实例"""
    from app.services.cpl.cap_service import CapService
    return CapService(db)

async def get_discount_service(db: AsyncSession = Depends(get_db)):
    """获取Discount服务实例"""
    from app.services.cpl.discount_service import DiscountService
    return DiscountService(db)

async def get_conversion_deduction_service(db: AsyncSession = Depends(get_db)):
    """获取转化扣减服务实例"""
    from app.services.cpl.conversion_deduction_service import ConversionDeductionService
    return ConversionDeductionService(db)

async def get_product_assignment_service(db: AsyncSession = Depends(get_db)):
    """获取产品分配服务实例"""
    from app.services.product_assignment_service import ProductAssignmentService
    return ProductAssignmentService(db)

async def get_notification_config_service(db: AsyncSession = Depends(get_db)):
    """获取通知配置服务实例"""
    from app.services.notification_config_service import NotificationConfigService
    return NotificationConfigService(db)

async def get_conversion_log_service(db: AsyncSession = Depends(get_db)):
    """获取转化日志服务实例"""
    from app.services.cpl.conversion_log_service import ConversionLogService
    return ConversionLogService(db)

async def get_click_service(db: AsyncSession = Depends(get_db)):
    """获取点击服务实例"""
    from app.services.click_service import ClickService
    return ClickService(db)

async def get_audit_log_service(db: AsyncSession = Depends(get_db)):
    """获取操作日志服务实例"""
    from app.services.audit_log_service import AuditLogService
    return AuditLogService(db)

async def get_session_service(db: AsyncSession = Depends(get_db)):
    """获取会话服务实例"""
    from app.services.session_service import SessionService
    return SessionService(db)

# 类型别名，便于在endpoints中使用
UserServiceDep = Annotated[object, Depends(get_user_service)]
ProductServiceDep = Annotated[object, Depends(get_product_service)]
AdvertiserServiceDep = Annotated[object, Depends(get_advertiser_service)]
PublisherServiceDep = Annotated[object, Depends(get_publisher_service)]
OfferServiceDep = Annotated[object, Depends(get_offer_service)]
ConversionServiceDep = Annotated[object, Depends(get_conversion_service)]
ClientServiceDep = Annotated[object, Depends(get_client_service)]
ShortLinkServiceDep = Annotated[object, Depends(get_short_link_service)]
    AdDataServiceDep = Annotated[object, Depends(get_ad_data_service)]
CapServiceDep = Annotated[object, Depends(get_cap_service)]
DiscountServiceDep = Annotated[object, Depends(get_discount_service)]
ConversionDeductionServiceDep = Annotated[object, Depends(get_conversion_deduction_service)]
ProductAssignmentServiceDep = Annotated[object, Depends(get_product_assignment_service)]
NotificationConfigServiceDep = Annotated[object, Depends(get_notification_config_service)]
ConversionLogServiceDep = Annotated[object, Depends(get_conversion_log_service)]
ClickServiceDep = Annotated[object, Depends(get_click_service)]
AuditLogServiceDep = Annotated[object, Depends(get_audit_log_service)]
SessionServiceDep = Annotated[object, Depends(get_session_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
    DatabaseDep = Annotated[AsyncSession, Depends(get_db)]

