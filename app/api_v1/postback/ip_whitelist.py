"""Postback IP 白名单管理 API

职责：维护允许向平台发送转化 Postback 的 IP 列表（单条/批量 CRUD）。

权限：仅管理员

主要端点：
- GET    /postback/ip-whitelist           分页列表
- POST   /postback/ip-whitelist           创建
- PUT    /postback/ip-whitelist/{id}      更新
- POST   /postback/ip-whitelist/batch     批量创建
- DELETE /postback/ip-whitelist/{id}      删除。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_create, log_update, log_delete, log_user_action, commit_audit_log
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
    """
    分页查询 Postback IP 白名单。

    权限：仅管理员。
    筛选：ip_address 模糊匹配、is_active 启用状态。
    """
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
    """
    新增单条 Postback IP 白名单。

    权限：仅管理员。
    请求体：PostbackIpWhitelistCreate；创建成功后写审计日志。
    """
    result = await postback_ip_whitelist_service.create_ip_whitelist(
        data=data, db=db, current_user=current_user
    )
    if result.data:
        await log_create(
            db=db,
            user=current_user,
            resource_type="POSTBACK_IP_WHITELIST",
            resource_id=result.data.id,
            resource_name=result.data.ip_address,
            request=request,
        )
        await commit_audit_log(db)
    return result


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
    """
    更新 Postback IP 白名单记录。

    权限：仅管理员。
    支持部分字段更新；有变更时写审计日志。
    """
    result = await postback_ip_whitelist_service.update_ip_whitelist(
        whitelist_id=whitelist_id,
        data=data,
        db=db,
        current_user=current_user,
    )
    update_fields = data.model_dump(exclude_unset=True)
    if update_fields:
        await log_update(
            db=db,
            user=current_user,
            resource_type="POSTBACK_IP_WHITELIST",
            resource_id=whitelist_id,
            resource_name=result.data.ip_address if result.data else f"白名单-{whitelist_id}",
            request=request,
            details={"updated_fields": list(update_fields.keys())},
        )
        await commit_audit_log(db)
    return result


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
    """
    批量导入 Postback IP 白名单。

    权限：仅管理员。
    返回成功/失败计数；至少有一条成功时写审计日志。
    """
    result = await postback_ip_whitelist_service.batch_create_ip_whitelist(
        data=data, db=db, current_user=current_user
    )
    if result.data and result.data.success_count > 0:
        await log_user_action(
            db=db,
            action_type="CREATE",
            user=current_user,
            resource_type="POSTBACK_IP_WHITELIST",
            resource_id=0,
            resource_name="批量创建Postback IP白名单",
            request=request,
            details={
                "success_count": result.data.success_count,
                "failed_count": result.data.failed_count,
                "total_count": result.data.total_count,
            },
        )
        await commit_audit_log(db)
    return result


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
    """
    删除 Postback IP 白名单记录。

    权限：仅管理员。
    删除后写审计日志。
    """
    result = await postback_ip_whitelist_service.delete_ip_whitelist(
        whitelist_id=whitelist_id, db=db, current_user=current_user
    )
    ip_address = result.data.get("ip_address") if result.data else None
    await log_delete(
        db=db,
        user=current_user,
        resource_type="POSTBACK_IP_WHITELIST",
        resource_id=whitelist_id,
        resource_name=ip_address or f"白名单-{whitelist_id}",
        request=request,
    )
    await commit_audit_log(db)
    return result
