"""
缓存管理器

管理 Postback 转发相关的缓存数据
"""
import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import Publisher, Offer, Product
from app.core.infrastructure.cache_compat import (
    generate_cache_key,
    legacy_get_cached as get_cached,
    legacy_set_cached as set_cached,
    _legacy_storage_key,
)
from app.core.infrastructure.cache import get_cache_backend

logger = logging.getLogger(__name__)


class CacheManager:
    """缓存管理器"""
    
    @staticmethod
    async def get_cached_publisher(publisher_id: int, db: AsyncSession) -> Optional[Publisher]:
        """
        获取渠道信息（带旁路缓存快照）。

        始终以数据库行为准，避免 is_active / postback_url 更新后被旧缓存 setattr 覆盖。
        """
        cache_key = generate_cache_key("publisher", publisher_id)

        result = await db.execute(
            select(Publisher).where(Publisher.id == publisher_id)
        )
        publisher = result.scalars().first()

        if publisher:
            try:
                publisher_data = {
                    "id": publisher.id,
                    "publisher_name": publisher.publisher_name,
                    "postback_url": publisher.postback_url,
                    "postback_method": publisher.postback_method,
                    "postback_success_check": publisher.postback_success_check,
                    "is_active": publisher.is_active,
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

    @staticmethod
    async def get_cached_product(product_id: int, db: AsyncSession) -> Optional[Product]:
        """
        获取产品信息（带旁路缓存快照）。

        始终以数据库行为准，避免 is_active / downstream_postback_* 被旧缓存覆盖。
        """
        cache_key = generate_cache_key("product", product_id)

        result = await db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalars().first()

        if product:
            try:
                product_data = {
                    "id": product.id,
                    "name": product.name,
                    "is_active": product.is_active,
                    "downstream_postback_url": product.downstream_postback_url,
                    "downstream_postback_method": product.downstream_postback_method,
                    "downstream_postback_success_check": product.downstream_postback_success_check,
                }
                await set_cached(cache_key, product_data, ttl=300, key_prefix="postback_forward")
            except Exception as e:
                logger.debug(f"缓存 Product 信息失败：{str(e)}")

        return product

    @staticmethod
    async def invalidate_product(product_id: int) -> None:
        """产品更新/删除后失效转发缓存。"""
        try:
            cache = await get_cache_backend()
            key = _legacy_storage_key(generate_cache_key("product", product_id))
            await cache.delete(key)
        except Exception as e:
            logger.debug("失效产品转发缓存失败: product_id=%s err=%s", product_id, e)

    @staticmethod
    async def invalidate_publisher(publisher_id: int) -> None:
        """渠道更新后失效转发缓存。"""
        try:
            cache = await get_cache_backend()
            key = _legacy_storage_key(generate_cache_key("publisher", publisher_id))
            await cache.delete(key)
        except Exception as e:
            logger.debug("失效渠道转发缓存失败: publisher_id=%s err=%s", publisher_id, e)
