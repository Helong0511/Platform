"""斗篷 /report 点击落库（尊重 PERSIST_CLICKS_TO_DB）。"""
import json
import logging
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import AsyncSessionLocal
from app.core.tracking.click_id_generator import generate_click_id_unified
from app.core.tracking.click_persist import persist_click_record, should_persist_clicks_to_db
from app.core.utils import get_app_now_naive
from app.models.models import ShortLink
from app.core.url.url_params_util import pack_query_params_for_storage
from app.routes.short_link.utils import resolve_cloak_click_offer_and_publisher

logger = logging.getLogger(__name__)


def build_cloak_url_params(
        fbclid: Optional[str],
        resolved_dp: Optional[str],
        email: Optional[str],
        phone: Optional[str],
) -> Optional[str]:
    flat: Dict[str, Any] = {}
    if fbclid:
        flat["fbclid"] = fbclid
    if resolved_dp:
        flat["dp"] = resolved_dp
    if email:
        flat["email"] = email
    if phone:
        flat["phone"] = phone
    packed = pack_query_params_for_storage(flat)
    return json.dumps(packed, ensure_ascii=False) if packed else None


async def persist_cloak_report_click(
        short_code: str,
        fbclid: Optional[str],
        resolved_dp: Optional[str],
        email: Optional[str],
        phone: Optional[str],
        client_ip: str,
        user_agent: str,
        referer: str,
        original_request_url: Optional[str],
        background_tasks: Optional[BackgroundTasks] = None,
        *,
        sync_short_link_click_count: bool = True,
) -> None:
    """
    将斗篷 /report 点击写入队列/clicks 表（仅当 PERSIST_CLICKS_TO_DB 生效时）。

    sync_short_link_click_count: 是否在落库时同步更新 short_links.click_count。
    """
    if not should_persist_clicks_to_db():
        logger.debug("[斗篷点击] PERSIST_CLICKS_TO_DB 未启用，跳过 Click 落库: short_code=%s", short_code)
        return

    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(ShortLink).where(ShortLink.short_code == short_code)
            )
            short_link = result.scalars().first()
            if not short_link:
                logger.warning("[斗篷点击] 短链接不存在，跳过落库: short_code=%s", short_code)
                return

            offer_id, publisher_id = await resolve_cloak_click_offer_and_publisher(
                short_link.offer_id,
                short_link.channel_id,
                resolved_dp,
                db_session,
            )

            if sync_short_link_click_count:
                short_link.click_count = (short_link.click_count or 0) + 1
                await db_session.commit()

            click_id = generate_click_id_unified(
                offer_id=offer_id,
                publisher_id=publisher_id,
                short_link_id=short_link.id,
                for_short_link=True,
            )
            click_data = {
                "click_id": click_id,
                "short_link_id": short_link.id,
                "offer_id": offer_id,
                "publisher_id": publisher_id,
                "advertiser_id": None,
                "click_time": get_app_now_naive().isoformat(),
                "ip": client_ip if client_ip != "未知" else None,
                "user_agent": user_agent if user_agent != "未知" else None,
                "referer": referer if referer != "未知" else None,
                "url_params": build_cloak_url_params(fbclid, resolved_dp, email, phone),
                "original_request_url": original_request_url,
                "is_bot": False,
            }
            await persist_click_record(click_data, background_tasks)
            logger.info(
                "[斗篷点击] 已排队落库: short_code=%s click_id=%s",
                short_code,
                click_data["click_id"],
            )
        except Exception as exc:
            await db_session.rollback()
            logger.error(
                "[斗篷点击] 落库失败: short_code=%s %s",
                short_code,
                exc,
                exc_info=True,
            )
        finally:
            await db_session.close()


def schedule_cloak_report_click_persist(
        background_tasks: BackgroundTasks,
        short_code: str,
        fbclid: Optional[str],
        resolved_dp: Optional[str],
        email: Optional[str],
        phone: Optional[str],
        client_ip: str,
        user_agent: str,
        referer: str,
        original_request_url: Optional[str],
        *,
        sync_short_link_click_count: bool = True,
) -> None:
    """在后台任务中执行 persist_cloak_report_click。"""
    if not should_persist_clicks_to_db():
        return

    async def _task():
        await persist_cloak_report_click(
            short_code=short_code,
            fbclid=fbclid,
            resolved_dp=resolved_dp,
            email=email,
            phone=phone,
            client_ip=client_ip,
            user_agent=user_agent,
            referer=referer,
            original_request_url=original_request_url,
            background_tasks=None,
            sync_short_link_click_count=sync_short_link_click_count,
        )

    background_tasks.add_task(_task)
