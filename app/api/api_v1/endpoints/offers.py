"""
Offer 管理 API
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import User, Offer, Advertiser, Publisher, OfferPublisherAssignment
from app.schemas.cpl.offer import OfferCreate, OfferUpdate, OfferResponse
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/",
             response_model=ResponseBaseSchema[OfferResponse],
             summary="创建Offer",
             dependencies=[Depends(require_admin)])
async def create_offer(
    offer_in: OfferCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建Offer（仅管理员）"""
    # 验证广告主是否存在
    adv_result = await db.execute(
        select(Advertiser).where(Advertiser.id == offer_in.advertiser_id)
    )
    advertiser = adv_result.scalars().first()
    if not advertiser:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"广告主ID {offer_in.advertiser_id} 不存在"
        )
    
    offer = Offer(
        offer_name=offer_in.offer_name,
        advertiser_offer_id=offer_in.advertiser_offer_id,
        advertiser_id=offer_in.advertiser_id,
        preview_link=offer_in.preview_link,
        payout=offer_in.payout,
        affiliate_payout=offer_in.affiliate_payout,
        country=offer_in.country,
        category=offer_in.category,
        type=offer_in.type,
        status=offer_in.status,
        upstream_cap=offer_in.upstream_cap,
        downstream_cap=offer_in.downstream_cap,
        advertiser_tracklink=offer_in.advertiser_tracklink,
        postback_method=offer_in.postback_method,
        is_active=offer_in.is_active
    )
    
    try:
        db.add(offer)
        await db.flush()  # 获取 offer.id
        
        # 生成下游 Tracklink（使用自增ID）
        base_url = getattr(settings, 'TRACKING_BASE_URL', 'https://client.btfrx.online')
        # 下游 Tracklink 模板，实际使用时需要替换 {publisher_id} 和 {click_id}
        downstream_tracklink = f"{base_url.rstrip('/')}/api/v1/track/click/{offer.id}?publisher_id={{publisher_id}}"
        
        # 生成 Postback URL（使用模板，实际使用时替换占位符）
        postback_url = f"{base_url.rstrip('/')}/api/v1/postback?click_id={{click_id}}&offer_id={offer.id}"
        
        # 更新下游tracklink和postback_url
        offer.downstream_tracklink = downstream_tracklink
        offer.postback_url = postback_url
        
        # 处理渠道分配
        if offer_in.publisher_ids:
            for pub_id in offer_in.publisher_ids:
                # 验证渠道是否存在且激活
                pub_result = await db.execute(
                    select(Publisher).where(Publisher.id == pub_id)
                )
                publisher = pub_result.scalars().first()
                if not publisher:
                    raise_api_exception(
                        ErrorCode.RESOURCE_NOT_FOUND,
                        detail=f"渠道ID {pub_id} 不存在"
                    )
                if not publisher.is_active:
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMS,
                        detail=f"渠道ID {pub_id} ({publisher.publisher_name}) 未激活，无法分配"
                    )
                assignment = OfferPublisherAssignment(
                    offer_id=offer.id,
                    publisher_id=pub_id,
                    is_active=True
                )
                db.add(assignment)
        
        await db.commit()
        await db.refresh(offer)
        
        # 加载关联信息
        offer_data = OfferResponse.model_validate(offer)
        offer_data.advertiser_name = advertiser.advertiser_name
        
        logger.info(f"Offer创建成功: id={offer.id}")
        return ResponseBaseSchema.success(data=offer_data)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建Offer失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建Offer失败: {str(e)}"
        )


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[OfferResponse]],
            summary="获取Offer列表",
            dependencies=[Depends(require_admin)])
