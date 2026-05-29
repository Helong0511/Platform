"""
Cap 管理 API（薄路由层）
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Path, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.dependencies import get_cap_service
from app.core.security import get_current_user, require_admin
from app.models.models import User
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.cpl.cap import OfferCapCreate, OfferCapUpdate, OfferCapResponse
from app.services.cpl.cap_service import CapService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/",
    response_model=ResponseBaseSchema[OfferCapResponse],
    summary="创建Cap配置",
    dependencies=[Depends(require_admin)],
)
async def create_cap(
        cap_in: OfferCapCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    cap_service: CapService = await get_cap_service(db)
    cap = await cap_service.create_cap(cap_in.model_dump(), current_user)
    return ResponseBaseSchema.success(data=cap_service.to_cap_response(cap))


@router.get(
    "/",
    response_model=PaginatedResponseBaseSchema[list[OfferCapResponse]],
    summary="获取Cap配置列表",
)
async def get_caps(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
        cap_type: Optional[str] = Query(None),
        offer_id: Optional[int] = Query(None),
        advertiser_id: Optional[int] = Query(None),
        publisher_id: Optional[int] = Query(None),
        is_active: Optional[bool] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    cap_service: CapService = await get_cap_service(db)
    caps, total = await cap_service.get_caps(
        page=page,
        page_size=page_size,
        cap_type=cap_type,
        offer_id=offer_id,
        advertiser_id=advertiser_id,
        publisher_id=publisher_id,
        is_active=is_active,
    )
    return PaginatedResponseBaseSchema.success(
        data=cap_service.to_cap_response_list(caps),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{cap_id}",
    response_model=ResponseBaseSchema[OfferCapResponse],
    summary="获取Cap配置详情",
    dependencies=[Depends(require_admin)],
)
async def get_cap(
        cap_id: int = Path(..., ge=1),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    cap_service: CapService = await get_cap_service(db)
    cap = await cap_service.get_cap_by_id(cap_id)
    if not cap:
        from app.core.errors import ErrorCode
        from app.core.exceptions import raise_api_exception

        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Cap配置ID {cap_id} 不存在",
        )
    return ResponseBaseSchema.success(data=cap_service.to_cap_response(cap))


@router.put(
    "/{cap_id}",
    response_model=ResponseBaseSchema[OfferCapResponse],
    summary="更新Cap配置",
    dependencies=[Depends(require_admin)],
)
async def update_cap(
        cap_id: int = Path(..., ge=1),
        cap_in: OfferCapUpdate = ...,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    cap_service: CapService = await get_cap_service(db)
    cap = await cap_service.update_cap(
        cap_id, cap_in.model_dump(exclude_unset=True), current_user
    )
    return ResponseBaseSchema.success(data=cap_service.to_cap_response(cap))


@router.delete(
    "/{cap_id}",
    response_model=ResponseBaseSchema[dict],
    summary="删除Cap配置",
    dependencies=[Depends(require_admin)],
)
async def delete_cap(
        cap_id: int = Path(..., ge=1),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    cap_service: CapService = await get_cap_service(db)
    await cap_service.delete_cap(cap_id, current_user)
    return ResponseBaseSchema.success(data={"message": "Cap配置已删除"})


@router.post(
    "/check-consistency",
    response_model=ResponseBaseSchema[list],
    summary="检查Cap计数一致性",
    dependencies=[Depends(require_admin)],
)
async def check_cap_consistency_api(
        offer_id: Optional[int] = Query(None),
        fix: bool = Query(False),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    cap_service: CapService = await get_cap_service(db)
    try:
        inconsistencies, message = await cap_service.check_cap_consistency(
            offer_id=offer_id, fix=fix
        )
        logger.info("Cap计数一致性检查完成: %s", message)
        return ResponseBaseSchema.success(data=inconsistencies, message=message)
    except HTTPException:
        raise
    except Exception as e:
        from app.core.errors import ErrorCode
        from app.core.exceptions import raise_api_exception

        logger.error("检查Cap计数一致性失败: %s", e, exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"检查Cap计数一致性失败: {str(e)}",
        )
