"""短链接服务 API

职责：短码生成、302 跳转、点击计数同步、Offer/渠道关联与斗篷桥页配置。

权限：
- GET /{short_code} 跳转：公开（记录点击）
- CRUD 与管理接口：需登录；部分操作需管理员

主要端点（前缀 /short-links）：
- POST   /              创建短链接
- GET    /              分页列表
- GET    /{id}          详情
- PUT    /{id}          更新
- DELETE /{id}          删除
- GET    /{short_code}  公开跳转。

说明：点击追踪与短链接服务，记录访问并对接斗篷跳转。"""
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Path, Request, HTTPException, BackgroundTasks, Body
from app.core.utils import get_app_now_naive
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_

from app.core.audit_log import log_create, log_update, log_delete, log_user_action, commit_audit_log
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.constants import MAX_PAGE_SIZE
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.dependencies import get_short_link_service
from app.services.short_link_service import ShortLinkService
from app.core.short_link.generator import (
    generate_short_code,
    generate_short_code_from_id,
    generate_unique_short_code
)
from app.core.short_link_click_counter import (
    sync_click_counts_to_db, 
    CLICK_COUNTER_PREFIX, 
    get_click_counter_stats,
    get_deadlock_stats
)
from app.core.redis_client import get_redis_client
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
    """
    生成唯一短链接代码。

    权限：登录用户；供前端表单自动生成 short_code。
    """
    # ---------- 入口：参数与依赖准备 ----------
    
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
        
        # ---------- 条件分支 ----------
        if code:
            # 生成成功
            logger.info(f"成功生成短链接代码: {code} (长度: {length})")
            return ResponseBaseSchema.success(data={"short_code": code})
        
        # 生成失败，记录连续失败次数
        consecutive_failures += 1
        logger.warning(f"生成短链接代码失败 (长度: {length}, 连续失败: {consecutive_failures})")
        
        # 如果连续失败5次，增加位数
        # ---------- 条件分支 ----------
        if consecutive_failures >= max_consecutive_failures:
            length += 1
            consecutive_failures = 0  # 重置计数器
            logger.info(f"增加短链接代码长度到 {length} 位")
            
            # 如果达到最大长度，停止尝试
            # ---------- 条件分支 ----------
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
    """
    检查短链接代码是否已被占用。

    权限：登录用户；供前端实时校验输入。
    """
    result = await db.execute(
        select(ShortLink).where(ShortLink.short_code == short_code)
    )
    exists = result.scalars().first() is not None
    
    return ResponseBaseSchema.success(data={"exists": exists, "short_code": short_code})


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
    """
    创建短链接。

    权限：仅管理员。
    业务：委托 ShortLinkService 完成 URL 校验、代码生成及审计日志。
    """
    # 使用服务层（业务逻辑在ShortLinkService中）
    short_link_service: ShortLinkService = await get_short_link_service(db)
    
    # 准备短链接数据
    link_data = link_in.model_dump()
    
    # 调用服务层创建短链接（服务层会处理验证和代码生成）
    short_link = await short_link_service.create_short_link(link_data, current_user)

    await log_create(
        db=db,
        user=current_user,
        resource_type="SHORT_LINK",
        resource_id=short_link.id,
        resource_name=short_link.short_code,
        request=request,
    )
    await commit_audit_log(db)
    
    # 构建完整的短链接URL
    base_url = str(request.base_url).rstrip('/')
    short_url = f"{base_url}/s/{short_link.short_code}"
    
    response_data = ShortLinkResponse.model_validate(short_link)
    response_data.short_url = short_url
    
    return ResponseBaseSchema.success(data=response_data)


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
    """
    分页获取短链接列表，支持标题/URL/短码搜索及 Offer、创建者筛选。

    权限：登录用户，按数据权限过滤可见范围；响应附带完整 short_url。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 使用服务层（业务逻辑在ShortLinkService中）
    short_link_service: ShortLinkService = await get_short_link_service(db)
    
    short_links, total = await short_link_service.get_short_links(
        current_user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        created_by=created_by,
        offer_id=offer_id
    )
    
    # 构建完整的短链接URL
    base_url = str(request.base_url).rstrip('/')
    links_data = []
    # ---------- 循环处理 ----------
    for link in short_links:
        link_data = ShortLinkResponse.model_validate(link)
        link_data.short_url = f"{base_url}/s/{link.short_code}"
        # 添加创建者名称（已通过joinedload预加载）
        # ---------- 条件分支 ----------
        if link.creator:
            link_data.creator_name = link.creator.username
        # 添加渠道名称（已通过joinedload预加载）
        # ---------- 条件分支 ----------
        if link.channel:
            link_data.channel_name = link.channel.publisher_name
        links_data.append(link_data)
    
    # ---------- 构建响应 ----------
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
    """
    按 link_id 获取单条短链接详情（含点击数、渠道名、完整 short_url）。

    权限：登录用户；无权限时返回 404。
    """
    # 使用服务层（业务逻辑在ShortLinkService中）
    short_link_service: ShortLinkService = await get_short_link_service(db)
    
    # 获取短链接（包含关联信息）
    short_link = await short_link_service.get_short_link_by_id(link_id, current_user, include_relations=True)
    
    # 构建完整的短链接URL
    base_url = str(request.base_url).rstrip('/')
    response_data = ShortLinkResponse.model_validate(short_link)
    response_data.short_url = f"{base_url}/s/{short_link.short_code}"
    # 添加创建者名称（已通过joinedload预加载）
    if short_link.creator:
        response_data.creator_name = short_link.creator.username
    # 添加渠道名称（已通过joinedload预加载）
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
    """
    按 link_id 更新短链接（URL、标题、Offer 关联、像素配置等）。

    修改 original_url 时重新校验 Tracklink 占位符。
    权限：仅管理员。
    """
    # 使用服务层（业务逻辑在ShortLinkService中）
    short_link_service: ShortLinkService = await get_short_link_service(db)
    
    # 获取更新数据
    update_data = link_in.model_dump(exclude_unset=True)
    
    # 调用服务层更新短链接（服务层会处理验证、权限检查和缓存清理）
    short_link = await short_link_service.update_short_link(link_id, update_data, current_user)

    if update_data:
        await log_update(
            db=db,
            user=current_user,
            resource_type="SHORT_LINK",
            resource_id=link_id,
            resource_name=short_link.short_code,
            request=request,
            details={"updated_fields": list(update_data.keys())},
        )
        await commit_audit_log(db)
    
    # 构建完整的短链接URL
    base_url = str(request.base_url).rstrip('/')
    response_data = ShortLinkResponse.model_validate(short_link)
    response_data.short_url = f"{base_url}/s/{short_link.short_code}"
    
    return ResponseBaseSchema.success(data=response_data)


@router.delete("/{link_id}",
                response_model=ResponseBaseSchema[dict],
                summary="删除短链接")
async def delete_short_link(
    request: Request,
    link_id: int = Path(..., ge=1, description="短链接ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    删除短链接。

    权限：仅管理员；有关联点击时由服务层拦截。
    """
    # 使用服务层（业务逻辑在ShortLinkService中）
    short_link_service: ShortLinkService = await get_short_link_service(db)

    short_link = await short_link_service.get_short_link_by_id(
        link_id, current_user, include_relations=False
    )
    short_code = short_link.short_code

    # 调用服务层删除短链接（服务层会处理权限检查和缓存清理）
    await short_link_service.delete_short_link(link_id, current_user)

    await log_delete(
        db=db,
        user=current_user,
        resource_type="SHORT_LINK",
        resource_id=link_id,
        resource_name=short_code,
        request=request,
    )
    await commit_audit_log(db)
    
    return ResponseBaseSchema.success(data={"message": "短链接已删除"})


