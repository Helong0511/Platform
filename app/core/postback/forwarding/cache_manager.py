"""
缓存管理器

管理 Postback 转发相关的缓存数据
"""
import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import Publisher, Offer
from app.core.infrastructure.cache_compat import (
    generate_cache_key,
    legacy_get_cached as get_cached,
    legacy_set_cached as set_cached,
)

logger = logging.getLogger(__name__)


class CacheManager:
    """缓存管理器"""
    
    @staticmethod
    async def get_cached_publisher(publisher_id: int, db: AsyncSession) -> Optional[Publisher]:
        """
        获取缓存的渠道信息
        
        Args:
            publisher_id: 渠道 ID
            db: 数据库会话
        
        Returns:
            Publisher: 渠道对象
        """
        cache_key = generate_cache_key("publisher", publisher_id)
        
        # 尝试从缓存获取
        cached_data = await get_cached(cache_key, key_prefix="postback_forward")
        if cached_data:
            try:
                result = await db.execute(
                    select(Publisher).where(Publisher.id == publisher_id)
                )
                publisher = result.scalars().first()
                if publisher:
                    for key, value in cached_data.items():
                        if hasattr(publisher, key):
                            setattr(publisher, key, value)
                    return publisher
            except Exception as e:
                logger.debug(f"从缓存重建 Publisher 对象失败：{str(e)}")
        
        # 缓存不存在，从数据库查询
        result = await db.execute(
            select(Publisher).where(Publisher.id == publisher_id)
        )
        publisher = result.scalars().first()
        
        if publisher:
            # 缓存渠道信息（5 分钟）
            try:
                publisher_data = {
                    "id": publisher.id,
                    "publisher_name": publisher.publisher_name,
                    "postback_url": publisher.postback_url,
                    "postback_method": publisher.postback_method,
                    "postback_success_check": publisher.postback_success_check
                }
                await set_cached(cache_key, publisher_data, ttl=300, key_prefix="postback_forward")
            except Exception as e:
                logger.debug(f"缓存 Publisher 信息失败：{str(e)}")
        
        return publisher
    
    @staticmethod
    async def get_cached_offer(offer_id: int, db: AsyncSession) -> Optional[Offer]:
        """
        获取缓存的 Offer 信息
        
        Args:
            offer_id: Offer ID
            db: 数据库会话
        
        Returns:
            Offer: Offer 对象
        """
        cache_key = generate_cache_key("offer", offer_id)
        
        # 尝试从缓存获取
        cached_data = await get_cached(cache_key, key_prefix="postback_forward")
        if cached_data:
            try:
                result = await db.execute(
                    select(Offer).where(Offer.id == offer_id)
                )
                offer = result.scalars().first()
                if offer:
                    for key, value in cached_data.items():
                        if hasattr(offer, key):
                            setattr(offer, key, value)
                    return offer
            except Exception as e:
                logger.debug(f"从缓存重建 Offer 对象失败：{str(e)}")
        
        # 缓存不存在，从数据库查询
        result = await db.execute(
            select(Offer).where(Offer.id == offer_id)
        )
        offer = result.scalars().first()
        
        if offer:
            # 缓存 Offer 信息（5 分钟）
            try:
                offer_data = {
                    "id": offer.id,
                    "offer_name": offer.offer_name,
                    "advertiser_id": offer.advertiser_id
                }
                await set_cached(cache_key, offer_data, ttl=300, key_prefix="postback_forward")
            except Exception as e:
                logger.debug(f"缓存 Offer 信息失败：{str(e)}")
        
        return offer
