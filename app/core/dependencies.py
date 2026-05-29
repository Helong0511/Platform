"""
依赖注入配置
统一管理FastAPI依赖项，包括服务、仓储等

优化：
- 提供组合依赖项，简化endpoint代码
- 统一服务实例化方式
- 支持类型提示
"""
from functools import lru_cache
from typing import Annotated, Tuple
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import User, UserRole
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode

# 服务类导入（延迟导入以避免循环依赖）
from app.services.user_service import UserService
from app.services.product_service import ProductService
from app.services.cpl.advertiser_service import AdvertiserService
from app.services.cpl.publisher_service import PublisherService
from app.services.cpl.offer_service import OfferService
from app.services.cpl.conversion_service import ConversionService
from app.services.client_service import ClientService
from app.services.short_link_service import ShortLinkService
from app.services.ad_data_service import AdDataService
from app.services.cpl.cap_service import CapService
from app.services.cpl.discount_service import DiscountService
from app.services.cpl.conversion_deduction_service import ConversionDeductionService
from app.services.product_assignment_service import ProductAssignmentService
from app.services.notification_config_service import NotificationConfigService
from app.services.click_service import ClickService
from app.services.audit_log_service import AuditLogService
from app.services.session_service import SessionService
from app.services.scheduled_task_service import ScheduledTaskService
from app.services.dashboard_service import DashboardService

# ====== 组合依赖项 ======

async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    获取当前管理员用户（组合依赖）
    
    如果当前用户不是管理员，抛出异常
    
    Returns:
        User: 管理员用户对象
    
    Raises:
        APIException: 如果不是管理员
    """
    if current_user.role != UserRole.ADMIN:
        raise_api_exception(
            ErrorCode.FORBIDDEN,
            detail="此操作需要管理员权限"
        )
    return current_user


async def get_db_and_user(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Tuple[AsyncSession, User]:
    """
    获取数据库会话和当前用户（组合依赖）
    
    Returns:
        (数据库会话, 当前用户)
    """
    return db, current_user


async def get_db_and_admin(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
) -> Tuple[AsyncSession, User]:
    """
    获取数据库会话和管理员用户（组合依赖）
    
    Returns:
        (数据库会话, 管理员用户)
    """
    return db, current_admin

# ====== 服务依赖 ======
async def get_user_service(db: AsyncSession = Depends(get_db)):
    """获取用户服务实例"""
    return UserService(db)

async def get_product_service(db: AsyncSession = Depends(get_db)):
    """获取产品服务实例"""
    return ProductService(db)

async def get_advertiser_service(db: AsyncSession = Depends(get_db)):
    """获取广告主服务实例"""
    return AdvertiserService(db)

async def get_publisher_service(db: AsyncSession = Depends(get_db)):
    """获取渠道服务实例"""
    return PublisherService(db)

async def get_offer_service(db: AsyncSession = Depends(get_db)):
    """获取Offer服务实例"""
    return OfferService(db)

async def get_conversion_service(db: AsyncSession = Depends(get_db)):
    """获取转化服务实例"""
    return ConversionService(db)

async def get_client_service(db: AsyncSession = Depends(get_db)):
    """获取客户服务实例"""
    return ClientService(db)

async def get_short_link_service(db: AsyncSession = Depends(get_db)):
    """获取短链接服务实例"""
    return ShortLinkService(db)

async def get_ad_data_service(db: AsyncSession = Depends(get_db)):
    """获取广告数据服务实例"""
    return AdDataService(db)

async def get_cap_service(db: AsyncSession = Depends(get_db)):
    """获取Cap服务实例"""
    return CapService(db)

async def get_discount_service(db: AsyncSession = Depends(get_db)):
    """获取Discount服务实例"""
    return DiscountService(db)

async def get_conversion_deduction_service(db: AsyncSession = Depends(get_db)):
    """获取转化扣减服务实例"""
    return ConversionDeductionService(db)

async def get_product_assignment_service(db: AsyncSession = Depends(get_db)):
    """获取产品分配服务实例"""
    return ProductAssignmentService(db)

async def get_notification_config_service(db: AsyncSession = Depends(get_db)):
    """获取通知配置服务实例"""
    return NotificationConfigService(db)

async def get_click_service(db: AsyncSession = Depends(get_db)):
    """获取点击服务实例"""
    return ClickService(db)

async def get_audit_log_service(db: AsyncSession = Depends(get_db)):
    """获取操作日志服务实例"""
    return AuditLogService(db)

async def get_session_service(db: AsyncSession = Depends(get_db)):
    """获取会话服务实例"""
    return SessionService(db)

async def get_scheduled_task_service(db: AsyncSession = Depends(get_db)):
    """获取定时任务服务实例"""
    return ScheduledTaskService(db)

async def get_dashboard_service(db: AsyncSession = Depends(get_db)):
    """获取仪表盘服务实例"""
    return DashboardService(db)

# ====== 类型别名，便于在endpoints中使用 ======

# 组合依赖项类型别名
CurrentAdminDep = Annotated[User, Depends(get_current_admin_user)]
DbAndUserDep = Annotated[Tuple[AsyncSession, User], Depends(get_db_and_user)]
DbAndAdminDep = Annotated[Tuple[AsyncSession, User], Depends(get_db_and_admin)]

# 服务依赖类型别名
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
ClickServiceDep = Annotated[object, Depends(get_click_service)]
AuditLogServiceDep = Annotated[object, Depends(get_audit_log_service)]
SessionServiceDep = Annotated[object, Depends(get_session_service)]
ScheduledTaskServiceDep = Annotated[object, Depends(get_scheduled_task_service)]
DashboardServiceDep = Annotated[object, Depends(get_dashboard_service)]

# 基础依赖类型别名
CurrentUserDep = Annotated[User, Depends(get_current_user)]
DatabaseDep = Annotated[AsyncSession, Depends(get_db)]