@router.get("/stats/summary",
            response_model=ResponseBaseSchema[ShortLinkStatsResponse],
            summary="获取短链接统计")
async def get_short_link_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取短链接点击统计摘要。

    权限：登录用户；含点击量、转化率等聚合指标。
    """
    # ---------- 入口：参数与依赖准备 ----------
    # 构建基础查询条件
    base_conditions = []
    # ---------- 条件分支 ----------
    if current_user.role != UserRole.ADMIN:
        # 普通用户只能查看自己的统计
        base_conditions.append(ShortLink.created_by == current_user.id)
    
    # 计算总数
    total_query = select(func.count(ShortLink.id))
    # ---------- 条件分支 ----------
    if base_conditions:
        total_query = total_query.where(and_(*base_conditions))
    total_result = await db.execute(total_query)
    total_links = total_result.scalar() or 0
    
    # 计算总点击次数
    click_query = select(func.sum(ShortLink.click_count))
    # ---------- 条件分支 ----------
    if base_conditions:
        click_query = click_query.where(and_(*base_conditions))
    click_result = await db.execute(click_query)
    total_clicks = click_result.scalar() or 0
    # 确保 total_clicks 是整数
    # ---------- 条件分支 ----------
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
    
    # ---------- 构建响应 ----------
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    手动触发短链接点击次数同步
    将Redis中的点击次数同步到数据库
    
    注意：此接口需要管理员权限
    """
    # ---------- 入口：参数与依赖准备 ----------
    
    # ---------- 异常处理 ----------
    try:
        logger.info(f"管理员 {current_user.id} 手动触发短链接点击次数同步")
        synced_count = await sync_click_counts_to_db(db)
        
        await log_user_action(
            db=db,
            action_type="TASK_RUN",
            user=current_user,
            resource_type="SHORT_LINK",
            resource_id=0,
            resource_name="同步短链接点击数",
            request=request,
            details={"synced_count": synced_count},
        )
        await commit_audit_log(db)
        # ---------- 条件分支 ----------
        if synced_count > 0:
            logger.info(f"手动同步成功: 更新了 {synced_count} 条记录")
            return ResponseBaseSchema.success(
                data={"synced_count": synced_count, "message": f"成功同步 {synced_count} 个短链接的点击次数"}
            )
        else:
            return ResponseBaseSchema.success(
                data={"synced_count": 0, "message": "没有需要同步的点击次数"}
            )
    except HTTPException:
        raise
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
    # ---------- 入口：参数与依赖准备 ----------
    
    # 获取进程内计数器统计信息（使用安全的函数，而不是直接访问私有变量）
    memory_stats = await get_click_counter_stats()
    
    stats = {
        "redis_available": False,
        "redis_counters": 0,
        "redis_counter_details": [],
        "memory_counters": memory_stats["total_counters"],
        "memory_counter_details": memory_stats.get("counter_details", []),  # 使用函数返回的详细信息
        "memory_total_clicks": memory_stats["total_clicks"],
        "database_total_clicks": 0,
        "deadlock_stats": await get_deadlock_stats(),  # 添加死锁统计信息
    }
    
    # 检查Redis状态
    redis = await get_redis_client()
    # ---------- 条件分支 ----------
    if redis:
        stats["redis_available"] = True
        # ---------- 异常处理 ----------
        try:
            # 使用SCAN而不是KEYS，避免在生产环境阻塞
            pattern = f"{CLICK_COUNTER_PREFIX}*"
            keys = []
            cursor = 0
            max_iterations = 100  # 限制迭代次数，避免长时间阻塞（最多10000个键）
            iteration = 0
            # ---------- 异常处理 ----------
            try:
                while True:
                    cursor, batch_keys = await redis.scan(cursor, match=pattern, count=100)
                    keys.extend(batch_keys)
                    iteration += 1
                    
                    # 安全检查：防止无限循环
                    # ---------- 条件分支 ----------
                    if iteration >= max_iterations:
                        logger.warning(
                            f"Redis SCAN达到最大迭代次数 {max_iterations}，停止扫描。"
                            f"已收集 {len(keys)} 个键"
                        )
                        break
                    
                    # ---------- 条件分支 ----------
                    if cursor == 0:
                        break
            except Exception as scan_error:
                # 如果SCAN失败，降级使用KEYS（仅用于监控端点，影响较小）
                logger.warning(f"Redis SCAN失败，降级使用KEYS: {scan_error}")
                keys = await redis.keys(pattern)
            
            stats["redis_counters"] = len(keys)
            
            # 获取每个计数器的详细信息（最多显示20个）
            # ---------- 循环处理 ----------
            for key in keys[:20]:
                # 安全地提取 short_code：使用 startswith 检查并移除前缀
                # ---------- 条件分支 ----------
                if not key.startswith(CLICK_COUNTER_PREFIX):
                    continue
                
                short_code = key[len(CLICK_COUNTER_PREFIX):]
                
                # 验证 short_code 不为空
                # ---------- 条件分支 ----------
                if not short_code:
                    continue
                
                # ---------- 异常处理 ----------
                try:
                    count = await redis.get(key)
                    count_value = int(count) if count else 0
                    stats["redis_counter_details"].append({
                        "short_code": short_code,
                        "count": count_value,
                        "key": key
                    })
                except Exception as get_error:
                    logger.debug(f"获取Redis计数器值失败: key={key}, error={get_error}")
        except Exception as e:
            stats["redis_error"] = str(e)
    
    # 获取数据库中的总点击次数
    # ---------- 异常处理 ----------
    try:
        result = await db.execute(select(func.sum(ShortLink.click_count)))
        total_clicks = result.scalar() or 0
        stats["database_total_clicks"] = int(total_clicks)
    except Exception as e:
        stats["database_error"] = str(e)
    
    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data=stats)


