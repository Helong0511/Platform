"""
Offer 管理 API
"""
import logging
from typing import Optional, Set
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_, delete

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import User, Offer, Advertiser, Publisher, OfferPublisherAssignment, ShortLink
from app.schemas.cpl.offer import OfferCreate, OfferUpdate, OfferResponse
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.core.config import settings
from app.core.short_link.generator import (
    generate_short_code_from_id,
    generate_unique_short_code
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def create_short_link_for_channel(
    db: AsyncSession,
    offer_id: int,
    channel_id: int,
    offer_name: str,
    publisher_name: str,
    base_url: str,
    current_user_id: int
) -> Optional[ShortLink]:
    """
    为指定渠道创建短链接
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        channel_id: 渠道ID (Publisher ID)
        offer_name: Offer名称
        publisher_name: 渠道名称
        base_url: 追踪服务基础URL
        current_user_id: 当前用户ID
        
    Returns:
        创建的短链接对象，如果失败返回None
    """
    try:
        # 生成短链接的原始URL（包含offer_id和channel_id参数）
        # 格式：{base_url}/api/v1/track/click/{offer_id}?publisher_id={channel_id}
        original_url = f"{base_url.rstrip('/')}/api/v1/track/click/{offer_id}?publisher_id={channel_id}"
        
        # 检查是否已存在相同URL的短链接
        existing_result = await db.execute(
            select(ShortLink).where(
                ShortLink.original_url == original_url,
                ShortLink.offer_id == offer_id,
                ShortLink.channel_id == channel_id
            )
        )
        existing_link = existing_result.scalars().first()
        
        if existing_link:
            # 如果已存在，直接返回
            logger.info(f"短链接已存在: offer_id={offer_id}, channel_id={channel_id}")
            return existing_link
        
        # 创建新的短链接
        short_link = ShortLink(
            original_url=original_url,
            title=f"{offer_name} - {publisher_name}",
            description=f"Offer: {offer_name}, 渠道: {publisher_name}",
            offer_id=offer_id,
            channel_id=channel_id,
            created_by=current_user_id,
            is_active=True,
            click_count=0
        )
        
        db.add(short_link)
        await db.flush()  # 先flush以获取ID
        
        # 生成短链接代码
        result = await db.execute(select(ShortLink.short_code))
        existing_codes = {row[0] for row in result.all()}
        
        # 尝试从ID生成
        code_from_id = generate_short_code_from_id(short_link.id, min_length=4)
        if code_from_id not in existing_codes:
            short_link.short_code = code_from_id
        else:
            # 如果ID生成的代码已存在，使用随机生成
            unique_code = generate_unique_short_code(existing_codes, length=6)
            if not unique_code:
                logger.error(f"生成短链接代码失败: offer_id={offer_id}, channel_id={channel_id}")
                return None
            short_link.short_code = unique_code
        
        logger.info(f"为渠道创建短链接成功: offer_id={offer_id}, channel_id={channel_id}, short_code={short_link.short_code}")
        return short_link
        
    except Exception as e:
        logger.error(f"为渠道创建短链接失败: offer_id={offer_id}, channel_id={channel_id}, error={str(e)}", exc_info=True)
        return None


async def sync_short_links_for_offer(
    db: AsyncSession,
    offer_id: int,
    publisher_ids: Optional[list[int]],
    offer_name: str,
    base_url: str,
    current_user_id: int
) -> None:
    """
    同步Offer的短链接（根据分配的渠道）
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        publisher_ids: 分配的渠道ID列表
        offer_name: Offer名称
        base_url: 追踪服务基础URL
        current_user_id: 当前用户ID
    """
    try:
        # 获取当前已存在的短链接（该Offer的所有短链接）
        existing_links_result = await db.execute(
            select(ShortLink).where(ShortLink.offer_id == offer_id)
        )
        existing_links = existing_links_result.scalars().all()
        
        # 构建现有短链接的渠道ID集合
        existing_channel_ids: Set[int] = {link.channel_id for link in existing_links if link.channel_id}
        
        # 构建目标渠道ID集合
        target_channel_ids: Set[int] = set(publisher_ids or [])
        
        # 1. 删除不再分配的渠道的短链接
        channels_to_remove = existing_channel_ids - target_channel_ids
        if channels_to_remove:
            for channel_id in channels_to_remove:
                await db.execute(
                    delete(ShortLink).where(
                        ShortLink.offer_id == offer_id,
                        ShortLink.channel_id == channel_id
                    )
                )
            logger.info(f"删除不再分配的渠道短链接: offer_id={offer_id}, channels={channels_to_remove}")
        
        # 2. 为新分配的渠道创建短链接
        channels_to_add = target_channel_ids - existing_channel_ids
        if channels_to_add:
            for channel_id in channels_to_add:
                # 获取渠道信息
                pub_result = await db.execute(
                    select(Publisher).where(Publisher.id == channel_id)
                )
                publisher = pub_result.scalars().first()
                
                if publisher:
                    await create_short_link_for_channel(
                        db=db,
                        offer_id=offer_id,
                        channel_id=channel_id,
                        offer_name=offer_name,
                        publisher_name=publisher.publisher_name,
                        base_url=base_url,
                        current_user_id=current_user_id
                    )
            logger.info(f"为新分配的渠道创建短链接: offer_id={offer_id}, channels={channels_to_add}")
            
    except Exception as e:
        logger.error(f"同步Offer短链接失败: offer_id={offer_id}, error={str(e)}", exc_info=True)
        # 不抛出异常，避免影响Offer的创建/更新


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
        click_validity_hours=offer_in.click_validity_hours,
        is_active=offer_in.is_active
    )
    
    try:
        db.add(offer)
        await db.flush()  # 获取 offer.id
        
        # 生成下游 Tracklink（使用自增ID）
        base_url = settings.TRACKING_BASE_URL
        # 下游 Tracklink 格式：/api/v1/track/click/{offer_id}?publisher_id={publisher_id}
        # 实际使用时，publisher_id 会通过查询参数传入
        downstream_tracklink = f"{base_url.rstrip('/')}/api/v1/track/click/{offer.id}?publisher_id={{publisher_id}}"
        
        # 生成 Postback URL（使用模板，实际使用时替换占位符）
        # 格式：/api/v1/postback?click_id={click_id}&offer_id={offer_id}
        postback_url = f"{base_url.rstrip('/')}/api/v1/postback?click_id={{click_id}}&offer_id={offer.id}"
        
        # 更新下游tracklink和postback_url
        offer.downstream_tracklink = downstream_tracklink
        offer.postback_url = postback_url
        
        # 处理渠道分配
        if offer_in.publisher_ids:
            for pub_id in offer_in.publisher_ids:
                # 验证渠道是否存在
                pub_result = await db.execute(
                    select(Publisher).where(Publisher.id == pub_id)
                )
                publisher = pub_result.scalars().first()
                if publisher:
                    assignment = OfferPublisherAssignment(
                        offer_id=offer.id,
                        publisher_id=pub_id,
                        is_active=True
                    )
                    db.add(assignment)
        
        await db.commit()
        await db.refresh(offer)
        
        # 为分配的渠道创建短链接
        if offer_in.publisher_ids:
            await sync_short_links_for_offer(
                db=db,
                offer_id=offer.id,
                publisher_ids=offer_in.publisher_ids,
                offer_name=offer.offer_name,
                base_url=base_url,
                current_user_id=current_user.id
            )
            await db.commit()  # 提交短链接创建
        
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
    
    # 使用joinedload优化关联查询，减少N+1查询问题
    from sqlalchemy.orm import joinedload, selectinload
    query = query.options(joinedload(Offer.advertiser))
    result = await db.execute(query)
    offers = result.scalars().all()
    
    # 加载关联信息
    offer_list = []
    # 批量加载所有offer的渠道分配
    offer_ids = [offer.id for offer in offers]
    if offer_ids:
        pub_result = await db.execute(
            select(OfferPublisherAssignment, Publisher)
            .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
            .where(OfferPublisherAssignment.offer_id.in_(offer_ids))
            .where(OfferPublisherAssignment.is_active == True)
        )
        assignments_map = {}
        for assignment, publisher in pub_result.all():
            if assignment.offer_id not in assignments_map:
                assignments_map[assignment.offer_id] = []
            assignments_map[assignment.offer_id].append({
                "id": publisher.id,
                "publisher_name": publisher.publisher_name
            })
    else:
        assignments_map = {}
    
    for offer in offers:
        offer_data = OfferResponse.model_validate(offer)
        # 从已加载的关联中获取广告主名称
        offer_data.advertiser_name = offer.advertiser.advertiser_name if offer.advertiser else None
        # 从批量查询的结果中获取渠道分配
        offer_data.assigned_publishers = assignments_map.get(offer.id, [])
        
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
    # 使用joinedload优化关联查询
    from sqlalchemy.orm import joinedload
    query = select(Offer).where(Offer.id == offer_id).options(joinedload(Offer.advertiser))
    result = await db.execute(query)
    offer = result.scalars().first()
    
    if not offer:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Offer ID {offer_id} 不存在"
        )
    
    # 加载分配的渠道
    pub_result = await db.execute(
        select(OfferPublisherAssignment, Publisher)
        .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
        .where(OfferPublisherAssignment.offer_id == offer.id)
        .where(OfferPublisherAssignment.is_active == True)
    )
    assignments = pub_result.all()
    
    offer_data = OfferResponse.model_validate(offer)
    # 从已加载的关联中获取广告主名称
    offer_data.advertiser_name = offer.advertiser.advertiser_name if offer.advertiser else None
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
    old_publisher_ids = None
    if 'publisher_ids' in offer_in.model_dump(exclude_unset=True):
        # 获取旧的渠道分配列表（用于比较）
        old_assignments_result = await db.execute(
            select(OfferPublisherAssignment).where(OfferPublisherAssignment.offer_id == offer.id)
        )
        old_assignments = old_assignments_result.scalars().all()
        old_publisher_ids = {assignment.publisher_id for assignment in old_assignments}
        
        # 先删除所有现有分配
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
                if publisher:
                    assignment = OfferPublisherAssignment(
                        offer_id=offer.id,
                        publisher_id=pub_id,
                        is_active=True
                    )
                    db.add(assignment)
    
    try:
        await db.commit()
        
        # 如果渠道分配有变化，同步短链接
        if 'publisher_ids' in offer_in.model_dump(exclude_unset=True):
            new_publisher_ids = set(offer_in.publisher_ids or [])
            if old_publisher_ids != new_publisher_ids:
                # 渠道分配有变化，同步短链接
                base_url = settings.TRACKING_BASE_URL
                await sync_short_links_for_offer(
                    db=db,
                    offer_id=offer.id,
                    publisher_ids=offer_in.publisher_ids,
                    offer_name=offer.offer_name,
                    base_url=base_url,
                    current_user_id=current_user.id
                )
                await db.commit()  # 提交短链接变更
        
        # 重新加载关联信息（使用joinedload优化）
        from sqlalchemy.orm import joinedload
        query = select(Offer).where(Offer.id == offer.id).options(joinedload(Offer.advertiser))
        result = await db.execute(query)
        offer = result.scalars().first()
        
        # 加载分配的渠道
        pub_result = await db.execute(
            select(OfferPublisherAssignment, Publisher)
            .join(Publisher, OfferPublisherAssignment.publisher_id == Publisher.id)
            .where(OfferPublisherAssignment.offer_id == offer.id)
            .where(OfferPublisherAssignment.is_active == True)
        )
        assignments = pub_result.all()
        
        offer_data = OfferResponse.model_validate(offer)
        offer_data.advertiser_name = offer.advertiser.advertiser_name if offer.advertiser else None
        offer_data.assigned_publishers = [
            {
                "id": pub.id,
                "publisher_name": pub.publisher_name
            }
            for _, pub in assignments
        ]
        
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

