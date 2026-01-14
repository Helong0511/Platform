"""
扣量管理 API
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.constants import MAX_PAGE_SIZE
from app.core.dependencies import get_discount_service
from app.services.cpl.discount_service import DiscountService
from app.models.models import User, OfferDiscount, Offer, Publisher
from app.schemas.cpl.discount import OfferDiscountCreate, OfferDiscountUpdate, OfferDiscountResponse
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/",
             response_model=ResponseBaseSchema[OfferDiscountResponse],
             summary="创建扣量配置",
             dependencies=[Depends(require_admin)])
async def create_discount(
    discount_in: OfferDiscountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建扣量配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在DiscountService中）
    discount_service: DiscountService = await get_discount_service(db)
    
    # 准备扣量配置数据
    discount_data = discount_in.model_dump()
    
    # 调用服务层创建扣量配置（服务层会处理所有验证）
    discount = await discount_service.create_discount(discount_data, current_user)
    
    # 构建响应数据
    discount_response = OfferDiscountResponse.model_validate(discount)
    discount_response.publisher_name = discount.publisher.publisher_name if discount.publisher else None
    discount_response.offer_name = discount.offer.offer_name if discount.offer else None
    
    return ResponseBaseSchema.success(data=discount_response)


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[OfferDiscountResponse]],
            summary="获取扣量配置列表")
async def get_discounts(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    discount_type: Optional[str] = Query(None, description="扣量类型过滤"),
    offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
    publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取扣量配置列表（所有登录用户可访问，已重构使用服务层）"""
    # 使用服务层（业务逻辑在DiscountService中）
    discount_service: DiscountService = await get_discount_service(db)
    
    # 调用服务层获取扣量配置列表（服务层会处理查询、过滤、分页）
    discounts, total = await discount_service.get_discounts(
        page=page,
        page_size=page_size,
        discount_type=discount_type,
        offer_id=offer_id,
        publisher_id=publisher_id,
        is_active=is_active
    )
    
    # 构建响应数据
    discount_list = []
    for discount in discounts:
        discount_data = OfferDiscountResponse.model_validate(discount)
        discount_data.publisher_name = discount.publisher.publisher_name if discount.publisher else None
        discount_data.offer_name = discount.offer.offer_name if discount.offer else None
        discount_list.append(discount_data)
    
    return PaginatedResponseBaseSchema.success(
        data=discount_list,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{discount_id}",
            response_model=ResponseBaseSchema[OfferDiscountResponse],
            summary="获取扣量配置详情",
            dependencies=[Depends(require_admin)])
async def get_discount(
    discount_id: int = Path(..., ge=1, description="扣量配置ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取扣量配置详情（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在DiscountService中）
    discount_service: DiscountService = await get_discount_service(db)
    
    # 调用服务层获取扣量配置详情
    discount = await discount_service.get_discount_by_id(discount_id)
    
    if not discount:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"扣量配置ID {discount_id} 不存在"
        )
    
    # 构建响应数据
    discount_data = OfferDiscountResponse.model_validate(discount)
    discount_data.publisher_name = discount.publisher.publisher_name if discount.publisher else None
    discount_data.offer_name = discount.offer.offer_name if discount.offer else None
    
    return ResponseBaseSchema.success(data=discount_data)


@router.put("/{discount_id}",
            response_model=ResponseBaseSchema[OfferDiscountResponse],
            summary="更新扣量配置",
            dependencies=[Depends(require_admin)])
async def update_discount(
    discount_id: int = Path(..., ge=1, description="扣量配置ID"),
    discount_in: OfferDiscountUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新扣量配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在DiscountService中）
    discount_service: DiscountService = await get_discount_service(db)
    
    # 准备更新数据
    update_data = discount_in.model_dump(exclude_unset=True)
    
    # 调用服务层更新扣量配置（服务层会处理所有验证和逻辑）
    discount = await discount_service.update_discount(discount_id, update_data, current_user)
    
    # 构建响应数据
    discount_data = OfferDiscountResponse.model_validate(discount)
    discount_data.publisher_name = discount.publisher.publisher_name if discount.publisher else None
    discount_data.offer_name = discount.offer.offer_name if discount.offer else None
    
    return ResponseBaseSchema.success(data=discount_data)


@router.delete("/{discount_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除扣量配置",
               dependencies=[Depends(require_admin)])
async def delete_discount(
    discount_id: int = Path(..., ge=1, description="扣量配置ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除扣量配置（仅管理员，已重构使用服务层）"""
    # 使用服务层（业务逻辑在DiscountService中）
    discount_service: DiscountService = await get_discount_service(db)
    
    # 调用服务层删除扣量配置（服务层会处理验证和删除）
    await discount_service.delete_discount(discount_id, current_user)
    
    return ResponseBaseSchema.success(data={"message": "扣量配置已删除"})

