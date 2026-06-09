"""扣量（Discount）管理 API

职责：Offer 与渠道维度的转化扣量比例配置 CRUD，用于控制向下游转发的转化数量。

权限：
- 列表查询：已登录用户
- 创建/详情/更新/删除：仅管理员（require_admin）

主要端点（前缀 /discounts）：
- POST   /                  创建扣量配置
- GET    /                  分页列表
- GET    /{discount_id}     详情
- PUT    /{discount_id}     更新
- DELETE /{discount_id}     删除。

说明：CPL 子系统接口，涵盖广告主（上游）、渠道（下游）、Offer、Cap、扣量与转化。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_create, log_update, log_delete, commit_audit_log
from app.core.constants import MAX_PAGE_SIZE
from app.core.database import get_db
from app.core.dependencies import get_discount_service
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.security import get_current_user, require_admin
from app.models.models import User
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.schemas.cpl.discount import (
    OfferDiscountCreate,
    OfferDiscountUpdate,
    OfferDiscountResponse,
)
from app.services.cpl.discount_service import DiscountService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/",
    response_model=ResponseBaseSchema[OfferDiscountResponse],
    summary="创建扣量配置",
    dependencies=[Depends(require_admin)],
)
async def create_discount(
        request: Request,
        discount_in: OfferDiscountCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    创建 Offer 扣量（折扣）配置。

    权限：仅管理员。
    请求体：OfferDiscountCreate，指定 Offer/渠道及扣量比例、规则。
    业务：入库后写审计日志，并刷新相关扣量缓存。
    """
    discount_service: DiscountService = await get_discount_service(db)
    discount = await discount_service.create_discount(
        discount_in.model_dump(), current_user
    )
    await log_create(
        db=db,
        user=current_user,
        resource_type="OFFER_DISCOUNT",
        resource_id=discount.id,
        resource_name=f"扣量-{discount.id}",
        request=request,
    )
    await commit_audit_log(db)
    return ResponseBaseSchema.success(
        data=discount_service.to_discount_response(discount)
    )


@router.get(
    "/",
    response_model=PaginatedResponseBaseSchema[list[OfferDiscountResponse]],
    summary="获取扣量配置列表",
)
async def get_discounts(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
        discount_type: Optional[str] = Query(None),
        offer_id: Optional[int] = Query(None),
        publisher_id: Optional[int] = Query(None),
        is_active: Optional[bool] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    分页查询扣量配置列表。

    权限：登录用户，按数据权限过滤。
    筛选：扣量类型、offer_id、channel_id、is_active 等组合条件。
    """
    discount_service: DiscountService = await get_discount_service(db)
    discounts, total = await discount_service.get_discounts(
        page=page,
        page_size=page_size,
        discount_type=discount_type,
        offer_id=offer_id,
        publisher_id=publisher_id,
        is_active=is_active,
    )
    return PaginatedResponseBaseSchema.success(
        data=discount_service.to_discount_response_list(discounts),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{discount_id}",
    response_model=ResponseBaseSchema[OfferDiscountResponse],
    summary="获取扣量配置详情",
    dependencies=[Depends(require_admin)],
)
async def get_discount(
        discount_id: int = Path(..., ge=1),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    按 ID 获取单条扣量配置详情。

    权限：仅管理员。
    不存在时返回 404。
    """
    discount_service: DiscountService = await get_discount_service(db)
    discount = await discount_service.get_discount_by_id(discount_id)
    if not discount:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"扣量配置ID {discount_id} 不存在",
        )
    return ResponseBaseSchema.success(
        data=discount_service.to_discount_response(discount)
    )


@router.put(
    "/{discount_id}",
    response_model=ResponseBaseSchema[OfferDiscountResponse],
    summary="更新扣量配置",
    dependencies=[Depends(require_admin)],
)
async def update_discount(
        request: Request,
        discount_id: int = Path(..., ge=1),
        discount_in: OfferDiscountUpdate = ...,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    部分更新扣量配置。

    权限：仅管理员。
    请求体：OfferDiscountUpdate，仅提交变更字段；有实际变更时写审计日志并刷新缓存。
    """
    discount_service: DiscountService = await get_discount_service(db)
    update_data = discount_in.model_dump(exclude_unset=True)
    discount = await discount_service.update_discount(
        discount_id, update_data, current_user
    )
    if update_data:
        await log_update(
            db=db,
            user=current_user,
            resource_type="OFFER_DISCOUNT",
            resource_id=discount_id,
            resource_name=f"扣量-{discount_id}",
            request=request,
            details={"updated_fields": list(update_data.keys())},
        )
        await commit_audit_log(db)
    return ResponseBaseSchema.success(
        data=discount_service.to_discount_response(discount)
    )


@router.delete(
    "/{discount_id}",
    response_model=ResponseBaseSchema[dict],
    summary="删除扣量配置",
    dependencies=[Depends(require_admin)],
)
async def delete_discount(
        request: Request,
        discount_id: int = Path(..., ge=1),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    删除扣量配置。

    权限：仅管理员。
    删除后写审计日志并失效相关扣量缓存。
    """
    discount_service: DiscountService = await get_discount_service(db)
    await discount_service.delete_discount(discount_id, current_user)
    await log_delete(
        db=db,
        user=current_user,
        resource_type="OFFER_DISCOUNT",
        resource_id=discount_id,
        resource_name=f"扣量-{discount_id}",
        request=request,
    )
    await commit_audit_log(db)
    return ResponseBaseSchema.success(data={"message": "扣量配置已删除"})
