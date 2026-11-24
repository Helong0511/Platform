"""
统一缓存管理模块。

职责：短链/Offer 预热、按标签批量失效、维护 Redis 标签→键映射，供管理端与定时任务使用。

在系统中的位置：``app.core.cache_manager.CacheManager``，协调 ``offer_cache`` 与 ``short_link_cache``。
"""
import logging
import secrets
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.redis_client import get_redis_client
from app.core.offer_cache import (
    get_offer_cache_entry,
    invalidate_offer_cache,
)
from app.core.short_link_cache import (
    get_short_link_from_cache,
    serialize_short_link,
    set_short_link_to_cache,
)
from app.models.models import ShortLink

logger = logging.getLogger(__name__)

# 标签到键的映射前缀
TAG_TO_KEYS_PREFIX = "tag_keys:"
TAG_BATCHES_PREFIX = "tag_batches:"
TAG_BATCH_PREFIX = "tag_batch:"

# 先登记恢复索引、再持久化活动集合、最后轮转；RENAME 后不再执行写命令。
# Redis Lua 遇到运行时命令错误不会回滚此前写入，因此必须保证 RENAME 成功前
# 活动集合仍在原位置，且批次索引已预登记。中途失败最多留下可清理的悬空索引，
# 不会出现已轮转批次没有 pending 索引、或成员集合因 TTL 到期而丢失的窗口。
_ROTATE_TAG_BATCH_LUA = """
local active_key = KEYS[1]
local pending_key = KEYS[2]
local batch_key = ARGV[1]
if redis.call('EXISTS', active_key) == 1 then
    redis.call('SADD', pending_key, batch_key)
    redis.call('PERSIST', active_key)
    redis.call('RENAME', active_key, batch_key)
end
return redis.call('SMEMBERS', pending_key)
"""

# 仅当批次确实为空时才清理批次及 pending 索引；并发 Worker 可安全重复执行。
_FINALIZE_TAG_BATCH_LUA = """
local batch_key = KEYS[1]
local pending_key = KEYS[2]
if redis.call('SCARD', batch_key) ~= 0 then
    return 0
end
redis.call('DEL', batch_key)
redis.call('SREM', pending_key, batch_key)
if redis.call('SCARD', pending_key) == 0 then
    redis.call('DEL', pending_key)
end
return 1
"""

_ADD_TAG_MEMBER_LUA = """
redis.call('SADD', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""


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
        """Offer 热点缓存没有业务读取者，禁用写入并保留接口兼容。"""
        logger.info("跳过 Offer 缓存预热：短链解析直接使用数据库权威数据")
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
        """原子添加标签成员并刷新活动集合 TTL。"""
        redis = await get_redis_client()
        if not redis:
            return False

        try:
            for tag in set(tags):
                tag_key = f"{TAG_TO_KEYS_PREFIX}{tag}"
                await redis.eval(
                    _ADD_TAG_MEMBER_LUA,
                    1,
                    tag_key,
                    cache_key,
                    7 * 24 * 3600,
                )
            return True
        except Exception as e:
            logger.warning(
                "添加缓存标签失败: cache_key=%s, tags=%s, error=%s",
                cache_key,
                tags,
                e,
            )
            return False

    @staticmethod
    async def invalidate_by_tag(tag: str) -> int:
        """按标签失效缓存；批次轮转和恢复索引具备原子性与崩溃恢复能力。

        活动集合通过 Lua 原子 RENAME 为不可变批次并写入持久 pending 索引。
        Worker 删除成员成功后才 SREM；若进程在 DEL 后、SREM 前崩溃，重试
        DEL 不存在的键是幂等操作，随后仍可移除成员。并发 Worker 可重复处理
        同一批次，不会因一个 Worker 清理索引而丢失另一个 Worker 新增的成员。
        """
        redis = await get_redis_client()
        if not redis:
            return 0

        active_key = f"{TAG_TO_KEYS_PREFIX}{tag}"
        pending_key = f"{TAG_BATCHES_PREFIX}{tag}"
        batch_key = f"{TAG_BATCH_PREFIX}{secrets.token_hex(16)}"
        deleted_count = 0

        try:
            batches = await redis.eval(
                _ROTATE_TAG_BATCH_LUA,
                2,
                active_key,
                pending_key,
                batch_key,
            )

            for raw_batch_key in batches or []:
                current_batch_key = (
                    raw_batch_key.decode("utf-8")
                    if isinstance(raw_batch_key, bytes)
                    else str(raw_batch_key)
                )
                try:
                    members = await redis.smembers(current_batch_key)
                except Exception as e:
                    logger.warning(
                        "读取缓存标签批次失败: tag=%s, batch=%s, error=%s",
                        tag,
                        current_batch_key,
                        e,
                    )
                    continue

                for cache_key in members:
                    try:
                        # DEL 返回 0 表示键已不存在，也属于已完成失效。
                        deleted_count += int(await redis.delete(cache_key) or 0)
                        await redis.srem(current_batch_key, cache_key)
                    except Exception as e:
                        # 删除或确认成员移除失败时保留该成员，供后续 Worker 重试。
                        logger.warning(
                            "删除缓存标签成员失败，保留批次供重试: tag=%s, cache_key=%s, error=%s",
                            tag,
                            cache_key,
                            e,
                        )

                try:
                    await redis.eval(
                        _FINALIZE_TAG_BATCH_LUA,
                        2,
                        current_batch_key,
                        pending_key,
                    )
                except Exception as e:
                    logger.warning(
                        "完成缓存标签批次清理失败: tag=%s, batch=%s, error=%s",
                        tag,
                        current_batch_key,
                        e,
                    )

            logger.info(
                "按标签清除缓存: tag=%s, 清除 %s 个缓存键",
                tag,
                deleted_count,
            )
            return deleted_count
        except Exception as e:
            logger.warning("按标签清除缓存失败: tag=%s, error=%s", tag, e)
            return deleted_count

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
        cache_entry = await get_offer_cache_entry(offer_id)
        if cache_entry.status != "hit" or cache_entry.advertiser_id is None:
            return None
        return {"advertiser_id": cache_entry.advertiser_id}

