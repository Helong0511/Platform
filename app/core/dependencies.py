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

# 类型别名，便于在endpoints中使用
UserServiceDep = Annotated[object, Depends(get_user_service)]
ProductServiceDep = Annotated[object, Depends(get_product_service)]
AdvertiserServiceDep = Annotated[object, Depends(get_advertiser_service)]
PublisherServiceDep = Annotated[object, Depends(get_publisher_service)]
OfferServiceDep = Annotated[object, Depends(get_offer_service)]
ConversionServiceDep = Annotated[object, Depends(get_conversion_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
DatabaseDep = Annotated[AsyncSession, Depends(get_db)]

