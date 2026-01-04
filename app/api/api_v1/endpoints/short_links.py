"""
短链接服务API端点
提供短链接的生成、重定向、管理功能
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Path, Request, HTTPException, BackgroundTasks
from app.core.utils import get_app_now_naive
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.constants import MAX_PAGE_SIZE
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.short_link.generator import (
    generate_short_code,
    generate_short_code_from_id,
    generate_unique_short_code
)
from app.core.tracking.click_id_generator import generate_click_id_from_timestamp
from app.models.models import User, UserRole, ShortLink, Offer, Publisher, Click
from app.schemas.short_link import (
    ShortLinkCreate,
    ShortLinkUpdate,
    ShortLinkResponse,
    ShortLinkListResponse,
    ShortLinkStatsResponse
)
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema

# 创建路由实例
router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== 短链接工具接口（必须在动态路径之前） ====================

@router.get("/generate-code",
            summary="生成短链接代码")
async def generate_short_code(
    db: AsyncSession = Depends(get_db)
):
    """生成唯一的短链接代码（公开接口，用于前端自动生成）"""
    from app.core.short_link.generator import generate_short_code, generate_unique_short_code
    
    # 获取所有已存在的代码
    result = await db.execute(select(ShortLink.short_code))
    existing_codes = {row[0] for row in result.all()}
    
    # 初始长度为6位
    length = 6
    max_length = 20  # 最大长度限制
    consecutive_failures = 0
    max_consecutive_failures = 5  # 连续5次失败后增加位数
    
    # 尝试生成唯一代码
    while length <= max_length:
        # 每次尝试最多100次
        code = generate_unique_short_code(existing_codes, length=length, max_attempts=100)
        
        if code:
            # 生成成功
            logger.info(f"成功生成短链接代码: {code} (长度: {length})")
            return ResponseBaseSchema.success(data={"short_code": code})
        
        # 生成失败，记录连续失败次数
        consecutive_failures += 1
        logger.warning(f"生成短链接代码失败 (长度: {length}, 连续失败: {consecutive_failures})")
        
        # 如果连续失败5次，增加位数
        if consecutive_failures >= max_consecutive_failures:
            length += 1
            consecutive_failures = 0  # 重置计数器
            logger.info(f"增加短链接代码长度到 {length} 位")
            
            # 如果达到最大长度，停止尝试
            if length > max_length:
                break
    
    # 所有尝试都失败
    raise_api_exception(
        ErrorCode.OPERATION_FAILED,
        detail="生成短链接代码失败，请稍后重试"
    )


@router.get("/check-code/{short_code}",
            summary="检查短链接代码是否存在")
async def check_short_code(
    short_code: str = Path(..., description="短链接代码"),
    db: AsyncSession = Depends(get_db)
):
    """检查短链接代码是否存在（公开接口，用于前端验证）"""
    result = await db.execute(
        select(ShortLink).where(ShortLink.short_code == short_code)
    )
    exists = result.scalars().first() is not None
    
    return ResponseBaseSchema.success(data={"exists": exists, "short_code": short_code})


# ==================== 短链接重定向 ====================

@router.get("/{short_code}", 
            summary="短链接重定向",
            deprecated=True,
            description="⚠️ 已废弃：推荐使用 `/s/{short_code}` 路由（带缓存优化，性能更好）")
async def redirect_short_link(
    short_code: str = Path(..., description="短链接代码"),
    offer_id: Optional[int] = Query(None, description="Offer ID（从URL参数获取）"),
    channel_id: Optional[int] = Query(None, description="渠道ID（从URL参数获取）"),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """
    短链接重定向（公开接口，无需认证）
    
    ⚠️ **已废弃**：此路由已废弃，推荐使用 `/s/{short_code}` 路由
    
    推荐路由：`/s/{short_code}`
    - 使用Redis缓存优化，减少数据库查询
    - 支持查询参数自动合并到原始URL
    - 性能更好，适合高并发场景
    
    此路由保留仅用于向后兼容，新项目请使用 `/s/{short_code}`
    
    功能说明：
    - 访问短链接时自动重定向到原始URL
    - 从URL参数中提取offer_id和channel_id并保存到点击记录
    """
    # 查询短链接
    result = await db.execute(
        select(ShortLink).where(ShortLink.short_code == short_code)
    )
    short_link = result.scalars().first()
    
    if not short_link:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"短链接不存在: {short_code}"
        )
    
    # 检查是否激活
    if not short_link.is_active:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail="短链接已禁用"
        )
    
    # 检查是否过期（expires_at 存储的是北京时间 naive）
    if short_link.expires_at:
        expires_at = short_link.expires_at
        # 如果带时区信息，转换为北京时间（naive）
        if expires_at.tzinfo is not None:
            from app.core.utils import APP_TIMEZONE
            expires_at = expires_at.astimezone(APP_TIMEZONE).replace(tzinfo=None)
        
        now = get_app_now_naive()  # 使用北京时间比较
        if expires_at < now:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="短链接已过期"
            )
    
    # 只使用URL参数中的offer_id和channel_id（如果有的话）
    # 如果URL参数中没有，则不保存这些值
    final_channel_id = channel_id  # 只使用URL参数
    
    # 如果从URL参数获取了offer_id，需要转换为数据库主键ID
    # URL参数中的offer_id可能是主键ID，也可能是上游Offer ID
    final_offer_id = None
    advertiser_id = None
    if offer_id:
        try:
            # 1. 先尝试作为主键ID查询
            offer_result = await db.execute(
                select(Offer).where(Offer.id == offer_id)
            )
            offer = offer_result.scalars().first()
            
            # 2. 如果找不到，尝试作为上游Offer ID查询
            if not offer:
                offer_result = await db.execute(
                    select(Offer).where(Offer.advertiser_offer_id == str(offer_id))
                )
                offer = offer_result.scalars().first()
                if offer:
                    logger.info(
                        f"[短链接点击] URL参数中的offer_id={offer_id} 是上游Offer ID，"
                        f"已转换为数据库主键ID={offer.id}"
                    )
            
            # 3. 如果找到了Offer，使用主键ID
            if offer:
                final_offer_id = offer.id  # 使用数据库主键ID
                advertiser_id = offer.advertiser_id
                # 缓存Offer信息（使用主键ID作为key）
                from app.core.offer_cache import set_offer_cache
                await set_offer_cache(final_offer_id, advertiser_id, offer.offer_name)
                logger.info(
                    f"[短链接点击] Offer信息: "
                    f"数据库主键ID={final_offer_id}, "
                    f"offer_name={offer.offer_name}, "
                    f"advertiser_id={advertiser_id}"
                )
            else:
                logger.warning(
                    f"[短链接点击] URL参数中的offer_id={offer_id} 无效"
                    f"（既不是主键ID，也不是上游Offer ID），short_code={short_code}"
                )
        except Exception as e:
            logger.warning(f"查询Offer失败: offer_id={offer_id}, error={e}")
    
    # 打印获得的参数
    logger.info(
        f"[短链接点击] 参数信息: "
        f"short_code={short_code}, "
        f"URL参数_offer_id={offer_id}, "
        f"URL参数_channel_id={channel_id}, "
        f"最终保存_offer_id={final_offer_id}, "
        f"最终保存_channel_id={final_channel_id}"
    )
    
    # 收集完整的请求信息（包括软件、硬件信息和URL参数）
    from app.core.device_info import collect_request_info
    request_info = collect_request_info(request) if request else {}
    
    # 打印客户端信息
    logger.info(
        f"[短链接点击] 客户端信息: "
        f"ip={request_info.get('ip')}, "
        f"user_agent={request_info.get('user_agent')}, "
        f"referer={request_info.get('referer')}, "
        f"os={request_info.get('os')}, "
        f"browser={request_info.get('browser')}, "
        f"device_type={request_info.get('device_type')}"
    )
    
    # 生成Click ID
    click_id = generate_click_id_from_timestamp()
    
    # 创建点击记录（使用Redis队列，高并发优化）
    click_data = {
        "click_id": click_id,
        "short_link_id": short_link.id,
        "offer_id": final_offer_id,
        "publisher_id": final_channel_id,  # publisher_id对应channel_id
        "advertiser_id": advertiser_id,  # 可能为None，批量处理时会补充
        "click_time": get_app_now_naive().isoformat(),  # 使用北京时间
        "ip": request_info.get('ip'),
        "user_agent": request_info.get('user_agent'),
        "referer": request_info.get('referer'),
        "country": None,
        # 软件信息
        "os": request_info.get('os'),
        "os_version": request_info.get('os_version'),
        "browser": request_info.get('browser'),
        "browser_version": request_info.get('browser_version'),
        "accept_language": request_info.get('accept_language'),
        "accept_encoding": request_info.get('accept_encoding'),
        "is_bot": request_info.get('is_bot', False),
        # 硬件信息
        "device_type": request_info.get('device_type'),
        "device_brand": request_info.get('device_brand'),
        "device_model": request_info.get('device_model'),
        # URL参数和请求头
        "url_params": request_info.get('url_params'),
        "all_headers": request_info.get('all_headers'),
        # 兼容旧字段
        "device": request_info.get('device_type')  # 使用device_type作为device字段的值
    }
    
    # 使用Redis队列缓冲（非阻塞，高并发优化）
    from app.core.clicks_queue import enqueue_click
    enqueued = await enqueue_click(click_data)
    
    if enqueued:
        logger.debug(
            f"[短链接点击] 点击记录已加入队列: "
            f"click_id={click_id}, "
            f"short_code={short_code}, "
            f"offer_id={final_offer_id}, "
            f"publisher_id={final_channel_id}"
        )
    else:
        # 队列失败，降级到后台任务（兼容性）
        logger.warning(f"Redis队列不可用，降级到后台任务: click_id={click_id}")
        if background_tasks:
            from app.api.api_v1.endpoints.tracking import create_click_background
            # 转换时间格式（使用北京时间）
            click_data['click_time'] = get_app_now_naive()
            background_tasks.add_task(create_click_background, click_data)
    
    # 异步更新点击次数（使用Redis计数器，不阻塞重定向）
    try:
        from app.core.short_link_click_counter import increment_click_count_async
        await increment_click_count_async(short_code)
        logger.debug(f"短链接点击计数已记录: short_code={short_code}")
    except Exception as e:
        logger.warning(f"更新短链接点击次数失败: short_code={short_code}, error={str(e)}")
        # 点击次数更新失败不影响重定向
    
    # 重定向到原始URL
    return RedirectResponse(url=short_link.original_url, status_code=302)


# ==================== 短链接管理 ====================

@router.post("/", 
             response_model=ResponseBaseSchema[ShortLinkResponse],
             summary="创建短链接")
async def create_short_link(
    request: Request,
    link_in: ShortLinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建短链接"""
    # 如果提供了自定义短链接代码，检查是否已存在
    if link_in.short_code:
        result = await db.execute(
            select(ShortLink).where(ShortLink.short_code == link_in.short_code)
        )
        existing = result.scalars().first()
        if existing:
            raise_api_exception(
                ErrorCode.RESOURCE_ALREADY_EXISTS,
                detail=f"短链接代码 '{link_in.short_code}' 已存在，请使用其他代码"
            )
        short_code = link_in.short_code
    else:
        # 自动生成短链接代码
        # 先尝试从ID生成（需要先插入获取ID）
        # 如果失败，使用随机生成
        short_code = None
    
    # 验证 Offer 是否存在（如果提供了 offer_id）
    if link_in.offer_id:
        offer_result = await db.execute(
            select(Offer).where(Offer.id == link_in.offer_id)
        )
        offer = offer_result.scalars().first()
        if not offer:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Offer ID {link_in.offer_id} 不存在"
            )
    
    # 验证渠道是否存在（如果提供了 channel_id）
    if link_in.channel_id:
        channel_result = await db.execute(
            select(Publisher).where(Publisher.id == link_in.channel_id)
        )
        channel = channel_result.scalars().first()
        if not channel:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"渠道ID {link_in.channel_id} 不存在"
            )
    
    # 创建短链接
    short_link = ShortLink(
        original_url=link_in.original_url,
        title=link_in.title,
        description=link_in.description,
        short_code=short_code or "temp",  # 临时代码，稍后更新
        created_by=current_user.id,
        offer_id=link_in.offer_id,
        channel_id=link_in.channel_id,
        is_active=link_in.is_active,
        expires_at=link_in.expires_at,
        click_count=0
    )
    
    try:
        db.add(short_link)
        await db.flush()  # 先flush以获取ID
        
        # 如果没有提供自定义代码，生成唯一代码
        if not link_in.short_code:
            # 获取所有已存在的代码
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
                    raise_api_exception(
                        ErrorCode.OPERATION_FAILED,
                        detail="生成短链接代码失败，请稍后重试"
                    )
                short_link.short_code = unique_code
        
        # 注意：不需要手动提交事务，get_db 依赖会自动处理
        # 刷新对象以获取最新数据（在自动提交之前）
        await db.flush()
        await db.refresh(short_link)
        
        # 构建完整的短链接URL
        base_url = str(request.base_url).rstrip('/')
        short_url = f"{base_url}/s/{short_link.short_code}"
        
        response_data = ShortLinkResponse.model_validate(short_link)
        response_data.short_url = short_url
        
        logger.info(f"短链接创建成功: {short_link.short_code} -> {short_link.original_url}")
        return ResponseBaseSchema.success(data=response_data)
        
    except Exception as e:
        # 注意：不需要手动回滚事务，get_db 依赖会自动处理
        logger.error(f"创建短链接失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"创建短链接失败: {str(e)}"
        )


