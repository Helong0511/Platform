"""斗篷 /change 桥页展示次数统计与 original_url 解析。"""
import logging
import uuid
from typing import Any, Dict, Optional, Tuple

from fastapi import BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm.exc import StaleDataError

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis_client
from app.core.short_link_cache import update_short_link_cache
from app.models.models import ShortLink
from app.routes.short_link.errors import raise_short_link_not_found

logger = logging.getLogger(__name__)

SHOW_COUNT_TTL_SECONDS = 21600
# 同 IP 在 Cookie 未生效前的并发 /change 请求去重窗口（秒）
CLOAK_VISIT_CLICK_IP_DEDUPE_SECONDS = 30


def resolve_session_id(request: Request) -> str:
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
    async def update_show_count_db():
        try:
            db_session = AsyncSessionLocal()
            result = await db_session.execute(
                select(ShortLink).where(ShortLink.short_code == short_code)
            )
            short_link = result.scalars().first()
            if short_link:
                target = cached_data["show_count"]
                if (short_link.show_count or 0) < target:
                    short_link.show_count = target
                    await db_session.commit()
                    logger.debug(
                        "[斗篷服务] 后台任务更新数据库: short_code=%s, 新show_count=%s",
                        short_code,
                        short_link.show_count,
                    )
                else:
                    logger.debug(
                        "[斗篷服务] 数据库值已最新，无需更新: short_code=%s", short_code
                    )
            else:
                logger.debug(
                    "[斗篷服务] 后台任务: 短链接不存在: short_code=%s", short_code
                )
        except Exception as exc:
            logger.error(
                "[斗篷服务] 后台任务更新数据库失败: %s", exc, exc_info=True
            )
        finally:
            if "db_session" in locals():
                await db_session.close()

    background_tasks.add_task(update_show_count_db)
    logger.debug("[斗篷服务] 添加后台任务: 更新数据库展示次数")


async def _record_first_show_and_get_url(
        short_code: str,
        cached_data: Optional[Dict[str, Any]],
        db: AsyncSession,
        background_tasks: BackgroundTasks,
) -> Optional[str]:
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
