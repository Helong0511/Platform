"""
短链接重定向工具函数
"""
import logging
from typing import Optional

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.offer_cache import set_offer_cache
from app.core.utils import get_app_now_naive
from app.models.models import Offer, OfferPublisherAssignment

logger = logging.getLogger(__name__)


async def resolve_offer_id(offer_id: Optional[int], db: AsyncSession) -> tuple[Optional[int], Optional[int]]:
    """
    解析Offer ID，返回(offer_id, advertiser_id)
    
    这个函数用于解析和验证Offer ID，并获取对应的广告主ID。
    支持两种查询方式：
    1. 作为主键ID查询（优先）
    2. 作为上游Offer ID查询（如果主键查询失败）
    
    Args:
        offer_id: Offer的ID（可能是主键ID或上游Offer ID）
        db: 数据库会话
    
    Returns:
        tuple[Optional[int], Optional[int]]: 
            - 第一个元素：Offer的主键ID（如果找到）
            - 第二个元素：广告主ID（如果找到Offer）
            如果 offer_id 为 None 或找不到，返回 (None, None)
    """
    if not offer_id:
        return None, None

    try:
        # 先尝试作为主键ID查询
        offer_result = await db.execute(
            select(Offer).where(Offer.id == offer_id)
        )
        offer = offer_result.scalars().first()

        # 如果找不到，尝试作为上游Offer ID查询
        if not offer:
            offer_result = await db.execute(
                select(Offer).where(Offer.advertiser_offer_id == str(offer_id))
            )
            offer = offer_result.scalars().first()

        if offer:
            await set_offer_cache(offer.id, offer.advertiser_id, offer.offer_name)
            return offer.id, offer.advertiser_id
    except Exception as e:
        logger.warning(f"查询Offer失败: offer_id={offer_id}, error={e}")

    return None, None


def offer_id_from_numeric_dp(dp: Optional[str]) -> Optional[int]:
    """
    纯数字 dp（如 145）与平台 Offer 主键对齐；非数字或空返回 None。
    用于 /change 占位符与 /report 点击归因，与桥页文件名 145.html 约定一致。
    """
    if dp is None:
        return None
    s = str(dp).strip()
    if not s.isdigit():
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


async def resolve_cloak_click_offer_and_publisher(
    short_link_offer_id: Optional[int],
    short_link_channel_id: Optional[int],
    resolved_dp: Optional[str],
    db: AsyncSession,
) -> tuple[Optional[int], Optional[int]]:
    """
    斗篷 /report 写入 clicks 时的 offer_id、publisher_id。
    数字 dp 覆盖短链 offer；渠道为空时按产品绑定回退。
    """
    offer_for = offer_id_from_numeric_dp(resolved_dp)
    if offer_for is None:
        offer_for = short_link_offer_id
    pub_for = short_link_channel_id
    if pub_for is None and offer_for is not None:
        pub_for = await resolve_default_publisher_for_offer(offer_for, db)
    return offer_for, pub_for


async def resolve_default_publisher_for_offer(offer_id: int, db: AsyncSession) -> Optional[int]:
    """
    当短链未关联 channel_id 时，按产品（Offer）下启用的渠道分配回退一个 publisher_id。

    规则：取该 offer 下 is_active=True 的分配记录中 id 最小的一条（稳定、可预期）。
    若无任何启用分配则返回 None。
    """
    if not offer_id:
        return None
    try:
        row = await db.execute(
            select(OfferPublisherAssignment.publisher_id)
            .where(
                OfferPublisherAssignment.offer_id == offer_id,
                OfferPublisherAssignment.is_active.is_(True),
            )
            .order_by(OfferPublisherAssignment.id.asc())
            .limit(1)
        )
        return row.scalar_one_or_none()
    except Exception as e:
        logger.warning(
            "按 Offer 回退渠道失败: offer_id=%s, error=%s",
            offer_id,
            e,
        )
        return None


async def create_click_record(
        click_id: str,
        short_link_id: int,
        offer_id: Optional[int],
        publisher_id: Optional[int],
        advertiser_id: Optional[int],
        request_info: dict,
        background_tasks: BackgroundTasks,
        original_request_url: Optional[str] = None,
        final_redirect_url: Optional[str] = None
):
    """
    创建点击记录（异步处理）
    
    这个函数用于创建点击记录，但不阻塞重定向响应。
    点击记录会先尝试加入Redis队列，如果队列已满，则使用FastAPI后台任务处理。
    """
    click_data = {
        "click_id": click_id,
        "short_link_id": short_link_id,
        "offer_id": offer_id,
        "publisher_id": publisher_id,
        "advertiser_id": advertiser_id,
        "click_time": get_app_now_naive().isoformat(),
        "ip": request_info.get('ip'),
        "user_agent": request_info.get('user_agent'),
        "referer": request_info.get('referer'),
        "country": None,
        "os": request_info.get('os'),
        "os_version": request_info.get('os_version'),
        "browser": request_info.get('browser'),
        "browser_version": request_info.get('browser_version'),
        "accept_language": request_info.get('accept_language'),
        "accept_encoding": request_info.get('accept_encoding'),
        "is_bot": request_info.get('is_bot', False),
        "device_type": request_info.get('device_type'),
        "device_brand": request_info.get('device_brand'),
        "device_model": request_info.get('device_model'),
        "url_params": request_info.get('url_params'),
        "all_headers": request_info.get('all_headers'),
        "device": request_info.get('device_type'),
        "original_request_url": original_request_url,
        "final_redirect_url": final_redirect_url
    }

    from app.core.tracking.click_persist import persist_click_record

    await persist_click_record(click_data, background_tasks)
