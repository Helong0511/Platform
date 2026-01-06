"""
Cap 管理 API
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.constants import MAX_PAGE_SIZE
from app.core.utils import get_app_now_naive
from app.models.models import User, OfferCap, Offer, Advertiser, Publisher
from app.schemas.cpl.cap import OfferCapCreate, OfferCapUpdate, OfferCapResponse
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.core.cap.consistency_checker import check_cap_consistency

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/",
             response_model=ResponseBaseSchema[OfferCapResponse],
             summary="创建Cap配置",
             dependencies=[Depends(require_admin)])
async def create_cap(
    cap_in: OfferCapCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建Cap配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在CapService中）
    from app.core.dependencies import get_cap_service
    from app.services.cpl.cap_service import CapService
    
    cap_service: CapService = await get_cap_service(db)
    
    # 准备Cap数据
    cap_data = cap_in.model_dump()
    
    # 调用服务层创建Cap配置（服务层会处理所有验证）
    cap = await cap_service.create_cap(cap_data, current_user)
    
    # 构建响应数据
    cap_response = OfferCapResponse.model_validate(cap)
    cap_response.offer_name = cap.offer.offer_name if cap.offer else None
    cap_response.advertiser_name = cap.advertiser.advertiser_name if cap.advertiser else None
    cap_response.publisher_name = cap.publisher.publisher_name if cap.publisher else None
    
    return ResponseBaseSchema.success(data=cap_response)


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[OfferCapResponse]],
            summary="获取Cap配置列表")
async def get_caps(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    cap_type: Optional[str] = Query(None, description="Cap类型过滤"),
    offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
    advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
    publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取Cap配置列表（所有登录用户可访问，已重构使用服务层）"""
    # 使用服务层（业务逻辑在CapService中）
    from app.core.dependencies import get_cap_service
    from app.services.cpl.cap_service import CapService
    
    cap_service: CapService = await get_cap_service(db)
    
    # 调用服务层获取Cap配置列表（服务层会处理查询、过滤、分页）
    caps, total = await cap_service.get_caps(
        page=page,
        page_size=page_size,
        cap_type=cap_type,
        offer_id=offer_id,
        advertiser_id=advertiser_id,
        publisher_id=publisher_id,
        is_active=is_active
    )
    
    # 构建响应数据
    cap_list = []
    for cap in caps:
        cap_data = OfferCapResponse.model_validate(cap)
        cap_data.offer_name = cap.offer.offer_name if cap.offer else None
        cap_data.advertiser_name = cap.advertiser.advertiser_name if cap.advertiser else None
        cap_data.publisher_name = cap.publisher.publisher_name if cap.publisher else None
        cap_list.append(cap_data)
    
    return PaginatedResponseBaseSchema.success(
        data=cap_list,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{cap_id}",
            response_model=ResponseBaseSchema[OfferCapResponse],
            summary="获取Cap配置详情",
            dependencies=[Depends(require_admin)])
async def get_cap(
    cap_id: int = Path(..., ge=1, description="Cap配置ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取Cap配置详情（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在CapService中）
    from app.core.dependencies import get_cap_service
    from app.services.cpl.cap_service import CapService
    
    cap_service: CapService = await get_cap_service(db)
    
    # 调用服务层获取Cap配置详情
    cap = await cap_service.get_cap_by_id(cap_id)
    
    if not cap:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Cap配置ID {cap_id} 不存在"
        )
    
    # 构建响应数据
    cap_data = OfferCapResponse.model_validate(cap)
    cap_data.offer_name = cap.offer.offer_name if cap.offer else None
    cap_data.advertiser_name = cap.advertiser.advertiser_name if cap.advertiser else None
    cap_data.publisher_name = cap.publisher.publisher_name if cap.publisher else None
    
    return ResponseBaseSchema.success(data=cap_data)


@router.put("/{cap_id}",
            response_model=ResponseBaseSchema[OfferCapResponse],
            summary="更新Cap配置",
            dependencies=[Depends(require_admin)])
async def update_cap(
    cap_id: int = Path(..., ge=1, description="Cap配置ID"),
    cap_in: OfferCapUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新Cap配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在CapService中）
    from app.core.dependencies import get_cap_service
    from app.services.cpl.cap_service import CapService
    
    cap_service: CapService = await get_cap_service(db)
    
    # 准备更新数据
    update_data = cap_in.model_dump(exclude_unset=True)
    
    # 调用服务层更新Cap配置（服务层会处理所有验证和逻辑）
    cap = await cap_service.update_cap(cap_id, update_data, current_user)
    
    # 构建响应数据
    cap_data = OfferCapResponse.model_validate(cap)
    cap_data.offer_name = cap.offer.offer_name if cap.offer else None
    cap_data.advertiser_name = cap.advertiser.advertiser_name if cap.advertiser else None
    cap_data.publisher_name = cap.publisher.publisher_name if cap.publisher else None
    
    return ResponseBaseSchema.success(data=cap_data)


@router.delete("/{cap_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除Cap配置",
               dependencies=[Depends(require_admin)])
async def delete_cap(
    cap_id: int = Path(..., ge=1, description="Cap配置ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除Cap配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在CapService中）
    from app.core.dependencies import get_cap_service
    from app.services.cpl.cap_service import CapService
    
    cap_service: CapService = await get_cap_service(db)
    
    # 调用服务层删除Cap配置（服务层会处理验证和删除）
    await cap_service.delete_cap(cap_id, current_user)
    
    return ResponseBaseSchema.success(data={"message": "Cap配置已删除"})


@router.post("/check-consistency",
             response_model=ResponseBaseSchema[list],
             summary="检查Cap计数一致性",
             dependencies=[Depends(require_admin)])
async def check_cap_consistency_api(
    offer_id: Optional[int] = Query(None, description="可选的Offer ID，如果提供则只检查该Offer的Cap"),
    fix: bool = Query(False, description="是否自动修复不一致的数据"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    检查Cap计数一致性（DB vs Redis）
    仅管理员
    """
    try:
        inconsistencies = await check_cap_consistency(
            db=db,
            offer_id=offer_id,
            fix_inconsistencies=fix
        )
        
        if inconsistencies:
            message = f"发现 {len(inconsistencies)} 个不一致的记录"
            if fix:
                message += "，已自动修复"
        else:
            message = "所有Cap计数一致"
        
        logger.info(f"Cap计数一致性检查完成: {message}")
        return ResponseBaseSchema.success(
            data=inconsistencies,
            message=message
        )
    except Exception as e:
        logger.error(f"检查Cap计数一致性失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"检查Cap计数一致性失败: {str(e)}"
        )

