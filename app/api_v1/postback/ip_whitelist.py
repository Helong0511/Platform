"""Postback IP 白名单 API（薄路由层）。"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.security import require_admin
from app.models.models import User
from app.schemas.base import PaginatedResponseBaseSchema, ResponseBaseSchema
from app.schemas.postback_ip_whitelist import (
    PostbackIpWhitelistBatchCreate,
    PostbackIpWhitelistBatchCreateResponse,
    PostbackIpWhitelistCreate,
    PostbackIpWhitelistResponse,
    PostbackIpWhitelistUpdate,
)
from app.services.cpl.postback_ip_whitelist_service import (
    postback_ip_whitelist_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/postback/ip-whitelist",
    response_model=PaginatedResponseBaseSchema[list[PostbackIpWhitelistResponse]],
    summary="查询 Postback IP 白名单列表（管理员）",
)
async def get_ip_whitelist(
        request: Request,
        ip_address: Optional[str] = Query(None, description="IP地址（模糊搜索）"),
        is_active: Optional[bool] = Query(None, description="是否启用"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页数量"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
):
    return await postback_ip_whitelist_service.list_ip_whitelist(
        ip_address=ip_address,
        is_active=is_active,
        page=page,
        page_size=page_size,
        db=db,
        current_user=current_user,
    )


@router.post(
    "/postback/ip-whitelist",
    response_model=ResponseBaseSchema[PostbackIpWhitelistResponse],
    summary="创建 Postback IP 白名单（管理员）",
)
async def create_ip_whitelist(
        request: Request,
        data: PostbackIpWhitelistCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
):
    return await postback_ip_whitelist_service.create_ip_whitelist(
        data=data, db=db, current_user=current_user
    )


@router.put(
    "/postback/ip-whitelist/{whitelist_id}",
    response_model=ResponseBaseSchema[PostbackIpWhitelistResponse],
    summary="更新 Postback IP 白名单（管理员）",
)
async def update_ip_whitelist(
        request: Request,
        whitelist_id: int = Path(..., ge=1, description="白名单ID"),
        data: PostbackIpWhitelistUpdate = ...,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
):
    return await postback_ip_whitelist_service.update_ip_whitelist(
        whitelist_id=whitelist_id,
        data=data,
        db=db,
        current_user=current_user,
    )


@router.post(
    "/postback/ip-whitelist/batch",
    response_model=ResponseBaseSchema[PostbackIpWhitelistBatchCreateResponse],
    summary="批量创建 Postback IP 白名单（管理员）",
)
async def batch_create_ip_whitelist(
        request: Request,
        data: PostbackIpWhitelistBatchCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
):
    return await postback_ip_whitelist_service.batch_create_ip_whitelist(
        data=data, db=db, current_user=current_user
    )


@router.delete(
    "/postback/ip-whitelist/{whitelist_id}",
    response_model=ResponseBaseSchema[dict],
    summary="删除 Postback IP 白名单（管理员）",
)
async def delete_ip_whitelist(
        request: Request,
        whitelist_id: int = Path(..., ge=1, description="白名单ID"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
):
    return await postback_ip_whitelist_service.delete_ip_whitelist(
        whitelist_id=whitelist_id, db=db, current_user=current_user
    )