@router.get("/diagnose/{short_code}",
            response_model=ResponseBaseSchema,
            summary="诊断短链接同步状态（管理员）")
async def diagnose_short_link_sync(
    short_code: str = Path(..., description="短链接代码"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    诊断短链接的同步状态
    
    检查短链接的完整状态，包括：
    - 短链接是否存在
    - 是否激活
    - 是否过期
    - 数据库中的点击计数
    - Redis中的计数器值
    - 进程内计数器值
    - 同步失败的可能原因
    
    注意：此接口需要管理员权限
    """
    # ---------- 入口：参数与依赖准备 ----------
    from app.core.short_link_click_counter import get_click_counter_stats
    from app.core.constants import APP_TIMEZONE
    
    diagnosis = {
        "short_code": short_code,
        "exists": False,
        "is_active": False,
        "is_expired": False,
        "database_click_count": None,
        "redis_counter_value": None,
        "memory_counter_value": None,
        "redis_key": f"{CLICK_COUNTER_PREFIX}{short_code}",
        "issues": [],
        "recommendations": []
    }
    
    # 1. 检查数据库中的短链接
    # ---------- 异常处理 ----------
    try:
        result = await db.execute(
            select(ShortLink).where(ShortLink.short_code == short_code)
        )
        short_link = result.scalars().first()
        
        # ---------- 条件分支 ----------
        if short_link:
            diagnosis["exists"] = True
            diagnosis["is_active"] = short_link.is_active
            diagnosis["database_click_count"] = short_link.click_count or 0
            
            # 检查是否过期
            # ---------- 条件分支 ----------
            if short_link.expires_at:
                expires_at = short_link.expires_at
                # ---------- 条件分支 ----------
                if expires_at.tzinfo is not None:
                    expires_at = expires_at.astimezone(APP_TIMEZONE).replace(tzinfo=None)
                now = get_app_now_naive()
                diagnosis["is_expired"] = expires_at < now
                # ---------- 条件分支 ----------
                if diagnosis["is_expired"]:
                    diagnosis["issues"].append("短链接已过期")
                    diagnosis["recommendations"].append("如果短链接已过期但仍在使用，请更新过期时间")
        else:
            diagnosis["issues"].append("短链接在数据库中不存在")
            diagnosis["recommendations"].append("检查短链接代码是否正确，或该短链接已被删除")
    except Exception as e:
        diagnosis["issues"].append(f"查询数据库失败: {str(e)}")
        logger.error(f"诊断短链接时查询数据库失败: {e}", exc_info=True)
    
    # 2. 检查Redis中的计数器
    redis = await get_redis_client()
    # ---------- 条件分支 ----------
    if redis:
        # ---------- 异常处理 ----------
        try:
            redis_key = f"{CLICK_COUNTER_PREFIX}{short_code}"
            counter_value = await redis.get(redis_key)
            # ---------- 条件分支 ----------
            if counter_value:
                diagnosis["redis_counter_value"] = int(counter_value)
                # ---------- 条件分支 ----------
                if diagnosis["redis_counter_value"] > 0:
                    diagnosis["issues"].append(f"Redis中有待同步的计数器值: {diagnosis['redis_counter_value']}")
                    diagnosis["recommendations"].append("等待下次自动同步（每5分钟），或手动触发同步")
        except Exception as e:
            diagnosis["issues"].append(f"查询Redis计数器失败: {str(e)}")
            logger.warning(f"诊断短链接时查询Redis失败: {e}")
    else:
        diagnosis["issues"].append("Redis不可用")
        diagnosis["recommendations"].append("检查Redis连接配置")
    
    # 3. 检查进程内计数器
    # ---------- 异常处理 ----------
    try:
        memory_stats = await get_click_counter_stats()
        # ---------- 循环处理 ----------
        for counter_detail in memory_stats.get("counter_details", []):
            # ---------- 条件分支 ----------
            if counter_detail.get("short_code") == short_code:
                diagnosis["memory_counter_value"] = counter_detail.get("count", 0)
                # ---------- 条件分支 ----------
                if diagnosis["memory_counter_value"] > 0:
                    diagnosis["issues"].append(f"进程内有待同步的计数器值: {diagnosis['memory_counter_value']}")
                    diagnosis["recommendations"].append("等待下次自动同步（每5分钟），或手动触发同步")
                break
    except Exception as e:
        logger.warning(f"诊断短链接时查询进程内计数器失败: {e}")
    
    # 4. 分析可能的问题
    # ---------- 条件分支 ----------
    if not diagnosis["exists"]:
        diagnosis["recommendations"].append("如果短链接不存在，Redis中的计数器将在下次同步时自动清理")
    # ---------- 条件分支 ----------
    elif not diagnosis["is_active"]:
        diagnosis["issues"].append("短链接已禁用")
        diagnosis["recommendations"].append("如果短链接已禁用但仍在使用，请重新激活")
    # ---------- 条件分支 ----------
    elif diagnosis["is_expired"]:
        diagnosis["recommendations"].append("如果短链接已过期但仍在使用，请更新过期时间")
    
    # 5. 检查是否有待同步的数据
    has_pending_sync = (
        (diagnosis["redis_counter_value"] and diagnosis["redis_counter_value"] > 0) or
        (diagnosis["memory_counter_value"] and diagnosis["memory_counter_value"] > 0)
    )
    
    # ---------- 条件分支 ----------
    if has_pending_sync and diagnosis["exists"] and diagnosis["is_active"] and not diagnosis["is_expired"]:
        diagnosis["recommendations"].append("短链接状态正常，待同步的计数器将在下次自动同步时处理")
    
    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data=diagnosis)


@router.post("/diagnose-batch",
             response_model=ResponseBaseSchema,
             summary="批量诊断短链接同步状态（管理员）")
async def diagnose_short_links_batch(
    request: Request,
    short_codes: list[str] = Body(..., description="短链接代码列表"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    批量诊断短链接的同步状态
    
    一次检查多个短链接的状态，适用于诊断同步失败的问题
    
    注意：此接口需要管理员权限
    """
    # ---------- 入口：参数与依赖准备 ----------
    # ---------- 条件分支 ----------
    if not short_codes:
        raise_api_exception(
            ErrorCode.INVALID_PARAMETER,
            detail="请提供至少一个短链接代码"
        )
    
    # ---------- 条件分支 ----------
    if len(short_codes) > 50:
        raise_api_exception(
            ErrorCode.INVALID_PARAMETER,
            detail="一次最多只能诊断50个短链接"
        )
    
    results = []
    # ---------- 循环处理 ----------
    for short_code in short_codes:
        # 调用单个诊断函数（复用逻辑）
        diagnosis = await diagnose_short_link_sync(short_code, db, current_user)
        results.append(diagnosis.data)
    
    # 统计信息
    summary = {
        "total": len(short_codes),
        "exists": sum(1 for r in results if r.get("exists")),
        "active": sum(1 for r in results if r.get("is_active")),
        "expired": sum(1 for r in results if r.get("is_expired")),
        "has_redis_counter": sum(1 for r in results if r.get("redis_counter_value") and r.get("redis_counter_value", 0) > 0),
        "has_memory_counter": sum(1 for r in results if r.get("memory_counter_value") and r.get("memory_counter_value", 0) > 0),
        "has_issues": sum(1 for r in results if r.get("issues")),
    }
    
    await log_user_action(
        db=db,
        action_type="API_ACCESS",
        user=current_user,
        resource_type="SHORT_LINK",
        resource_id=0,
        resource_name="批量诊断短链接",
        request=request,
        details={"total": summary["total"]},
    )
    await commit_audit_log(db)

    # ---------- 构建响应 ----------
    return ResponseBaseSchema.success(data={
        "summary": summary,
        "details": results
    })
