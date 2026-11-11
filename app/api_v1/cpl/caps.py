"""Cap（转化上限）管理 API

职责：Offer 维度的日/总转化上限配置 CRUD，以及计数一致性巡检与修复。

权限：
- 全部端点：仅管理员（require_admin）；Cap 含跨租户上限，禁止客户拉取。

主要端点（前缀 /caps）：
- POST   /              创建 Cap 配置
- GET    /              分页列表（可按 offer/渠道/广告主/类型筛选）
- GET    /{cap_id}      详情
- PUT    /{cap_id}      更新
- DELETE /{cap_id}      删除
- POST   /check-consistency  检查或修复计数不一致。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Path, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_create, log_update, log_delete, log_user_action, commit_audit_log
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
        request: Request,
        cap_in: OfferCapCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    创建 Offer Cap（流量上限）配置。

    权限：仅管理员。
    请求体：OfferCapCreate，指定 Cap 类型（日/总）、目标 Offer/渠道及上限值。
    业务：入库后写审计日志，并同步 Cap 计数缓存。
    """
    cap_service: CapService = await get_cap_service(db)
    cap = await cap_service.create_cap(cap_in.model_dump(), current_user)
    await log_create(
        db=db,
        user=current_user,
        resource_type="OFFER_CAP",
        resource_id=cap.id,
        resource_name=f"Cap-{cap.id}",
        request=request,
    )
    await commit_audit_log(db)
    return ResponseBaseSchema.success(data=cap_service.to_cap_response(cap))


@router.get(
    "/",
    response_model=PaginatedResponseBaseSchema[list[OfferCapResponse]],
    summary="获取Cap配置列表",
    dependencies=[Depends(require_admin)],
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
        current_user: User = Depends(require_admin),
):
    """
    分页查询 Cap 配置列表。

    权限：仅管理员（含跨租户费率/上限，禁止客户拉取）。
    筛选：cap_type、offer_id、advertiser_id、channel_id、is_active 等。
    """
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
    """
    按 ID 获取单条 Cap 配置详情。

    权限：仅管理员。
    不存在时由服务层返回 404。
    """
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
        request: Request,
        cap_id: int = Path(..., ge=1),
        cap_in: OfferCapUpdate = ...,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    部分更新 Cap 配置。

    权限：仅管理员。
    有实际字段变更时写审计日志并刷新 Cap 缓存。
    """
    cap_service: CapService = await get_cap_service(db)
    update_data = cap_in.model_dump(exclude_unset=True)
    cap = await cap_service.update_cap(cap_id, update_data, current_user)
    if update_data:
        await log_update(
            db=db,
            user=current_user,
            resource_type="OFFER_CAP",
            resource_id=cap_id,
            resource_name=f"Cap-{cap_id}",
            request=request,
            details={"updated_fields": list(update_data.keys())},
        )
        await commit_audit_log(db)
    return ResponseBaseSchema.success(data=cap_service.to_cap_response(cap))


@router.delete(
    "/{cap_id}",
    response_model=ResponseBaseSchema[dict],
    summary="删除Cap配置",
    dependencies=[Depends(require_admin)],
)
async def delete_cap(
        request: Request,
        cap_id: int = Path(..., ge=1),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    删除 Cap 配置。

    权限：仅管理员。
    删除前保存配置快照，删除后将快照写入审计日志；不清理 Redis 历史计数。
    """
    cap_service: CapService = await get_cap_service(db)
    deleted_snapshot = await cap_service.delete_cap(cap_id, current_user)
    await log_delete(
        db=db,
        user=current_user,
        resource_type="OFFER_CAP",
        resource_id=cap_id,
        resource_name=f"Cap-{cap_id}",
        request=request,
        details={"deleted_cap": deleted_snapshot},
    )
    await commit_audit_log(db)
    return ResponseBaseSchema.success(data={"message": "Cap配置已删除"})


@router.post(
    "/check-consistency",
    response_model=ResponseBaseSchema[list],
    summary="检查Cap计数一致性",
    dependencies=[Depends(require_admin)],
)
async def check_cap_consistency_api(
        request: Request,
        offer_id: Optional[int] = Query(None),
        fix: bool = Query(False),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    检查 Cap 计数与数据库/Redis 状态是否一致。

    fix=true 仅保留兼容参数；为避免覆盖并发预留，不执行自动覆盖修复。
    每次检查均记录审计结果，包括通过、发现问题及执行失败。
    """
    cap_service: CapService = await get_cap_service(db)
    try:
        inconsistencies, message = await cap_service.check_cap_consistency(
            offer_id=offer_id, fix=fix
        )
        await log_user_action(
            db=db,
            action_type="API_ACCESS",
            user=current_user,
            resource_type="OFFER_CAP",
            resource_id=offer_id or 0,
            resource_name="Cap计数一致性检查",
            request=request,
            success=True,
            details={
                "outcome": "inconsistencies_found" if inconsistencies else "consistent",
                "inconsistency_count": len(inconsistencies),
                "offer_id": offer_id,
                "fix_requested": fix,
                "repair_performed": False,
            },
        )
        await commit_audit_log(db)
        return ResponseBaseSchema.success(data=inconsistencies, message=message)
    except HTTPException:
        raise
    except Exception as e:
        from app.core.errors import ErrorCode
        from app.core.exceptions import raise_api_exception

        logger.error("检查Cap计数一致性失败: %s", e, exc_info=True)
        try:
            await log_user_action(
                db=db,
                action_type="API_ACCESS",
                user=current_user,
                resource_type="OFFER_CAP",
                resource_id=offer_id or 0,
                resource_name="Cap计数一致性检查",
                request=request,
                success=False,
                error_message=str(e)[:1000],
                details={
                    "outcome": "failed",
                    "offer_id": offer_id,
                    "fix_requested": fix,
                    "repair_performed": False,
                },
            )
            await commit_audit_log(db)
        except Exception:
            logger.exception("记录 Cap 一致性检查失败审计日志时发生异常")
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"检查Cap计数一致性失败: {str(e)}",
        )
