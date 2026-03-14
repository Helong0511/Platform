"""
转发缓存主动失效模块

在 Publisher/Offer 更新时主动失效缓存，确保数据一致性
"""
import logging
from typing import Optional

from app.core.infrastructure.cache import get_cache_backend
from app.core.infrastructure.cache_compat import set_cached

logger = logging.getLogger(__name__)


class ForwardingCacheInvalidator:
    """转发缓存失效器"""
    
    @staticmethod
    async def invalidate_publisher(publisher_id: int) -> bool:
        """
        失效 Publisher 缓存
        
        Args:
            publisher_id: Publisher ID
        
        Returns:
            bool: 是否成功
        """
        cache = await get_cache_backend()
        cache_key = f"publisher:{publisher_id}"
        
        try:
            await cache.delete(cache_key)
            logger.info(f"Publisher 缓存已失效：publisher_id={publisher_id}")
            return True
        except Exception as e:
            logger.error(f"失效 Publisher 缓存失败：publisher_id={publisher_id}, error={e}")
            return False
    
    @staticmethod
    async def invalidate_offer(offer_id: int) -> bool:
        """
        失效 Offer 缓存
        
        Args:
            offer_id: Offer ID
        
        Returns:
            bool: 是否成功
        """
        cache = await get_cache_backend()
        cache_key = f"offer:{offer_id}"
        
        try:
            await cache.delete(cache_key)
            logger.info(f"Offer 缓存已失效：offer_id={offer_id}")
            return True
        except Exception as e:
            logger.error(f"失效 Offer 缓存失败：offer_id={offer_id}, error={e}")
            return False
    
    @staticmethod
    async def invalidate_by_client(client_id: int) -> bool:
        """
        失效客户相关的所有缓存
        
        Args:
            client_id: 客户 ID
        
        Returns:
            bool: 是否成功
        """
        cache = await get_cache_backend()
        
        try:
            # 失效模式匹配的所有 Key
            patterns = [
                f"publisher:*:client:{client_id}",
                f"offer:*:client:{client_id}"
            ]
            
            deleted_count = 0
            for pattern in patterns:
                deleted_count += await cache.delete_pattern(pattern)
            
            logger.info(f"客户缓存已失效：client_id={client_id}, deleted={deleted_count}")
            return True
            
        except Exception as e:
            logger.error(f"失效客户缓存失败：client_id={client_id}, error={e}")
            return False


class ForwardingCacheMetrics:
    """转发缓存指标"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.publisher_hits = 0
            cls._instance.publisher_misses = 0
            cls._instance.offer_hits = 0
            cls._instance.offer_misses = 0
        return cls._instance
    
    def record_publisher_hit(self):
        """记录 Publisher 缓存命中"""
        self.publisher_hits += 1
    
    def record_publisher_miss(self):
        """记录 Publisher 缓存未命中"""
        self.publisher_misses += 1
    
    def record_offer_hit(self):
        """记录 Offer 缓存命中"""
        self.offer_hits += 1
    
    def record_offer_miss(self):
        """记录 Offer 缓存未命中"""
        self.offer_misses += 1
    
    @property
    def publisher_hit_rate(self) -> float:
        """Publisher 缓存命中率"""
        total = self.publisher_hits + self.publisher_misses
        return self.publisher_hits / total if total > 0 else 0.0
    
    @property
    def offer_hit_rate(self) -> float:
        """Offer 缓存命中率"""
        total = self.offer_hits + self.offer_misses
        return self.offer_hits / total if total > 0 else 0.0
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'publisher_hits': self.publisher_hits,
            'publisher_misses': self.publisher_misses,
            'publisher_hit_rate': round(self.publisher_hit_rate * 100, 2),
            'offer_hits': self.offer_hits,
            'offer_misses': self.offer_misses,
            'offer_hit_rate': round(self.offer_hit_rate * 100, 2),
        }
    
    def reset(self):
        """重置统计"""
        self.publisher_hits = 0
        self.publisher_misses = 0
        self.offer_hits = 0
        self.offer_misses = 0


def get_forwarding_metrics() -> ForwardingCacheMetrics:
    """获取转发缓存指标实例"""
    return ForwardingCacheMetrics()
