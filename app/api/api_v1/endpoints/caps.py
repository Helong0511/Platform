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
from app.models.models import User, OfferCap, Offer, Advertiser, Publisher
from app.schemas.cpl.cap import OfferCapCreate, OfferCapUpdate, OfferCapResponse
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

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
    """创建Cap配置（仅管理员）"""
    # 验证Offer是否存在
    offer_result = await db.execute(
        select(Offer).where(Offer.id == cap_in.offer_id)
    )
    offer = offer_result.scalars().first()
    if not offer:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Offer ID {cap_in.offer_id} 不存在"
        )
    
    # 如果是advertiser_offer类型，验证广告主
    if cap_in.cap_type == 'advertiser_offer' and cap_in.advertiser_id:
        adv_result = await db.execute(
            select(Advertiser).where(Advertiser.id == cap_in.advertiser_id)
        )
        advertiser = adv_result.scalars().first()
        if not advertiser:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"广告主ID {cap_in.advertiser_id} 不存在"
            )
    
    # 如果指定了渠道，验证渠道
    if cap_in.publisher_id:
        pub_result = await db.execute(
            select(Publisher).where(Publisher.id == cap_in.publisher_id)
        )
        publisher = pub_result.scalars().first()
        if not publisher:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"渠道ID {cap_in.publisher_id} 不存在"
            )
    
    # 设置Cap开始日期（用于Total Cap）
    cap_start_date = None
    if cap_in.total_cap:
        cap_start_date = datetime.now(timezone.utc)
    
    cap = OfferCap(
        cap_type=cap_in.cap_type,
        advertiser_id=cap_in.advertiser_id,
        offer_id=cap_in.offer_id,
        publisher_id=cap_in.publisher_id,
        daily_cap=cap_in.daily_cap,
        total_cap=cap_in.total_cap,
        current_daily_count=0,
        current_total_count=0,
        cap_start_date=cap_start_date,
        is_active=cap_in.is_active
    )
    
    try:
        db.add(cap)
        await db.commit()
        await db.refresh(cap)
        
        # 加载关联信息
        cap_data = OfferCapResponse.model_validate(cap)
        cap_data.offer_name = offer.offer_name
        if cap.advertiser_id:
            adv_result = await db.execute(
                select(Advertiser).where(Advertiser.id == cap.advertiser_id)
            )
            advertiser = adv_result.scalars().first()
            if advertiser:
                cap_data.advertiser_name = advertiser.advertiser_name
        if cap.publisher_id:
            pub_result = await db.execute(
                select(Publisher).where(Publisher.id == cap.publisher_id)
            )
            publisher = pub_result.scalars().first()
            if publisher:
                cap_data.publisher_name = publisher.publisher_name
        
        logger.info(f"Cap配置创建成功: cap_id={cap.id}")
        return ResponseBaseSchema.success(data=cap_data)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建Cap配置失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建Cap配置失败: {str(e)}"
        )


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[OfferCapResponse]],
            summary="获取Cap配置列表",
            dependencies=[Depends(require_admin)])
