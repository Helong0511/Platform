"""
斗篷 /change 桥页展示次数统计与 original_url 解析。

职责：
1. 按浏览器会话（session_id Cookie）统计 short_links.show_count，同会话重复打开桥页不重复计数
2. 返回短链配置的 original_url，供 cloak_change 做占位符替换与最终跳转
3. 控制桥页首次访问时是否写入 clicks 表（会话维度 + IP 短窗口去重）

与 Redis 的配合：
- show_count:{short_code}:{session_id}：展示去重，TTL 6 小时
- cloak_visit_click:{short_code}:{session_id}：桥页访问落库去重
- cloak_visit_click_ip:{short_code}:{ip}：Cookie 未落盘时的并发请求去重
"""
import logging
import uuid
from typing import Any, Dict, Optional, Tuple

from fastapi import BackgroundTasks, Request
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.exc import StaleDataError

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis_client
from app.core.short_link_cache import update_short_link_cache
from app.models.models import ShortLink
from app.routes.short_link.errors import raise_short_link_not_found

logger = logging.getLogger(__name__)

# 展示次数与会话落库去重的 Redis 键 TTL（秒），与 session_id Cookie max_age 对齐（6 小时）
SHOW_COUNT_TTL_SECONDS = 21600
# 同 IP 在 Cookie 未生效前的并发 /change 请求去重窗口（秒），避免双写 clicks
CLOAK_VISIT_CLICK_IP_DEDUPE_SECONDS = 30


