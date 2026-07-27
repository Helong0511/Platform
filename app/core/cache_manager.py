"""
统一缓存管理模块。

职责：短链/Offer 预热、按标签批量失效、维护 Redis 标签→键映射，供管理端与定时任务使用。

在系统中的位置：``app.core.cache_manager.CacheManager``，协调 ``offer_cache`` 与 ``short_link_cache``。
"""
import logging
from typing import Optional, List, Dict, Any

from app.core.redis_client import get_redis_client
from app.core.offer_cache import set_offer_cache, get_offer_advertiser_id, invalidate_offer_cache
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

logger = logging.getLogger(__name__)

# 标签到键的映射前缀
TAG_TO_KEYS_PREFIX = "tag_keys:"


class CacheManager:
    """缓存管理器，提供缓存预热、精确失效等功能"""
    
    @staticmethod
    async def warmup_short_links(db: AsyncSession, limit: int = 100) -> int:
        """
        预热短链接缓存
        
        加载最近访问或活跃的短链接到缓存中，提高缓存命中率
        
        Args:
            db: 数据库会话
            limit: 预热的短链接数量
            
        Returns:
            成功预热的数量
        """
        try:
            # 延迟导入，避免 lifespan 启动阶段与 models 循环依赖导致 NameError
            from app.models.postback import ShortLink
            from app.core.short_link_cache import (
                get_short_link_from_cache,
                serialize_short_link,
                set_short_link_to_cache,
            )

            result = await db.execute(
                select(ShortLink)
                .where(ShortLink.is_active.is_(True))
                .order_by(ShortLink.click_count.desc(), ShortLink.id.desc())
                .limit(limit)
            )
            short_links = result.scalars().all()
            
            warmed_count = 0
            for short_link in short_links:
                try:
                    cached = await get_short_link_from_cache(short_link.short_code)
                    if not cached:
                        written = await set_short_link_to_cache(
                            short_link.short_code,
                            serialize_short_link(short_link),
                        )
                        if written:
                            warmed_count += 1
                except Exception as e:
                    logger.warning(
                        "预热短链接失败: short_code=%s, error=%s",
                        getattr(short_link, "short_code", "unknown"),
                        e,
                    )
            
            logger.info(
                "短链接缓存预热完成: 实际写入 %s/%s 个短链接",
                warmed_count,
                len(short_links),
            )
            return warmed_count
        except Exception as e:
            logger.error(f"短链接缓存预热失败: {e}", exc_info=True)
            return 0
    
    @staticmethod
    async def warmup_offers(db: AsyncSession, limit: int = 50) -> int:
        """
        预热Offer缓存
        
        加载活跃的Offer到缓存中
        
        Args:
            db: 数据库会话
            limit: 预热的Offer数量
            
        Returns:
            成功预热的数量
        """
        try:
            # 延迟导入，避免 lifespan 启动阶段与 models 循环依赖导致 NameError
            from app.models.cpl import Offer

            # 查询活跃的Offer
            result = await db.execute(
                select(Offer)
                .where(
                    Offer.status == "Active",
                    Offer.is_active.is_(True),
                )
                .order_by(Offer.id.desc())
                .limit(limit)
            )
            offers = result.scalars().all()
            
            warmed_count = 0
            for offer in offers:
                try:
                    # 检查是否已在缓存中
                    cached = await CacheManager.get_offer_cache(offer.id)
                    if not cached:
                        written = await set_offer_cache(
                            offer.id,
                            offer.advertiser_id,
                            offer.offer_name,
                        )
                        if written:
                            warmed_count += 1
                except Exception as e:
                    logger.warning(f"预热Offer失败: offer_id={offer.id}, error={e}")
            
            logger.info(
                "Offer缓存预热完成: 实际写入 %s/%s 个Offer",
                warmed_count,
                len(offers),
            )
            return warmed_count
        except Exception as e:
            logger.error(f"Offer缓存预热失败: {e}", exc_info=True)
            return 0
    
    @staticmethod
    async def warmup_all(db: AsyncSession) -> Dict[str, int]:
        """
        预热所有缓存
        
        Args:
            db: 数据库会话
            
        Returns:
            预热结果统计
        """
        logger.info("开始缓存预热...")
        
        results = {
            'short_links': 0,
            'offers': 0
        }

        redis = await get_redis_client()
        if not redis:
            logger.info("Redis 不可用，跳过短链接/Offer 缓存预热")
            return results
        
        # 预热短链接
        results['short_links'] = await CacheManager.warmup_short_links(db)
        
        # 预热Offer
        results['offers'] = await CacheManager.warmup_offers(db)
        
        logger.info(f"缓存预热完成: {results}")
        return results
    
    @staticmethod
    async def add_cache_tag(cache_key: str, tags: List[str]) -> bool:
        """
        为缓存键添加标签
        
        标签用于精确失效，可以按标签批量清除相关缓存
        
        Args:
            cache_key: 缓存键
            tags: 标签列表
            
        Returns:
            是否添加成功
        """
        redis = await get_redis_client()
        if not redis:
            return False
        
        try:
            # 为每个标签维护一个键集合
            for tag in tags:
                tag_key = f"{TAG_TO_KEYS_PREFIX}{tag}"
                await redis.sadd(tag_key, cache_key)
                # 设置标签键的过期时间（7天）
                await redis.expire(tag_key, 7 * 24 * 3600)
            
            return True
        except Exception as e:
            logger.warning(f"添加缓存标签失败: cache_key={cache_key}, tags={tags}, error={e}")
            return False
    
    @staticmethod
    async def invalidate_by_tag(tag: str) -> int:
        """
        按标签清除缓存
        
        清除所有带有指定标签的缓存键
        
        Args:
            tag: 标签名称
            
        Returns:
            清除的缓存数量
        """
        redis = await get_redis_client()
        if not redis:
            return 0
        
        try:
            tag_key = f"{TAG_TO_KEYS_PREFIX}{tag}"
            # 获取所有带此标签的缓存键
            cache_keys = await redis.smembers(tag_key)
            
            if not cache_keys:
                return 0
            
            # 删除所有缓存键
            deleted_count = 0
            for cache_key in cache_keys:
                try:
                    if await redis.delete(cache_key):
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"删除缓存键失败: {cache_key}, error={e}")
            
            # 删除标签键
            await redis.delete(tag_key)
            
            logger.info(f"按标签清除缓存: tag={tag}, 清除 {deleted_count} 个缓存键")
            return deleted_count
        except Exception as e:
            logger.warning(f"按标签清除缓存失败: tag={tag}, error={e}")
            return 0
    
    @staticmethod
    async def invalidate_by_tags(tags: List[str]) -> int:
        """
        按多个标签清除缓存
        
        Args:
            tags: 标签列表
            
        Returns:
            清除的缓存总数
        """
        total_deleted = 0
        for tag in tags:
            total_deleted += await CacheManager.invalidate_by_tag(tag)
        return total_deleted
    
    @staticmethod
    async def invalidate_short_link_related(short_code: str) -> bool:
        """
        清除短链接相关的所有缓存
        
        包括短链接本身和相关的Offer缓存
        
        Args:
            short_code: 短链接代码
            
        Returns:
            是否清除成功
        """
        try:
            # 延迟导入，避免循环导入
            from app.core.short_link_cache import invalidate_short_link_cache
            
            # 清除短链接缓存
            await invalidate_short_link_cache(short_code)
            
            # 清除相关标签的缓存
            await CacheManager.invalidate_by_tag(f"short_link:{short_code}")
            
            return True
        except Exception as e:
            logger.warning(f"清除短链接相关缓存失败: short_code={short_code}, error={e}")
            return False
    
    @staticmethod
    async def invalidate_offer_related(offer_id: int) -> bool:
        """
        清除Offer相关的所有缓存
        
        Args:
            offer_id: Offer ID
            
        Returns:
            是否清除成功
        """
        try:
            # 清除Offer缓存
            await invalidate_offer_cache(offer_id)
            
            # 清除相关标签的缓存
            await CacheManager.invalidate_by_tag(f"offer:{offer_id}")
            
            return True
        except Exception as e:
            logger.warning(f"清除Offer相关缓存失败: offer_id={offer_id}, error={e}")
            return False
    
    @staticmethod
    async def get_offer_cache(offer_id: int) -> Optional[Dict[str, Any]]:
        """
        获取Offer缓存（用于检查缓存是否存在）
        
        Args:
            offer_id: Offer ID
            
        Returns:
            缓存的Offer信息，如果不存在则返回None
        """
        advertiser_id = await get_offer_advertiser_id(offer_id)
        if advertiser_id:
            return {"advertiser_id": advertiser_id}
        return None