@router.get("/", 
            response_model=PaginatedResponseBaseSchema[list[ShortLinkResponse]],
            summary="获取短链接列表")
async def get_short_links(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    search: Optional[str] = Query(None, description="搜索关键词（标题、URL、代码）"),
    is_active: Optional[bool] = Query(None, description="是否激活过滤"),
    created_by: Optional[int] = Query(None, description="创建者ID过滤"),
    offer_id: Optional[int] = Query(None, description="Offer ID过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取短链接列表"""
    # 权限检查：管理员可以查看所有，普通用户只能查看自己的
    query = select(ShortLink)
    
    if current_user.role != UserRole.ADMIN:
        query = query.where(ShortLink.created_by == current_user.id)
    
    # 应用过滤条件
    conditions = []
    
    if is_active is not None:
        conditions.append(ShortLink.is_active == is_active)
    
    if created_by:
        conditions.append(ShortLink.created_by == created_by)
    
    if offer_id:
        conditions.append(ShortLink.offer_id == offer_id)
    
    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                ShortLink.title.like(search_pattern),
                ShortLink.original_url.like(search_pattern),
                ShortLink.short_code.like(search_pattern),
                ShortLink.description.like(search_pattern)
            )
        )
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # 排序：最新的在前
    query = query.order_by(ShortLink.created_at.desc())
    
    # 计算总数（在加载关联之前）
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    # 执行查询，加载创建者和渠道信息（在分页之后）
    from sqlalchemy.orm import joinedload
    query = query.options(joinedload(ShortLink.creator), joinedload(ShortLink.channel))
    result = await db.execute(query)
    short_links = result.scalars().all()
    
    # 构建完整的短链接URL
    base_url = str(request.base_url).rstrip('/')
    links_data = []
    for link in short_links:
        link_data = ShortLinkResponse.model_validate(link)
        link_data.short_url = f"{base_url}/s/{link.short_code}"
        # 添加创建者名称
        if link.creator:
            link_data.creator_name = link.creator.username
        # 添加渠道名称
        if link.channel:
            link_data.channel_name = link.channel.publisher_name
        links_data.append(link_data)
    
    return PaginatedResponseBaseSchema.success(
        data=links_data,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{link_id}/detail",
            response_model=ResponseBaseSchema[ShortLinkResponse],
            summary="获取短链接详情")