def resolve_session_id(request: Request) -> str:
    """
    解析或生成桥页会话 ID。

    优先读取 request 中 session_id Cookie（由 build_bridge_html_response 在首次响应时写入）；
    首次访问无 Cookie 时生成 UUID，并在响应中 Set-Cookie 使后续 /change、/report 共享同一会话。

    Args:
        request: FastAPI 请求对象

    Returns:
        会话 ID 字符串（UUID 或已有 Cookie 值）
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.debug("[斗篷服务] 生成新会话ID: %s", session_id)
    else:
        logger.debug("[斗篷服务] 使用现有会话ID: %s", session_id)
    return session_id


async def session_already_shown(short_code: str, session_id: str) -> bool:
    """Redis SET NX：首次访问返回 False，同会话重复访问返回 True。"""
    redis = await get_redis_client()
    show_key = f"show_count:{short_code}:{session_id}"
    logger.debug("[斗篷服务] 检查展示次数: key=%s", show_key)
    if not redis:
        logger.debug("[斗篷服务] Redis客户端不可用")
        return False
    try:
        first_show = await redis.set(show_key, "1", ex=SHOW_COUNT_TTL_SECONDS, nx=True)
        has_shown = not bool(first_show)
        logger.debug(
            "[斗篷服务] Redis 展示标记: key=%s 首次访问=%s",
            show_key,
            not has_shown,
        )
        return has_shown
    except Exception as exc:
        logger.error("[斗篷服务] Redis检查展示次数失败: %s", exc)
        return False


async def should_persist_cloak_visit_click(
        short_code: str,
        session_id: str,
        client_ip: str,
) -> bool:
    """
    是否应为本次 /change 访问写入 clicks 表。

    - 同 session 仅写一次（与 show_count 会话维度一致）
    - 同 IP 在短窗口内仅写一次，避免 Cookie 未落盘时的并发双请求
    """
    redis = await get_redis_client()
    if not redis:
        return True
    ip_key = f"cloak_visit_click_ip:{short_code}:{client_ip}"
    session_key = f"cloak_visit_click:{short_code}:{session_id}"
    try:
        if await redis.get(ip_key):
            logger.debug(
                "[斗篷服务] 跳过桥页点击落库（同 IP 短窗口去重）: short_code=%s ip=%s",
                short_code,
                client_ip,
            )
            return False
        if not await redis.set(session_key, "1", ex=SHOW_COUNT_TTL_SECONDS, nx=True):
            logger.debug(
                "[斗篷服务] 跳过桥页点击落库（同会话已记录）: short_code=%s session=%s",
                short_code,
                session_id,
            )
            return False
        await redis.set(ip_key, "1", ex=CLOAK_VISIT_CLICK_IP_DEDUPE_SECONDS)
        return True
    except Exception as exc:
        logger.warning("[斗篷服务] 桥页点击去重检查失败，允许落库: %s", exc)
        return True


async def _fetch_original_url_from_db(
        short_code: str,
        db: AsyncSession,
) -> Optional[str]:
    """重复访问且缓存未命中时，仅从库读取 original_url（不递增 show_count）。"""
    result = await db.execute(
        select(ShortLink).where(ShortLink.short_code == short_code)
    )
    short_link = result.scalars().first()
    if short_link:
        return short_link.original_url
    logger.debug("[斗篷服务] 短链接不存在: short_code=%s", short_code)
    return None


async def _increment_show_count_in_db(
        short_code: str,
        db: AsyncSession,
) -> Optional[str]:
    """缓存未命中时同步递增 short_links.show_count 并返回 original_url。"""
    result = await db.execute(
        select(ShortLink).where(ShortLink.short_code == short_code)
    )
    short_link = result.scalars().first()
    if not short_link:
        logger.debug("[斗篷服务] 短链接不存在: short_code=%s", short_code)
        return None
    original_url = short_link.original_url
    logger.debug(
        "[斗篷服务] 数据库查询结果: short_code=%s, id=%s, 原始show_count=%s",
        short_code,
        short_link.id,
        short_link.show_count or 0,
    )
    short_link.show_count = (short_link.show_count or 0) + 1
    logger.debug(
        "[斗篷服务] 更新数据库: short_code=%s, 新show_count=%s",
        short_code,
        short_link.show_count,
    )
    try:
        await db.commit()
        logger.debug("[斗篷服务] 数据库提交成功")
    except StaleDataError:
        logger.debug("[斗篷服务] 数据库更新冲突，忽略StaleDataError")
        await db.rollback()
    return original_url


def _schedule_db_show_count_sync(
        short_code: str,
        cached_data: Dict[str, Any],
        background_tasks: BackgroundTasks,
) -> None:
    """后台任务：将缓存中已递增的 show_count 同步到数据库（仅当库值落后时更新）。"""
    async def update_show_count_db():
        """后台协程：仅当库内 show_count 落后于缓存目标值时写库。"""
        target = cached_data.get("show_count", 0)
        try:
            async with AsyncSessionLocal() as db_session:
                # 单条 UPDATE 避免 ORM 先查后改：短链被删或并发时不会抛 StaleDataError
                result = await db_session.execute(
                    update(ShortLink)
                    .where(ShortLink.short_code == short_code)
                    .where(func.coalesce(ShortLink.show_count, 0) < target)
                    .values(show_count=target)
                )
                if result.rowcount > 0:
                    await db_session.commit()
                    logger.debug(
                        "[斗篷服务] 后台任务更新数据库: short_code=%s, 新show_count=%s",
                        short_code,
                        target,
                    )
                else:
                    await db_session.rollback()
                    logger.debug(
                        "[斗篷服务] 数据库无需更新或短链不存在: short_code=%s, target=%s",
                        short_code,
                        target,
                    )
        except StaleDataError:
            logger.debug(
                "[斗篷服务] 后台任务更新冲突，忽略 StaleDataError: short_code=%s",
                short_code,
            )
        except Exception as exc:
            logger.error(
                "[斗篷服务] 后台任务更新数据库失败: %s", exc, exc_info=True
            )

    background_tasks.add_task(update_show_count_db)
    logger.debug("[斗篷服务] 添加后台任务: 更新数据库展示次数")


async def _record_first_show_and_get_url(
        short_code: str,
        cached_data: Optional[Dict[str, Any]],
        db: AsyncSession,
        background_tasks: BackgroundTasks,
) -> Optional[str]:
    """本会话首次展示：递增 show_count（缓存优先）并返回 original_url。"""
    logger.debug("[斗篷服务] 首次访问，开始统计展示次数: short_code=%s", short_code)
    if cached_data:
        original_url = cached_data.get("original_url")
        logger.debug(
            "[斗篷服务] 从缓存获取数据: short_code=%s, 原始show_count=%s",
            short_code,
            cached_data.get("show_count", 0),
        )
        cached_data["show_count"] = cached_data.get("show_count", 0) + 1
        logger.debug(
            "[斗篷服务] 更新缓存: short_code=%s, 新show_count=%s",
            short_code,
            cached_data["show_count"],
        )
        update_result = await update_short_link_cache(short_code, cached_data)
        logger.debug("[斗篷服务] 缓存更新结果: %s", update_result)
        _schedule_db_show_count_sync(short_code, cached_data, background_tasks)
        return original_url

    logger.debug("[斗篷服务] 缓存未命中，从数据库查询: short_code=%s", short_code)
    return await _increment_show_count_in_db(short_code, db)


async def resolve_cloak_change_original_url(
        short_code: str,
        session_id: str,
        cached_data: Optional[Dict[str, Any]],
        db: AsyncSession,
        background_tasks: BackgroundTasks,
) -> Tuple[str, bool]:
    """
    按会话统计展示次数并返回斗篷原始跳转 URL。

    Returns:
        (original_url, is_first_visit) — is_first_visit 为 True 表示本会话首次展示

    Raises:
        HTTPException: 404 当短链不存在或未配置 original_url
    """
    has_shown = await session_already_shown(short_code, session_id)
    is_first_visit = not has_shown
    if not has_shown:
        original_url = await _record_first_show_and_get_url(
            short_code, cached_data, db, background_tasks
        )
    else:
        logger.debug("[斗篷服务] 重复访问，跳过统计: short_code=%s", short_code)
        if cached_data:
            original_url = cached_data.get("original_url")
            logger.debug("[斗篷服务] 从缓存获取原始URL: %s", original_url)
        else:
            logger.debug(
                "[斗篷服务] 缓存未命中，从数据库查询原始URL: short_code=%s", short_code
            )
            original_url = await _fetch_original_url_from_db(short_code, db)

    if not original_url:
        logger.error("[斗篷服务] 未找到原始 URL: short_code=%s", short_code)
        raise_short_link_not_found("斗篷不存在或未配置原始 URL")
    return original_url, is_first_visit
