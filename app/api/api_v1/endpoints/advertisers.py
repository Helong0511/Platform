"""
广告主管理 API
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, String

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.constants import MAX_PAGE_SIZE
from app.models.models import User, UserRole, Advertiser
from app.schemas.cpl.advertiser import AdvertiserCreate, AdvertiserUpdate, AdvertiserResponse
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/",
             response_model=ResponseBaseSchema[AdvertiserResponse],
             summary="创建广告主",
             dependencies=[Depends(require_admin)])
async def create_advertiser(
    advertiser_in: AdvertiserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建广告主（已重构使用服务层）"""
    # 使用服务层（业务逻辑在AdvertiserService中）
    from app.core.dependencies import get_advertiser_service
    from app.services.cpl.advertiser_service import AdvertiserService
    
    advertiser_service: AdvertiserService = await get_advertiser_service(db)
    
    # 准备广告主数据
    advertiser_data = advertiser_in.model_dump()
    
    # 调用服务层创建广告主（服务层会处理所有验证和审计日志）
    advertiser = await advertiser_service.create_advertiser(advertiser_data, current_user)
    
    return ResponseBaseSchema.success(data=AdvertiserResponse.model_validate(advertiser))


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[AdvertiserResponse]],
            summary="获取广告主列表")
async def get_advertisers(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    search: Optional[str] = Query(None, description="搜索关键词（名称、ID）"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取广告主列表（已重构使用服务层）"""
    # 使用服务层（业务逻辑在AdvertiserService中）
    from app.core.dependencies import get_advertiser_service
    from app.services.cpl.advertiser_service import AdvertiserService
    
    advertiser_service: AdvertiserService = await get_advertiser_service(db)
    advertisers, total = await advertiser_service.get_advertisers(
        current_user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active
    )
    
    return PaginatedResponseBaseSchema.success(
        data=[AdvertiserResponse.model_validate(adv) for adv in advertisers],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{advertiser_id}",
            response_model=ResponseBaseSchema[AdvertiserResponse],
            summary="获取广告主详情",
            dependencies=[Depends(require_admin)])
async def get_advertiser(
    advertiser_id: int = Path(..., ge=1, description="广告主ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取广告主详情（已重构使用服务层）"""
    # 使用服务层（业务逻辑在AdvertiserService中）
    from app.core.dependencies import get_advertiser_service
    from app.services.cpl.advertiser_service import AdvertiserService
    
    advertiser_service: AdvertiserService = await get_advertiser_service(db)
    advertiser = await advertiser_service.get_advertiser_by_id(advertiser_id, current_user)
    
    return ResponseBaseSchema.success(data=AdvertiserResponse.model_validate(advertiser))


@router.put("/{advertiser_id}",
            response_model=ResponseBaseSchema[AdvertiserResponse],
            summary="更新广告主",
            dependencies=[Depends(require_admin)])
async def update_advertiser(
    advertiser_id: int = Path(..., ge=1, description="广告主ID"),
    advertiser_in: AdvertiserUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新广告主（已重构使用服务层）"""
    # 使用服务层（业务逻辑在AdvertiserService中）
    from app.core.dependencies import get_advertiser_service
    from app.services.cpl.advertiser_service import AdvertiserService
    
    advertiser_service: AdvertiserService = await get_advertiser_service(db)
    
    # 获取更新数据（排除未设置的字段）
    update_data = advertiser_in.model_dump(exclude_unset=True)
    
    # 调用服务层更新广告主（服务层会处理所有验证、缓存失效和审计日志）
    advertiser = await advertiser_service.update_advertiser(advertiser_id, update_data, current_user)
    
    return ResponseBaseSchema.success(data=AdvertiserResponse.model_validate(advertiser))


@router.delete("/{advertiser_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除广告主",
               dependencies=[Depends(require_admin)])
async def delete_advertiser(
    advertiser_id: int = Path(..., ge=1, description="广告主ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除广告主（已重构使用服务层）"""
    # 使用服务层（业务逻辑在AdvertiserService中）
    from app.core.dependencies import get_advertiser_service
    from app.services.cpl.advertiser_service import AdvertiserService
    
    advertiser_service: AdvertiserService = await get_advertiser_service(db)
    
    # 调用服务层删除广告主（服务层会检查关联数据、记录审计日志）
    await advertiser_service.delete_advertiser(advertiser_id, current_user)
    
    return ResponseBaseSchema.success(data={"message": "广告主已删除"})

