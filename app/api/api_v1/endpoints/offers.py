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


async def create_short_link_for_offer(
    db: AsyncSession,
    offer_id: int,
    offer_name: str,
    base_url: str,
    current_user_id: int,
    advertiser_tracklink: Optional[str] = None
) -> tuple[Optional[ShortLink], bool]:
    """
    为Offer创建主短链接（不区分渠道）
    使用上游Tracklink（advertiser_tracklink）作为原始URL
    每个渠道使用主短链接 + 参数（offer_id和channel_id）
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        offer_name: Offer名称
        base_url: 追踪服务基础URL
        current_user_id: 当前用户ID
        advertiser_tracklink: 上游Tracklink（用作短链接的原始URL）
        
    Returns:
        (短链接对象, 是否重复) 元组，如果失败返回 (None, False)
    """
    try:
        # 使用上游Tracklink作为原始URL
        if not advertiser_tracklink:
            logger.warning(f"Offer {offer_id} 没有配置上游Tracklink，无法创建短链接")
            return None, False
        
        original_url = advertiser_tracklink
        
        # 检查是否已存在该Offer的主短链接（channel_id为NULL）
        existing_result = await db.execute(
            select(ShortLink).where(
                and_(
                    ShortLink.offer_id == offer_id,
                    ShortLink.channel_id.is_(None)  # 主短链接的channel_id为NULL
                )
            )
        )
        existing_link = existing_result.scalars().first()
        
        if existing_link:
            # 如果已存在，返回已存在的短链接和重复标志
            logger.info(f"Offer主短链接已存在: offer_id={offer_id}, short_code={existing_link.short_code}")
            return existing_link, True
        
        # 创建新的主短链接（channel_id为NULL）
        # 先设置临时的short_code，避免NOT NULL约束错误
        short_link = ShortLink(
            original_url=original_url,
            title=f"{offer_name} - 主短链接",
            description=f"Offer: {offer_name} 的主短链接",
            offer_id=offer_id,  # 保存 Offer ID
            channel_id=None,  # 主短链接的channel_id为NULL
            created_by=current_user_id,
            is_active=True,
            click_count=0,
            short_code="temp"  # 临时代码，稍后更新
        )
        
        db.add(short_link)
        await db.flush()  # 先flush以获取ID
        
        # 生成短链接代码
        result = await db.execute(select(ShortLink.short_code))
        existing_codes = {row[0] for row in result.all() if row[0] != "temp"}  # 排除临时代码
        
        # 尝试从ID生成
        code_from_id = generate_short_code_from_id(short_link.id, min_length=4)
        if code_from_id not in existing_codes:
            short_link.short_code = code_from_id
        else:
            # 如果ID生成的代码已存在，使用随机生成
            unique_code = generate_unique_short_code(existing_codes, length=6)
            if not unique_code:
                logger.error(f"生成短链接代码失败: offer_id={offer_id}")
                return None, False
            short_link.short_code = unique_code
        
        logger.info(
            f"为Offer创建主短链接成功: "
            f"short_link_id={short_link.id}, "
            f"short_code={short_link.short_code}, "
            f"offer_id={short_link.offer_id}, "
            f"original_url={original_url}"
        )
        return short_link, False  # 新创建的，不是重复
        
    except Exception as e:
        logger.error(f"为Offer创建主短链接失败: offer_id={offer_id}, error={str(e)}", exc_info=True)
        return None, False


def get_short_link_url(base_url: str, short_code: str) -> str:
    """
    生成短链接的完整URL
    
    Args:
        base_url: 基础URL
        short_code: 短链接代码
        
    Returns:
        完整的短链接URL
    """
    return f"{base_url.rstrip('/')}/s/{short_code}"


