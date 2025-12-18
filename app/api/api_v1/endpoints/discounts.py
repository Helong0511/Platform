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
    """创建扣量配置（仅管理员）"""
    # 验证渠道是否存在
    pub_result = await db.execute(
        select(Publisher).where(Publisher.id == discount_in.publisher_id)
    )
    publisher = pub_result.scalars().first()
    if not publisher:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"渠道ID {discount_in.publisher_id} 不存在"
        )
    
    # 如果是offer类型，验证Offer
    if discount_in.discount_type == 'offer' and discount_in.offer_id:
        offer_result = await db.execute(
            select(Offer).where(Offer.id == discount_in.offer_id)
        )
        offer = offer_result.scalars().first()
        if not offer:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Offer ID {discount_in.offer_id} 不存在"
            )
    
    discount = OfferDiscount(
        discount_type=discount_in.discount_type,
        offer_id=discount_in.offer_id,
        publisher_id=discount_in.publisher_id,
        discount_ratio=discount_in.discount_ratio,
        is_active=discount_in.is_active
    )
    
    try:
        db.add(discount)
        await db.commit()
        await db.refresh(discount)
        
        # 加载关联信息
        discount_data = OfferDiscountResponse.model_validate(discount)
        discount_data.publisher_name = publisher.publisher_name
        
        if discount.offer_id:
            offer_result = await db.execute(
                select(Offer).where(Offer.id == discount.offer_id)
            )
            offer = offer_result.scalars().first()
            if offer:
                discount_data.offer_name = offer.offer_name
        
        logger.info(f"扣量配置创建成功: discount_id={discount.id}")
        return ResponseBaseSchema.success(data=discount_data)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建扣量配置失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建扣量配置失败: {str(e)}"
        )


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[OfferDiscountResponse]],
            summary="获取扣量配置列表",
            dependencies=[Depends(require_admin)])
async def get_discounts(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    discount_type: Optional[str] = Query(None, description="扣量类型过滤"),
    offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
    publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取扣量配置列表（仅管理员）"""
    query = select(OfferDiscount)
    
    if discount_type:
        query = query.where(OfferDiscount.discount_type == discount_type)
    
    if offer_id:
        query = query.where(OfferDiscount.offer_id == offer_id)
    
    if publisher_id:
        query = query.where(OfferDiscount.publisher_id == publisher_id)
    
    if is_active is not None:
        query = query.where(OfferDiscount.is_active == is_active)
    
    # 总数
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    
    # 分页
    query = query.order_by(OfferDiscount.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    discounts = result.scalars().all()
    
    # 加载关联信息
    discount_list = []
    for discount in discounts:
        # 加载渠道信息
        pub_result = await db.execute(
            select(Publisher).where(Publisher.id == discount.publisher_id)
        )
        publisher = pub_result.scalars().first()
        
        discount_data = OfferDiscountResponse.model_validate(discount)
        discount_data.publisher_name = publisher.publisher_name if publisher else None
        
        # 加载Offer信息
        if discount.offer_id:
            offer_result = await db.execute(
                select(Offer).where(Offer.id == discount.offer_id)
            )
            offer = offer_result.scalars().first()
            if offer:
                discount_data.offer_name = offer.offer_name
        
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
    """获取扣量配置详情（仅管理员）"""
    result = await db.execute(
        select(OfferDiscount).where(OfferDiscount.id == discount_id)
    )
    discount = result.scalars().first()
    
    if not discount:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"扣量配置ID {discount_id} 不存在"
        )
    
    # 加载关联信息
    pub_result = await db.execute(
        select(Publisher).where(Publisher.id == discount.publisher_id)
    )
    publisher = pub_result.scalars().first()
    
    discount_data = OfferDiscountResponse.model_validate(discount)
    discount_data.publisher_name = publisher.publisher_name if publisher else None
    
    if discount.offer_id:
        offer_result = await db.execute(
            select(Offer).where(Offer.id == discount.offer_id)
        )
        offer = offer_result.scalars().first()
        if offer:
            discount_data.offer_name = offer.offer_name
    
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
    """更新扣量配置（仅管理员）"""
    result = await db.execute(
        select(OfferDiscount).where(OfferDiscount.id == discount_id)
    )
    discount = result.scalars().first()
    
    if not discount:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"扣量配置ID {discount_id} 不存在"
        )
    
    # 更新字段
    update_data = discount_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(discount, key, value)
    
    try:
        await db.commit()
        await db.refresh(discount)
        
        # 加载关联信息
        pub_result = await db.execute(
            select(Publisher).where(Publisher.id == discount.publisher_id)
        )
        publisher = pub_result.scalars().first()
        
        discount_data = OfferDiscountResponse.model_validate(discount)
        discount_data.publisher_name = publisher.publisher_name if publisher else None
        
        if discount.offer_id:
            offer_result = await db.execute(
                select(Offer).where(Offer.id == discount.offer_id)
            )
            offer = offer_result.scalars().first()
            if offer:
                discount_data.offer_name = offer.offer_name
        
        logger.info(f"扣量配置更新成功: discount_id={discount_id}")
        return ResponseBaseSchema.success(data=discount_data)
    except Exception as e:
        await db.rollback()
        logger.error(f"更新扣量配置失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新扣量配置失败: {str(e)}"
        )


@router.delete("/{discount_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除扣量配置",
               dependencies=[Depends(require_admin)])
async def delete_discount(
    discount_id: int = Path(..., ge=1, description="扣量配置ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除扣量配置（仅管理员）"""
    result = await db.execute(
        select(OfferDiscount).where(OfferDiscount.id == discount_id)
    )
    discount = result.scalars().first()
    
    if not discount:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"扣量配置ID {discount_id} 不存在"
        )
    
    try:
        from sqlalchemy import delete
        await db.execute(delete(OfferDiscount).where(OfferDiscount.id == discount_id))
        await db.commit()
        
        logger.info(f"扣量配置删除成功: discount_id={discount_id}")
        return ResponseBaseSchema.success(data={"message": "扣量配置已删除"})
    except Exception as e:
        await db.rollback()
        logger.error(f"删除扣量配置失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除扣量配置失败: {str(e)}"
        )