async def get_caps(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    cap_type: Optional[str] = Query(None, description="Cap类型过滤"),
    offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
    advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
    publisher_id: Optional[int] = Query(None, description="渠道ID过滤"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取Cap配置列表（仅管理员）"""
    query = select(OfferCap)
    
    if cap_type:
        query = query.where(OfferCap.cap_type == cap_type)
    
    if offer_id:
        query = query.where(OfferCap.offer_id == offer_id)
    
    if advertiser_id:
        query = query.where(OfferCap.advertiser_id == advertiser_id)
    
    if publisher_id:
        query = query.where(OfferCap.publisher_id == publisher_id)
    
    if is_active is not None:
        query = query.where(OfferCap.is_active == is_active)
    
    # 总数
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    
    # 分页
    query = query.order_by(OfferCap.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    # 使用JOIN优化查询，避免N+1问题
    from sqlalchemy.orm import aliased
    offer_alias = aliased(Offer)
    advertiser_alias = aliased(Advertiser)
    publisher_alias = aliased(Publisher)
    
    query = query.outerjoin(offer_alias, OfferCap.offer_id == offer_alias.id)
    query = query.outerjoin(advertiser_alias, OfferCap.advertiser_id == advertiser_alias.id)
    query = query.outerjoin(publisher_alias, OfferCap.publisher_id == publisher_alias.id)
    
    # 选择所有需要的字段
    query = query.add_columns(
        offer_alias.offer_name,
        advertiser_alias.advertiser_name,
        publisher_alias.publisher_name
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    # 构建响应数据
    cap_list = []
    for row in rows:
        cap = row[0]  # OfferCap对象
        offer_name = row[1] if len(row) > 1 else None
        advertiser_name = row[2] if len(row) > 2 else None
        publisher_name = row[3] if len(row) > 3 else None
        
        cap_data = OfferCapResponse.model_validate(cap)
        cap_data.offer_name = offer_name
        cap_data.advertiser_name = advertiser_name
        cap_data.publisher_name = publisher_name
        
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
    """获取Cap配置详情（仅管理员）"""
    result = await db.execute(
        select(OfferCap).where(OfferCap.id == cap_id)
    )
    cap = result.scalars().first()
    
    if not cap:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Cap配置ID {cap_id} 不存在"
        )
    
    # 加载关联信息
    offer_result = await db.execute(
        select(Offer).where(Offer.id == cap.offer_id)
    )
    offer = offer_result.scalars().first()
    
    cap_data = OfferCapResponse.model_validate(cap)
    cap_data.offer_name = offer.offer_name if offer else None
    
    if cap.advertiser_id:
        adv_result = await db.execute(
            select(Advertiser).where(Advertiser.id == cap.advertiser_id)
        )
        advertiser = adv_result.scalars().first()
        if advertiser:
            cap_data.advertiser_name = advertiser.advertiser_name
    
    if cap.publisher_id:
        pub_result = await db.execute(
            select(Publisher).where(Publisher.id == cap.publisher_id)
        )
        publisher = pub_result.scalars().first()
        if publisher:
            cap_data.publisher_name = publisher.publisher_name
    
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
    """更新Cap配置（仅管理员）"""
    result = await db.execute(
        select(OfferCap).where(OfferCap.id == cap_id)
    )
    cap = result.scalars().first()
    
    if not cap:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Cap配置ID {cap_id} 不存在"
        )
    
    # 更新字段
    update_data = cap_in.model_dump(exclude_unset=True)
    
    # 如果更新了total_cap且之前没有cap_start_date，设置开始日期
    if 'total_cap' in update_data and update_data['total_cap'] and not cap.cap_start_date:
        update_data['cap_start_date'] = datetime.now(timezone.utc)
    
    for key, value in update_data.items():
        setattr(cap, key, value)
    
    try:
        await db.commit()
        await db.refresh(cap)
        
        # 加载关联信息
        offer_result = await db.execute(
            select(Offer).where(Offer.id == cap.offer_id)
        )
        offer = offer_result.scalars().first()
        
        cap_data = OfferCapResponse.model_validate(cap)
        cap_data.offer_name = offer.offer_name if offer else None
        
        if cap.advertiser_id:
            adv_result = await db.execute(
                select(Advertiser).where(Advertiser.id == cap.advertiser_id)
            )
            advertiser = adv_result.scalars().first()
            if advertiser:
                cap_data.advertiser_name = advertiser.advertiser_name
        
        if cap.publisher_id:
            pub_result = await db.execute(
                select(Publisher).where(Publisher.id == cap.publisher_id)
            )
            publisher = pub_result.scalars().first()
            if publisher:
                cap_data.publisher_name = publisher.publisher_name
        
        logger.info(f"Cap配置更新成功: cap_id={cap_id}")
        return ResponseBaseSchema.success(data=cap_data)
    except Exception as e:
        await db.rollback()
        logger.error(f"更新Cap配置失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新Cap配置失败: {str(e)}"
        )


@router.delete("/{cap_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除Cap配置",
               dependencies=[Depends(require_admin)])
async def delete_cap(
    cap_id: int = Path(..., ge=1, description="Cap配置ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除Cap配置（仅管理员）"""
    result = await db.execute(
        select(OfferCap).where(OfferCap.id == cap_id)
    )
    cap = result.scalars().first()
    
    if not cap:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Cap配置ID {cap_id} 不存在"
        )
    
    try:
        from sqlalchemy import delete
        await db.execute(delete(OfferCap).where(OfferCap.id == cap_id))
        await db.commit()
        
        logger.info(f"Cap配置删除成功: cap_id={cap_id}")
        return ResponseBaseSchema.success(data={"message": "Cap配置已删除"})
    except Exception as e:
        await db.rollback()
        logger.error(f"删除Cap配置失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除Cap配置失败: {str(e)}"
        )