async def sync_short_links_for_offer(
    db: AsyncSession,
    offer_id: int,
    publisher_ids: Optional[list[int]],
    offer_name: str,
    base_url: str,
    current_user_id: int,
    advertiser_tracklink: Optional[str] = None
) -> dict:
    """
    同步Offer的主短链接
    只为Offer创建一个主短链接（channel_id为NULL），每个渠道使用主短链接 + 参数
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        publisher_ids: 分配的渠道ID列表（用于验证，不影响短链接创建）
        offer_name: Offer名称
        base_url: 追踪服务基础URL
        current_user_id: 当前用户ID
        advertiser_tracklink: 上游Tracklink（用作短链接的原始URL）
        
    Returns:
        包含短链接信息的字典：{
            'created': bool  # 是否新创建
            'duplicate': bool  # 是否重复
            'final_short_link_url': str  # 主短链接URL
        }
    """
    result = {
        'created': False,
        'duplicate': False,
        'final_short_link_url': None
    }
    
    try:
        # 如果没有上游Tracklink，无法创建短链接
        if not advertiser_tracklink:
            logger.warning(f"Offer {offer_id} 没有配置上游Tracklink，跳过短链接创建")
            return result
        
        # 删除该Offer的所有旧短链接（包括channel_id为NULL的主短链接和channel_id不为NULL的旧短链接）
        await db.execute(
            delete(ShortLink).where(ShortLink.offer_id == offer_id)
        )
        logger.info(f"删除Offer的所有旧短链接: offer_id={offer_id}")
        
        # 创建主短链接（channel_id为NULL）
        short_link, is_duplicate = await create_short_link_for_offer(
            db=db,
            offer_id=offer_id,
            offer_name=offer_name,
            base_url=base_url,
            current_user_id=current_user_id,
            advertiser_tracklink=advertiser_tracklink
        )
        
        if short_link:
            short_link_url = get_short_link_url(base_url, short_link.short_code)
            result['final_short_link_url'] = short_link_url
            result['created'] = not is_duplicate
            result['duplicate'] = is_duplicate
            
            # 更新Offer的downstream_tracklink为主短链接URL
            offer_result = await db.execute(
                select(Offer).where(Offer.id == offer_id)
            )
            offer = offer_result.scalars().first()
            
            if offer:
                offer.downstream_tracklink = short_link_url
                logger.info(f"更新Offer的downstream_tracklink: offer_id={offer_id}, tracklink={short_link_url}")
        else:
            # 如果创建失败，清空downstream_tracklink
            offer_result = await db.execute(
                select(Offer).where(Offer.id == offer_id)
            )
            offer = offer_result.scalars().first()
            
            if offer:
                offer.downstream_tracklink = None
                logger.warning(f"清空Offer的downstream_tracklink: offer_id={offer_id}（创建短链接失败）")
        
        return result
        
    except Exception as e:
        logger.error(f"同步Offer短链接失败: offer_id={offer_id}, error={str(e)}", exc_info=True)
        return result
            
    except Exception as e:
        logger.error(f"同步Offer短链接失败: offer_id={offer_id}, error={str(e)}", exc_info=True)
        # 不抛出异常，避免影响Offer的创建/更新
    
    return result


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
        publisher_ids_for_short_link = []
        if offer_in.publisher_configs is not None:
            # 使用新的渠道配置方式
            # 验证不能为空数组
            if len(offer_in.publisher_configs) == 0:
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="渠道配置不能为空，请至少添加一个渠道"
                )
            
            # 验证是否有重复的publisher_id
            publisher_ids = [config.publisher_id for config in offer_in.publisher_configs]
            if len(publisher_ids) != len(set(publisher_ids)):
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="渠道配置中存在重复的渠道ID"
                )
            
            for config in offer_in.publisher_configs:
                # 验证渠道是否存在
                pub_result = await db.execute(
                    select(Publisher).where(Publisher.id == config.publisher_id)
                )
                publisher = pub_result.scalars().first()
                if not publisher:
                    raise_api_exception(
                        ErrorCode.RESOURCE_NOT_FOUND,
                        detail=f"渠道ID {config.publisher_id} 不存在"
                    )
                
                assignment = OfferPublisherAssignment(
                    offer_id=offer.id,
                    publisher_id=config.publisher_id,
                    downstream_cap=config.downstream_cap,
                    affiliate_payout=config.affiliate_payout,
                    is_active=True
                )
                db.add(assignment)
                publisher_ids_for_short_link.append(config.publisher_id)
        elif offer_in.publisher_ids:
            # 向后兼容：使用旧的publisher_ids方式
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
                    publisher_ids_for_short_link.append(pub_id)
        
        await db.commit()
        await db.refresh(offer)
        
        # 为分配的渠道创建短链接（使用上游Tracklink作为原始URL）
        short_link_info = None
        if publisher_ids_for_short_link and offer.advertiser_tracklink:
            short_link_info = await sync_short_links_for_offer(
                db=db,
                offer_id=offer.id,
                publisher_ids=publisher_ids_for_short_link,
                offer_name=offer.offer_name,
                base_url=base_url,
                current_user_id=current_user.id,
                advertiser_tracklink=offer.advertiser_tracklink
            )
            await db.commit()  # 提交短链接创建
            
            # 刷新offer以获取更新后的downstream_tracklink
            await db.refresh(offer)
        elif publisher_ids_for_short_link and not offer.advertiser_tracklink:
            logger.warning(f"Offer {offer.id} 没有配置上游Tracklink，无法创建短链接")
        
        # 加载关联信息
        offer_data = OfferResponse.model_validate(offer)
        offer_data.advertiser_name = advertiser.advertiser_name
        
        # 构建响应消息，包含短链接信息
        message = "Offer创建成功"
        if short_link_info:
            if short_link_info.get('duplicate'):
                message = (
                    f"Offer创建成功。"
                    f"主短链接已存在: {short_link_info.get('final_short_link_url', 'N/A')}。"
                    f"每个渠道使用主短链接 + 参数（offer_id和channel_id）"
                )
            elif short_link_info.get('created'):
                message = (
                    f"Offer创建成功。"
                    f"已创建主短链接: {short_link_info.get('final_short_link_url', 'N/A')}。"
                    f"每个渠道使用主短链接 + 参数（offer_id和channel_id）"
                )
            elif short_link_info.get('final_short_link_url'):
                message = (
                    f"Offer创建成功。"
                    f"主短链接: {short_link_info.get('final_short_link_url', 'N/A')}。"
                    f"每个渠道使用主短链接 + 参数（offer_id和channel_id）"
                )
        
        logger.info(f"Offer创建成功: id={offer.id}, message={message}")
        return ResponseBaseSchema.success(data=offer_data, message=message)
    except Exception as e:
        await db.rollback()
        logger.error(f"创建Offer失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建Offer失败: {str(e)}"
        )


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[OfferResponse]],
            summary="获取Offer列表")
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
    """获取Offer列表（所有登录用户可访问）"""
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
                "publisher_name": publisher.publisher_name,
                "downstream_cap": assignment.downstream_cap,
                "affiliate_payout": assignment.affiliate_payout
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
            summary="获取Offer详情")