async def get_offers(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    search: Optional[str] = Query(None, description="搜索关键词（名称、ID）"),
    advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
    status: Optional[str] = Query(None, description="状态过滤"),
    country: Optional[str] = Query(None, description="国家过滤"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取Offer列表（仅管理员）"""
    query = select(Offer)
    
    # 搜索过滤
    if search:
        from sqlalchemy import String
        query = query.where(
            (Offer.offer_name.like(f"%{search}%")) |
            (Offer.id.cast(String).like(f"%{search}%")) |
            (Offer.advertiser_offer_id.like(f"%{search}%"))
        )
    
    # 广告主过滤
    if advertiser_id:
        query = query.where(Offer.advertiser_id == advertiser_id)
    
    # 状态过滤
    if status:
        query = query.where(Offer.status == status)
    
    # 国家过滤
    if country:
        query = query.where(Offer.country == country)
    
    # 激活状态过滤
    if is_active is not None:
        query = query.where(Offer.is_active == is_active)
    
    # 总数
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    
    # 分页
    query = query.order_by(Offer.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    offers = result.scalars().all()
    
    # 加载关联信息
    offer_list = []
    for offer in offers:
        # 加载广告主信息
        adv_result = await db.execute(
            select(Advertiser).where(Advertiser.id == offer.advertiser_id)
        )
        advertiser = adv_result.scalars().first()
        
        # 加载分配的渠道
        pub_result = await db.execute(
            select(OfferPublisherAssignment, Publisher)
            .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
            .where(OfferPublisherAssignment.offer_id == offer.id)
            .where(OfferPublisherAssignment.is_active == True)
        )
        assignments = pub_result.all()
        
        offer_data = OfferResponse.model_validate(offer)
        offer_data.advertiser_name = advertiser.advertiser_name if advertiser else None
        offer_data.assigned_publishers = [
            {
                "id": pub.id,
                "publisher_name": pub.publisher_name
            }
            for _, pub in assignments
        ]
        
        offer_list.append(offer_data)
    
    return PaginatedResponseBaseSchema.success(
        data=offer_list,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{offer_id}",
            response_model=ResponseBaseSchema[OfferResponse],
            summary="获取Offer详情",
            dependencies=[Depends(require_admin)])
async def get_offer(
    offer_id: int = Path(..., ge=1, description="Offer ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取Offer详情（仅管理员）"""
    result = await db.execute(
        select(Offer).where(Offer.id == offer_id)
    )
    offer = result.scalars().first()
    
    if not offer:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Offer ID {offer_id} 不存在"
        )
    
    # 加载关联信息
    adv_result = await db.execute(
        select(Advertiser).where(Advertiser.id == offer.advertiser_id)
    )
    advertiser = adv_result.scalars().first()
    
    pub_result = await db.execute(
        select(OfferPublisherAssignment, Publisher)
        .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
        .where(OfferPublisherAssignment.offer_id == offer.id)
        .where(OfferPublisherAssignment.is_active == True)
    )
    assignments = pub_result.all()
    
    offer_data = OfferResponse.model_validate(offer)
    offer_data.advertiser_name = advertiser.advertiser_name if advertiser else None
    offer_data.assigned_publishers = [
        {
            "id": pub.id,
            "publisher_name": pub.publisher_name
        }
        for _, pub in assignments
    ]
    
    return ResponseBaseSchema.success(data=offer_data)


@router.put("/{offer_id}",
            response_model=ResponseBaseSchema[OfferResponse],
            summary="更新Offer",
            dependencies=[Depends(require_admin)])
async def update_offer(
    offer_id: int = Path(..., ge=1, description="Offer ID"),
    offer_in: OfferUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新Offer（仅管理员）"""
    result = await db.execute(
        select(Offer).where(Offer.id == offer_id)
    )
    offer = result.scalars().first()
    
    if not offer:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Offer ID {offer_id} 不存在"
        )
    
    # 如果更新广告主，验证新广告主是否存在
    if offer_in.advertiser_id and offer_in.advertiser_id != offer.advertiser_id:
        adv_result = await db.execute(
            select(Advertiser).where(Advertiser.id == offer_in.advertiser_id)
        )
        advertiser = adv_result.scalars().first()
        if not advertiser:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"广告主ID {offer_in.advertiser_id} 不存在"
            )
    
    # 更新字段
    update_data = offer_in.model_dump(exclude_unset=True, exclude={'publisher_ids'})
    for key, value in update_data.items():
        setattr(offer, key, value)
    
    # 处理渠道分配
    if 'publisher_ids' in offer_in.model_dump(exclude_unset=True):
        # 先删除所有现有分配
        from sqlalchemy import delete
        await db.execute(
            delete(OfferPublisherAssignment).where(OfferPublisherAssignment.offer_id == offer.id)
        )
        
        # 添加新分配
        if offer_in.publisher_ids:
            for pub_id in offer_in.publisher_ids:
                pub_result = await db.execute(
                    select(Publisher).where(Publisher.id == pub_id)
                )
                publisher = pub_result.scalars().first()
                if not publisher:
                    raise_api_exception(
                        ErrorCode.RESOURCE_NOT_FOUND,
                        detail=f"渠道ID {pub_id} 不存在"
                    )
                if not publisher.is_active:
                    raise_api_exception(
                        ErrorCode.INVALID_PARAMS,
                        detail=f"渠道ID {pub_id} ({publisher.publisher_name}) 未激活，无法分配"
                    )
                assignment = OfferPublisherAssignment(
                    offer_id=offer.id,
                    publisher_id=pub_id,
                    is_active=True
                )
                db.add(assignment)
    
    try:
        await db.commit()
        await db.refresh(offer)
        
        # 加载关联信息
        adv_result = await db.execute(
            select(Advertiser).where(Advertiser.id == offer.advertiser_id)
        )
        advertiser = adv_result.scalars().first()
        
        offer_data = OfferResponse.model_validate(offer)
        offer_data.advertiser_name = advertiser.advertiser_name if advertiser else None
        
        logger.info(f"Offer更新成功: id={offer.id}")
        return ResponseBaseSchema.success(data=offer_data)
    except Exception as e:
        await db.rollback()
        logger.error(f"更新Offer失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新Offer失败: {str(e)}"
        )


@router.delete("/{offer_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除Offer",
               dependencies=[Depends(require_admin)])
async def delete_offer(
    offer_id: int = Path(..., ge=1, description="Offer ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除Offer（仅管理员）"""
    result = await db.execute(
        select(Offer).where(Offer.id == offer_id)
    )
    offer = result.scalars().first()
    
    if not offer:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Offer ID {offer_id} 不存在"
        )
    
    try:
        from sqlalchemy import delete
        await db.execute(delete(Offer).where(Offer.id == offer_id))
        await db.commit()
        
        logger.info(f"Offer删除成功: id={offer.id}")
        return ResponseBaseSchema.success(data={"message": "Offer已删除"})
    except Exception as e:
        await db.rollback()
        logger.error(f"删除Offer失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除Offer失败: {str(e)}"
        )

