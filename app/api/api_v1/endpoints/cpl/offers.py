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
from app.core.constants import MAX_PAGE_SIZE
from app.core.dependencies import get_offer_service
from app.services.cpl.offer_service import OfferService
from app.models.models import User, UserRole, Offer, Advertiser, Publisher, OfferPublisherAssignment, ShortLink, Client
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
        
        # 验证URL格式，确保以http://或https://开头
        original_url = advertiser_tracklink.strip()
        if not original_url.startswith(('http://', 'https://')):
            logger.error(f"Offer {offer_id} 的上游Tracklink格式无效（必须以http://或https://开头）: {advertiser_tracklink}")
            return None, False
        
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


async def check_and_create_downstream_tracklink_short_link(
    db: AsyncSession,
    offer_id: int,
    downstream_tracklink: str,
    advertiser_tracklink: str,
    offer_name: str,
    base_url: str,
    current_user_id: int
) -> tuple[Optional[ShortLink], bool]:
    """
    检查下游Tracklink是否在short_links表中存在，如果不存在则创建
    注意：创建时使用上游Tracklink（advertiser_tracklink）作为original_url
    
    Args:
        db: 数据库会话
        offer_id: Offer ID
        downstream_tracklink: 下游Tracklink URL（用于检查是否存在）
        advertiser_tracklink: 上游Tracklink URL（用作短链接的original_url）
        offer_name: Offer名称
        base_url: 追踪服务基础URL
        current_user_id: 当前用户ID
        
    Returns:
        (短链接对象, 是否新创建) 元组，如果失败返回 (None, False)
        is_new: True表示新创建的，False表示已存在
    """
    try:
        if not downstream_tracklink:
            logger.warning(f"Offer {offer_id} 没有配置下游Tracklink，跳过检查")
            return None, False
        
        if not advertiser_tracklink:
            logger.warning(f"Offer {offer_id} 没有配置上游Tracklink，无法创建短链接")
            return None, False
        
        # 验证上游Tracklink URL格式，确保以http://或https://开头
        original_url = advertiser_tracklink.strip()
        if not original_url.startswith(('http://', 'https://')):
            logger.warning(f"Offer {offer_id} 的上游Tracklink格式无效（必须以http://或https://开头）: {advertiser_tracklink}")
            return None, False
        
        # 检查是否已存在该Offer的短链接记录（通过offer_id和original_url匹配上游Tracklink）
        existing_result = await db.execute(
            select(ShortLink).where(
                and_(
                    ShortLink.offer_id == offer_id,
                    ShortLink.original_url == original_url,
                    ShortLink.channel_id.is_(None)  # 主短链接的channel_id为NULL
                )
            )
        )
        existing_link = existing_result.scalars().first()
        
        if existing_link:
            # 如果已存在，返回已存在的短链接
            logger.info(
                f"下游Tracklink的短链接已存在: "
                f"offer_id={offer_id}, "
                f"short_code={existing_link.short_code}, "
                f"original_url={original_url}"
            )
            return existing_link, False
        
        # 不存在，创建新的短链接（使用上游Tracklink作为original_url）
        # 使用重试机制处理并发冲突
        max_retries = 3
        for attempt in range(max_retries):
            try:
                short_link = ShortLink(
                    original_url=original_url,  # 使用上游Tracklink作为original_url
                    title=f"{offer_name} - 下游Tracklink短链接",
                    description=f"Offer: {offer_name} 的下游Tracklink短链接（原始URL使用上游Tracklink）",
                    offer_id=offer_id,
                    channel_id=None,  # 下游Tracklink短链接不关联特定渠道
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
                        logger.error(f"生成下游Tracklink短链接代码失败: offer_id={offer_id}")
                        await db.rollback()
                        return None, False
                    short_link.short_code = unique_code
                
                # 尝试flush，如果发生唯一约束冲突，会在commit时抛出IntegrityError
                # 注意：这里不commit，让外层函数commit，避免事务嵌套问题
                await db.flush()
                
                logger.info(
                    f"为下游Tracklink创建短链接成功: "
                    f"short_link_id={short_link.id}, "
                    f"short_code={short_link.short_code}, "
                    f"offer_id={short_link.offer_id}, "
                    f"original_url={original_url} (使用上游Tracklink)"
                )
                return short_link, True  # 新创建的
                
            except Exception as e:
                # 检查是否是唯一约束冲突（并发冲突）
                error_msg = str(e)
                is_integrity_error = (
                    "IntegrityError" in str(type(e)) or
                    "Duplicate entry" in error_msg or
                    "UNIQUE constraint" in error_msg or
                    "unique constraint" in error_msg.lower() or
                    "duplicate key" in error_msg.lower()
                )
                
                if is_integrity_error and attempt < max_retries - 1:
                    # 回滚当前事务
                    await db.rollback()
                    logger.warning(
                        f"短链接代码冲突（并发冲突），重试中: "
                        f"offer_id={offer_id}, "
                        f"attempt={attempt + 1}/{max_retries}, "
                        f"error={error_msg[:200]}"
                    )
                    # 重新检查是否已存在（可能另一个请求已经创建了）
                    existing_result = await db.execute(
                        select(ShortLink).where(
                            and_(
                                ShortLink.offer_id == offer_id,
                                ShortLink.original_url == original_url,
                                ShortLink.channel_id.is_(None)
                            )
                        )
                    )
                    existing_link = existing_result.scalars().first()
                    if existing_link:
                        # 另一个请求已经创建了，返回已存在的短链接
                        logger.info(
                            f"检测到并发创建，使用已存在的短链接: "
                            f"offer_id={offer_id}, "
                            f"short_code={existing_link.short_code}"
                        )
                        return existing_link, False
                    # 继续重试
                    continue
                else:
                    # 其他错误或重试次数用尽，记录错误并返回失败
                    await db.rollback()
                    if is_integrity_error:
                        logger.error(
                            f"短链接代码冲突，重试次数用尽: "
                            f"offer_id={offer_id}, "
                            f"error={error_msg[:200]}"
                        )
                    raise  # 重新抛出异常，让外层处理
        
    except Exception as e:
        logger.error(f"检查并创建下游Tracklink短链接失败: offer_id={offer_id}, error={str(e)}", exc_info=True)
        return None, False


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
    """创建Offer（已重构使用服务层）"""
    # 使用服务层（业务逻辑在OfferService中）
    offer_service: OfferService = await get_offer_service(db)
    
    # 准备Offer数据（包含渠道配置）
    offer_data = offer_in.model_dump()
    if offer_in.publisher_configs is not None:
        # 将Pydantic对象转换为字典
        offer_data['publisher_configs'] = [config.model_dump() if hasattr(config, 'model_dump') else config for config in offer_in.publisher_configs]
    
    # 调用服务层创建Offer（服务层会处理渠道分配和短链接创建）
    offer, short_link_info = await offer_service.create_offer(offer_data, current_user)
    
    # 重新加载以获取广告主信息
    offer = await offer_service.get_offer_by_id(offer.id, current_user, include_advertiser=True, include_assignments=False)
    
    # 构建响应数据
    offer_response = OfferResponse.model_validate(offer)
    offer_response.advertiser_name = offer.advertiser.advertiser_name if offer.advertiser else None
    
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
    return ResponseBaseSchema.success(data=offer_response, message=message)


@router.get("/",
            response_model=PaginatedResponseBaseSchema[list[OfferResponse]],
            summary="获取Offer列表")
async def get_offers(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    search: Optional[str] = Query(None, description="搜索关键词（名称、ID）"),
    advertiser_id: Optional[int] = Query(None, description="广告主ID过滤"),
    status: Optional[str] = Query(None, description="状态过滤"),
    country: Optional[str] = Query(None, description="国家过滤"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取Offer列表（已重构使用服务层，批量加载关联数据）"""
    # 使用服务层（业务逻辑在OfferService中，已优化批量加载）
    offer_service: OfferService = await get_offer_service(db)
    offers, total, assignments_map = await offer_service.get_offers(
        current_user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        advertiser_id=advertiser_id,
        status=status,
        country=country,
        is_active=is_active
    )
    
    # 构建响应数据（广告主信息已通过joinedload预加载，渠道分配已批量加载）
    offer_list = []
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


@router.get("/{offer_id}/check-short-link",
            response_model=ResponseBaseSchema[dict],
            summary="检查Offer的短链接是否存在")
async def check_offer_short_link(
    offer_id: int = Path(..., ge=1, description="Offer ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    检查Offer的短链接是否存在
    检查条件：下游Tracklink在short_links表中存在，并且original_url等于上游Tracklink
    """
    result = await db.execute(
        select(Offer).where(Offer.id == offer_id)
    )
    offer = result.scalars().first()
    
    if not offer:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"Offer ID {offer_id} 不存在"
        )
    
    # 如果没有下游Tracklink或上游Tracklink，返回不存在
    if not offer.downstream_tracklink or not offer.advertiser_tracklink:
        return ResponseBaseSchema.success(data={"exists": False, "short_link": None})
    
    # 验证上游Tracklink URL格式
    original_url = offer.advertiser_tracklink.strip()
    if not original_url.startswith(('http://', 'https://')):
        return ResponseBaseSchema.success(data={"exists": False, "short_link": None})
    
    # 检查是否已存在该Offer的短链接记录（通过offer_id和original_url匹配上游Tracklink）
    existing_result = await db.execute(
        select(ShortLink).where(
            and_(
                ShortLink.offer_id == offer_id,
                ShortLink.original_url == original_url,
                ShortLink.channel_id.is_(None)  # 主短链接的channel_id为NULL
            )
        )
    )
    existing_link = existing_result.scalars().first()
    
    if existing_link:
        # 生成短链接URL
        base_url = settings.TRACKING_BASE_URL
        short_link_url = get_short_link_url(base_url, existing_link.short_code)
        
        # 如果找到了短链接记录（offer_id和original_url匹配），就认为短链接已存在
        # 不需要检查downstream_tracklink是否等于短链接URL，因为：
        # 1. 短链接可能已创建，但downstream_tracklink可能还没有更新
        # 2. 用户要求是检查"下游Tracklink在short_links表中存在，并且original_url等于上游Tracklink"
        return ResponseBaseSchema.success(data={
            "exists": True,
            "short_link": {
                "id": existing_link.id,
                "short_code": existing_link.short_code,
                "short_url": short_link_url,
                "original_url": existing_link.original_url
            }
        })
    
    return ResponseBaseSchema.success(data={"exists": False, "short_link": None})


@router.get("/{offer_id}",
            response_model=ResponseBaseSchema[OfferResponse],
            summary="获取Offer详情")
async def get_offer(
    offer_id: int = Path(..., ge=1, description="Offer ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取Offer详情（已重构使用服务层，权限检查和数据加载都在服务层）"""
    # 使用服务层（业务逻辑在OfferService中，包含权限检查）
    offer_service: OfferService = await get_offer_service(db)
    
    # 获取Offer（服务层会处理权限检查和关联数据加载）
    offer = await offer_service.get_offer_by_id(offer_id, current_user, include_advertiser=True, include_assignments=False)
    
    # 获取渠道分配列表（服务层会处理权限过滤）
    assignments = await offer_service.get_offer_assignments(offer_id, current_user)
    
    offer_data = OfferResponse.model_validate(offer)
    # 从已加载的关联中获取广告主名称
    offer_data.advertiser_name = offer.advertiser.advertiser_name if offer.advertiser else None
    offer_data.assigned_publishers = assignments
    
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
    """更新Offer（已重构使用服务层）"""
    # 使用服务层（业务逻辑在OfferService中）
    offer_service: OfferService = await get_offer_service(db)
    
    # 准备更新数据（包含渠道配置）
    update_data = offer_in.model_dump(exclude_unset=True, exclude={'publisher_ids', 'publisher_configs'})
    if offer_in.publisher_configs is not None:
        # 将Pydantic对象转换为字典
        update_data['publisher_configs'] = [config.model_dump() if hasattr(config, 'model_dump') else config for config in offer_in.publisher_configs]
    elif offer_in.publisher_ids is not None:
        update_data['publisher_ids'] = offer_in.publisher_ids
    
    # 调用服务层更新Offer（服务层会处理渠道分配、短链接同步等）
    offer, short_link_info, downstream_tracklink_short_link_info, downstream_tracklink_changed = await offer_service.update_offer(
        offer_id, update_data, current_user
    )
    
    # 重新加载关联信息（使用服务层方法）
    offer = await offer_service.get_offer_by_id(offer.id, current_user, include_advertiser=True, include_assignments=False)
    
    # 获取渠道分配列表（使用服务层方法，包含权限过滤）
    assignments = await offer_service.get_offer_assignments(offer.id, current_user)
    
    offer_data = OfferResponse.model_validate(offer)
    offer_data.advertiser_name = offer.advertiser.advertiser_name if offer.advertiser else None
    offer_data.assigned_publishers = assignments
    
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
    
    # 添加下游Tracklink短链接信息
    if downstream_tracklink_short_link_info:
        if downstream_tracklink_short_link_info['is_new']:
            message += f" 已为下游Tracklink创建短链接: {downstream_tracklink_short_link_info['short_link_url']}。"
        else:
            message += f" 下游Tracklink短链接已存在: {downstream_tracklink_short_link_info['short_link_url']}。"
    
    logger.info(f"Offer更新成功: id={offer.id}, message={message}")
    return ResponseBaseSchema.success(data=offer_data, message=message)


@router.delete("/{offer_id}",
               response_model=ResponseBaseSchema[dict],
               summary="删除Offer",
               dependencies=[Depends(require_admin)])
async def delete_offer(
    offer_id: int = Path(..., ge=1, description="Offer ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除Offer（已重构使用服务层）"""
    # 使用服务层（业务逻辑在OfferService中）
    offer_service: OfferService = await get_offer_service(db)
    
    # 调用服务层删除Offer（服务层会检查关联数据、记录审计日志）
    await offer_service.delete_offer(offer_id, current_user)
    
    return ResponseBaseSchema.success(data={"message": "Offer已删除"})

