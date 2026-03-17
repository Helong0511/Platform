"""
短链接重定向工具函数
"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import BackgroundTasks

from app.models.models import Offer
from app.core.offer_cache import set_offer_cache
from app.core.clicks_queue import enqueue_click
from app.core.utils import get_app_now_naive
from app.api_v1.tracking.tracking import create_click_background

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
    
    enqueued = await enqueue_click(click_data)
    if not enqueued:
        click_data['click_time'] = get_app_now_naive()
        background_tasks.add_task(create_click_background, click_data)

