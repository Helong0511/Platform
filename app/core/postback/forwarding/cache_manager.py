"""
Postback 转发数据读取与历史缓存清理。

Publisher、Offer、Product 均以当前数据库事务中的 ORM 数据为权威来源。
Publisher/Product 旧实现只在数据库读取后写入 Redis，从未从该键读取，
会产生无效写放大；因此读取路径不再写入旁路快照。
历史键清理方法暂时保留，便于清除升级前遗留的缓存数据。
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import Publisher, Offer, Product
from app.core.infrastructure.cache_compat import (
    generate_cache_key,
    _legacy_storage_key,
)
from app.core.infrastructure.cache import get_cache_backend

logger = logging.getLogger(__name__)


class CacheManager:
    """Postback 转发数据访问管理器。"""

    @staticmethod
    async def get_cached_publisher(
        publisher_id: int,
        db: AsyncSession,
    ) -> Optional[Publisher]:
        """从当前数据库会话读取 Publisher，禁止写入无读取者的缓存快照。"""
        result = await db.execute(
            select(Publisher).where(Publisher.id == publisher_id)
        )
        return result.scalars().first()

    @staticmethod
    async def get_cached_offer(
        offer_id: int,
        db: AsyncSession,
    ) -> Optional[Offer]:
        """从数据库读取 Offer 权威数据，不能用缓存快照覆盖 ORM 实体。"""
        result = await db.execute(
            select(Offer).where(Offer.id == offer_id)
        )
        return result.scalars().first()

    @staticmethod
    async def get_cached_product(
        product_id: int,
        db: AsyncSession,
    ) -> Optional[Product]:
        """从当前数据库会话读取 Product，禁止写入无读取者的缓存快照。"""
        result = await db.execute(
            select(Product).where(Product.id == product_id)
        )
        return result.scalars().first()

    @staticmethod
    async def invalidate_product(product_id: int) -> None:
        """清理旧版本遗留的 Product 转发缓存键；不代表当前读取路径使用缓存。"""
        try:
            cache = await get_cache_backend()
            key = _legacy_storage_key(generate_cache_key("product", product_id))
            await cache.delete(key)
        except Exception as exc:
            logger.debug(
                "清理历史 Product 转发缓存失败: product_id=%s error_type=%s",
                product_id,
                type(exc).__name__,
            )

    @staticmethod
    async def invalidate_publisher(publisher_id: int) -> None:
        """清理旧版本遗留的 Publisher 转发缓存键；不代表当前读取路径使用缓存。"""
        try:
            cache = await get_cache_backend()
            key = _legacy_storage_key(generate_cache_key("publisher", publisher_id))
            await cache.delete(key)
        except Exception as exc:
            logger.debug(
                "清理历史 Publisher 转发缓存失败: publisher_id=%s error_type=%s",
                publisher_id,
                type(exc).__name__,
            )