async def get_short_link_detail(
    request: Request,
    link_id: int = Path(..., ge=1, description="短链接ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取短链接详情"""
    from sqlalchemy.orm import joinedload
    result = await db.execute(
        select(ShortLink)
        .where(ShortLink.id == link_id)
        .options(joinedload(ShortLink.creator), joinedload(ShortLink.channel))
    )
    short_link = result.scalars().first()
    
    if not short_link:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"短链接ID {link_id} 不存在"
        )
    
    # 权限检查
    if current_user.role != UserRole.ADMIN:
        if short_link.created_by != current_user.id:
            raise_api_exception(
                ErrorCode.ACCESS_DENIED,
                detail="无权访问该短链接"
            )
    
    # 构建完整的短链接URL
    base_url = str(request.base_url).rstrip('/')
    response_data = ShortLinkResponse.model_validate(short_link)
    response_data.short_url = f"{base_url}/s/{short_link.short_code}"
    # 添加创建者名称
    if short_link.creator:
        response_data.creator_name = short_link.creator.username
    # 添加渠道名称
    if short_link.channel:
        response_data.channel_name = short_link.channel.publisher_name
    
    return ResponseBaseSchema.success(data=response_data)


@router.put("/{link_id}",
            response_model=ResponseBaseSchema[ShortLinkResponse],
            summary="更新短链接")
async def update_short_link(
    request: Request,
    link_id: int = Path(..., ge=1, description="短链接ID"),
    link_in: ShortLinkUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新短链接"""
    from sqlalchemy.orm import joinedload
    result = await db.execute(
        select(ShortLink)
        .where(ShortLink.id == link_id)
        .options(joinedload(ShortLink.channel))
    )
    short_link = result.scalars().first()
    
    if not short_link:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"短链接ID {link_id} 不存在"
        )
    
    # 权限检查
    if current_user.role != UserRole.ADMIN:
        if short_link.created_by != current_user.id:
            raise_api_exception(
                ErrorCode.ACCESS_DENIED,
                detail="无权修改该短链接"
            )
    
    # 验证 Offer 是否存在（如果提供了 offer_id）
    update_data = link_in.model_dump(exclude_unset=True)
    if 'offer_id' in update_data and update_data['offer_id'] is not None:
        offer_result = await db.execute(
            select(Offer).where(Offer.id == update_data['offer_id'])
        )
        offer = offer_result.scalars().first()
        if not offer:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"Offer ID {update_data['offer_id']} 不存在"
            )
    
    # 验证渠道是否存在（如果提供了 channel_id）
    if 'channel_id' in update_data and update_data['channel_id'] is not None:
        channel_result = await db.execute(
            select(Publisher).where(Publisher.id == update_data['channel_id'])
        )
        channel = channel_result.scalars().first()
        if not channel:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail=f"渠道ID {update_data['channel_id']} 不存在"
            )
    
    # 更新字段
    for key, value in update_data.items():
        setattr(short_link, key, value)
    
    try:
        # 注意：不需要手动提交事务，get_db 依赖会自动处理
        # 刷新对象以获取最新数据（在自动提交之前）
        await db.flush()
        await db.refresh(short_link)
        
        # 构建完整的短链接URL
        base_url = str(request.base_url).rstrip('/')
        response_data = ShortLinkResponse.model_validate(short_link)
        response_data.short_url = f"{base_url}/s/{short_link.short_code}"
        # 添加渠道名称
        if short_link.channel:
            response_data.channel_name = short_link.channel.publisher_name
        
        # 清除缓存，确保数据一致性
        from app.core.short_link_cache import invalidate_short_link_cache
        await invalidate_short_link_cache(short_link.short_code)
        
        logger.info(f"短链接更新成功: {short_link.short_code}")
        return ResponseBaseSchema.success(data=response_data)
        
    except Exception as e:
        # 注意：不需要手动回滚事务，get_db 依赖会自动处理
        logger.error(f"更新短链接失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新短链接失败: {str(e)}"
        )


@router.delete("/{link_id}",
                response_model=ResponseBaseSchema[dict],
                summary="删除短链接")
async def delete_short_link(
    link_id: int = Path(..., ge=1, description="短链接ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除短链接"""
    result = await db.execute(
        select(ShortLink).where(ShortLink.id == link_id)
    )
    short_link = result.scalars().first()
    
    if not short_link:
        raise_api_exception(
            ErrorCode.RESOURCE_NOT_FOUND,
            detail=f"短链接ID {link_id} 不存在"
        )
    
    # 权限检查
    if current_user.role != UserRole.ADMIN:
        if short_link.created_by != current_user.id:
            raise_api_exception(
                ErrorCode.ACCESS_DENIED,
                detail="无权删除该短链接"
            )
    
    short_code = short_link.short_code
    
    try:
        from sqlalchemy import delete
        await db.execute(delete(ShortLink).where(ShortLink.id == link_id))
        # 注意：不需要手动提交事务，get_db 依赖会自动处理
        
        # 清除缓存，确保数据一致性
        from app.core.short_link_cache import invalidate_short_link_cache
        await invalidate_short_link_cache(short_code)
        
        logger.info(f"短链接删除成功: {link_id}")
        return ResponseBaseSchema.success(data={"message": "短链接已删除"})
    except Exception as e:
        # 注意：不需要手动回滚事务，get_db 依赖会自动处理
        logger.error(f"删除短链接失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"删除短链接失败: {str(e)}"
        )


@router.get("/stats/summary",
            response_model=ResponseBaseSchema[ShortLinkStatsResponse],
            summary="获取短链接统计")
async def get_short_link_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取短链接统计信息"""
    # 构建基础查询条件
    base_conditions = []
    if current_user.role != UserRole.ADMIN:
        # 普通用户只能查看自己的统计
        base_conditions.append(ShortLink.created_by == current_user.id)
    
    # 计算总数
    total_query = select(func.count(ShortLink.id))
    if base_conditions:
        total_query = total_query.where(and_(*base_conditions))
    total_result = await db.execute(total_query)
    total_links = total_result.scalar() or 0
    
    # 计算总点击次数
    click_query = select(func.sum(ShortLink.click_count))
    if base_conditions:
        click_query = click_query.where(and_(*base_conditions))
    click_result = await db.execute(click_query)
    total_clicks = click_result.scalar() or 0
    # 确保 total_clicks 是整数
    if total_clicks is None:
        total_clicks = 0
    else:
        total_clicks = int(total_clicks)
    
    # 计算激活数量
    active_conditions = base_conditions + [ShortLink.is_active == True]
    active_query = select(func.count(ShortLink.id)).where(and_(*active_conditions))
    active_result = await db.execute(active_query)
    active_links = active_result.scalar() or 0
    
    # 计算过期数量（expires_at 存储的是北京时间，使用北京时间比较）
    now = get_app_now_naive()
    expired_conditions = base_conditions + [
        ShortLink.expires_at.isnot(None),
        ShortLink.expires_at < now
    ]
    expired_query = select(func.count(ShortLink.id)).where(and_(*expired_conditions))
    expired_result = await db.execute(expired_query)
    expired_links = expired_result.scalar() or 0
    
    return ResponseBaseSchema.success(data=ShortLinkStatsResponse(
        total_links=total_links,
        total_clicks=total_clicks,
        active_links=active_links,
        expired_links=expired_links
    ))


@router.post("/sync-clicks",
             response_model=ResponseBaseSchema,
             summary="手动同步点击次数到数据库（管理员）")
async def sync_short_link_clicks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    手动触发短链接点击次数同步
    将Redis中的点击次数同步到数据库
    
    注意：此接口需要管理员权限
    """
    from app.core.short_link_click_counter import sync_click_counts_to_db
    
    try:
        logger.info(f"管理员 {current_user.id} 手动触发短链接点击次数同步")
        synced_count = await sync_click_counts_to_db(db)
        
        if synced_count > 0:
            logger.info(f"手动同步成功: 更新了 {synced_count} 条记录")
            return ResponseBaseSchema.success(
                data={"synced_count": synced_count, "message": f"成功同步 {synced_count} 个短链接的点击次数"}
            )
        else:
            return ResponseBaseSchema.success(
                data={"synced_count": 0, "message": "没有需要同步的点击次数"}
            )
    except Exception as e:
        logger.error(f"手动同步短链接点击次数失败: {str(e)}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"同步点击次数失败: {str(e)}"
        )


@router.get("/click-stats",
            response_model=ResponseBaseSchema,
            summary="检查点击计数系统状态（管理员）")
async def check_click_count_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    检查短链接点击计数系统的状态
    包括Redis计数器、进程内计数器和数据库中的点击次数
    
    注意：此接口需要管理员权限
    """
    from app.core.short_link_click_counter import CLICK_COUNTER_PREFIX, _click_counters
    from app.core.redis_client import get_redis_client
    
    stats = {
        "redis_available": False,
        "redis_counters": 0,
        "redis_counter_details": [],
        "memory_counters": len(_click_counters),
        "memory_counter_details": list(_click_counters.items()) if _click_counters else [],
        "database_total_clicks": 0,
    }
    
    # 检查Redis状态
    redis = await get_redis_client()
    if redis:
        stats["redis_available"] = True
        try:
            # 获取所有计数器键
            pattern = f"{CLICK_COUNTER_PREFIX}*"
            keys = await redis.keys(pattern)
            stats["redis_counters"] = len(keys)
            
            # 获取每个计数器的详细信息
            for key in keys[:20]:  # 最多显示20个
                short_code = key.replace(CLICK_COUNTER_PREFIX, "")
                count = await redis.get(key)
                count_value = int(count) if count else 0
                stats["redis_counter_details"].append({
                    "short_code": short_code,
                    "count": count_value,
                    "key": key
                })
        except Exception as e:
            stats["redis_error"] = str(e)
    
    # 获取数据库中的总点击次数
    try:
        result = await db.execute(select(func.sum(ShortLink.click_count)))
        total_clicks = result.scalar() or 0
        stats["database_total_clicks"] = int(total_clicks)
    except Exception as e:
        stats["database_error"] = str(e)
    
    return ResponseBaseSchema.success(data=stats)