async def get_offer(
    offer_id: int = Path(..., ge=1, description="Offer ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取Offer详情（所有登录用户可访问）"""
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
            "publisher_name": pub.publisher_name,
            "client_id": pub.client_id,  # 添加client_id，用于客户筛选
            "downstream_cap": assignment.downstream_cap,
            "affiliate_payout": assignment.affiliate_payout
        }
        for assignment, pub in assignments
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
    
    # 保存旧的tracklink，用于检测变化
    old_downstream_tracklink = offer.downstream_tracklink
    old_advertiser_tracklink = offer.advertiser_tracklink
    
    # 更新字段
    update_data = offer_in.model_dump(exclude_unset=True, exclude={'publisher_ids', 'publisher_configs'})
    for key, value in update_data.items():
        setattr(offer, key, value)
    
    # 检查advertiser_tracklink是否改变（如果改变，需要重新创建短链接）
    advertiser_tracklink_changed = False
    if 'advertiser_tracklink' in update_data:
        new_advertiser_tracklink = update_data.get('advertiser_tracklink')
        if new_advertiser_tracklink != old_advertiser_tracklink:
            advertiser_tracklink_changed = True
            logger.info(
                f"检测到advertiser_tracklink变化: "
                f"offer_id={offer_id}, "
                f"old={old_advertiser_tracklink}, "
                f"new={new_advertiser_tracklink}"
            )
    
    # 检查downstream_tracklink是否改变
    downstream_tracklink_changed = False
    if 'downstream_tracklink' in update_data:
        new_downstream_tracklink = update_data.get('downstream_tracklink')
        if new_downstream_tracklink != old_downstream_tracklink:
            downstream_tracklink_changed = True
            logger.info(
                f"检测到downstream_tracklink变化: "
                f"offer_id={offer_id}, "
                f"old={old_downstream_tracklink}, "
                f"new={new_downstream_tracklink}"
            )
    
    # 处理渠道分配
    old_publisher_ids = None
    publisher_ids_for_short_link = []
    if 'publisher_configs' in offer_in.model_dump(exclude_unset=True):
        # 使用新的渠道配置方式
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
        if offer_in.publisher_configs is not None:
            # 验证不能为空数组
            if len(offer_in.publisher_configs) == 0:
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="渠道配置不能为空，请至少添加一个渠道"
                )
            
            # 验证是否有重复的publisher_id
            publisher_ids = [config.publisher_id for config in offer_in.publisher_configs]
            if len(publisher_ids) != len(set(publisher_ids)):
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail="渠道配置中存在重复的渠道ID"
                )
            
            for config in offer_in.publisher_configs:
                pub_result = await db.execute(
                    select(Publisher).where(Publisher.id == config.publisher_id)
                )
                publisher = pub_result.scalars().first()
                if not publisher:
                    raise_api_exception(
                        ErrorCode.RESOURCE_NOT_FOUND,
                        detail=f"渠道ID {config.publisher_id} 不存在"
                    )
                
                assignment = OfferPublisherAssignment(
                    offer_id=offer.id,
                    publisher_id=config.publisher_id,
                    downstream_cap=config.downstream_cap,
                    affiliate_payout=config.affiliate_payout,
                    is_active=True
                )
                db.add(assignment)
                publisher_ids_for_short_link.append(config.publisher_id)
    elif 'publisher_ids' in offer_in.model_dump(exclude_unset=True):
        # 向后兼容：使用旧的publisher_ids方式
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
                    publisher_ids_for_short_link.append(pub_id)
    
    try:
        await db.commit()
        
        # 如果advertiser_tracklink改变了，删除该Offer的所有旧短链接（因为原始URL变了）
        if advertiser_tracklink_changed:
            # 删除该Offer的所有短链接（因为tracklink改变了，需要重新生成）
            old_short_links_result = await db.execute(
                select(ShortLink).where(ShortLink.offer_id == offer_id)
            )
            old_short_links = old_short_links_result.scalars().all()
            
            if old_short_links:
                deleted_count = 0
                for old_link in old_short_links:
                    await db.execute(
                        delete(ShortLink).where(ShortLink.id == old_link.id)
                    )
                    deleted_count += 1
                logger.info(
                    f"删除旧的短链接（advertiser_tracklink已改变）: "
                    f"offer_id={offer_id}, "
                    f"deleted_count={deleted_count}, "
                    f"old_advertiser_tracklink={old_advertiser_tracklink}"
                )
                await db.commit()
        
        # 如果渠道分配有变化或advertiser_tracklink改变，同步短链接（使用上游Tracklink作为原始URL）
        short_link_info = None
        need_sync_short_links = False
        
        # 检查是否需要同步短链接
        if 'publisher_configs' in offer_in.model_dump(exclude_unset=True):
            new_publisher_ids = set(publisher_ids_for_short_link)
            if old_publisher_ids != new_publisher_ids:
                need_sync_short_links = True
        elif 'publisher_ids' in offer_in.model_dump(exclude_unset=True):
            new_publisher_ids = set(offer_in.publisher_ids or [])
            if old_publisher_ids != new_publisher_ids:
                need_sync_short_links = True
        elif advertiser_tracklink_changed:
            # advertiser_tracklink改变，需要重新创建短链接
            need_sync_short_links = True
        
        if need_sync_short_links:
            # 获取当前的上游Tracklink（可能是新更新的）
            current_advertiser_tracklink = offer.advertiser_tracklink
            # 获取当前的渠道分配
            if 'publisher_configs' in offer_in.model_dump(exclude_unset=True):
                current_publisher_ids = publisher_ids_for_short_link
            elif 'publisher_ids' in offer_in.model_dump(exclude_unset=True):
                current_publisher_ids = offer_in.publisher_ids
            else:
                # 如果没有明确指定publisher_ids，使用现有的分配
                existing_assignments_result = await db.execute(
                    select(OfferPublisherAssignment).where(OfferPublisherAssignment.offer_id == offer.id)
                )
                existing_assignments = existing_assignments_result.scalars().all()
                current_publisher_ids = [assignment.publisher_id for assignment in existing_assignments]
            
            if current_advertiser_tracklink and current_publisher_ids:
                base_url = settings.TRACKING_BASE_URL
                short_link_info = await sync_short_links_for_offer(
                    db=db,
                    offer_id=offer.id,
                    publisher_ids=current_publisher_ids,
                    offer_name=offer.offer_name,
                    base_url=base_url,
                    current_user_id=current_user.id,
                    advertiser_tracklink=current_advertiser_tracklink
                )
                await db.commit()  # 提交短链接变更
                
                # 刷新offer以获取更新后的downstream_tracklink
                await db.refresh(offer)
            elif not current_advertiser_tracklink:
                logger.warning(f"Offer {offer.id} 没有配置上游Tracklink，无法创建短链接")
        
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
                "publisher_name": pub.publisher_name,
                "downstream_cap": assignment.downstream_cap,
                "affiliate_payout": assignment.affiliate_payout
            }
            for assignment, pub in assignments
        ]
        
        # 构建响应消息，包含短链接信息
        message = "Offer更新成功"
        if short_link_info:
            if short_link_info.get('duplicate'):
                message = (
                    f"Offer更新成功。"
                    f"主短链接已存在: {short_link_info.get('final_short_link_url', 'N/A')}。"
                    f"每个渠道使用主短链接 + 参数（offer_id和channel_id）"
                )
            elif short_link_info.get('created'):
                message = (
                    f"Offer更新成功。"
                    f"已创建主短链接: {short_link_info.get('final_short_link_url', 'N/A')}。"
                    f"每个渠道使用主短链接 + 参数（offer_id和channel_id）"
                )
            elif short_link_info.get('final_short_link_url'):
                message = (
                    f"Offer更新成功。"
                    f"主短链接: {short_link_info.get('final_short_link_url', 'N/A')}。"
                    f"每个渠道使用主短链接 + 参数（offer_id和channel_id）"
                )
        
        if downstream_tracklink_changed:
            message += f" 已删除旧的短链接。"
        
        logger.info(f"Offer更新成功: id={offer.id}, message={message}")
        return ResponseBaseSchema.success(data=offer_data, message=message)
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

