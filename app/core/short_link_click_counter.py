"""
短链接点击次数异步更新模块
使用Redis计数器异步批量更新点击次数，减少数据库压力
"""
import logging
import asyncio
from typing import Dict
from datetime import datetime, timezone
from app.core.redis_client import get_redis_client
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.models import ShortLink

logger = logging.getLogger(__name__)

# Redis键前缀
CLICK_COUNTER_PREFIX = "short_link:click:"
# 批量更新阈值：每10次点击或每5秒更新一次
BATCH_UPDATE_THRESHOLD = 10
BATCH_UPDATE_INTERVAL = 5  # 秒

# 全局计数器缓存（进程内）
_click_counters: Dict[str, int] = {}
_last_update_time: Dict[str, float] = {}


async def increment_click_count_async(short_code: str) -> None:
    """
    异步增加点击次数（使用Redis计数器）
    
    Args:
        short_code: 短链接代码
    """
    redis = await get_redis_client()
    if not redis:
        # Redis不可用时，使用进程内计数器
        old_count = _click_counters.get(short_code, 0)
        _click_counters[short_code] = old_count + 1
        new_count = _click_counters[short_code]
        logger.info(
            f"短链接点击计数（进程内）: short_code={short_code}, "
            f"旧值={old_count}, 新值={new_count}"
        )
        return
    
    try:
        # 使用Redis原子递增
        counter_key = f"{CLICK_COUNTER_PREFIX}{short_code}"
        new_count = await redis.incr(counter_key)
        # 设置过期时间（48小时）
        await redis.expire(counter_key, 48 * 3600)
        logger.info(
            f"短链接点击计数（Redis）: short_code={short_code}, "
            f"计数器键={counter_key}, 当前值={new_count}"
        )
    except Exception as e:
        logger.warning(f"Redis点击计数递增失败: short_code={short_code}, error={e}")
        # 降级到进程内计数器
        old_count = _click_counters.get(short_code, 0)
        _click_counters[short_code] = old_count + 1
        new_count = _click_counters[short_code]
        logger.info(
            f"短链接点击计数（降级到进程内）: short_code={short_code}, "
            f"旧值={old_count}, 新值={new_count}"
        )


async def sync_click_counts_to_db(db: AsyncSession, short_codes: list[str] = None) -> int:
    """
    将Redis中的点击次数同步到数据库
    
    Args:
        db: 数据库会话
        short_codes: 要同步的短链接代码列表，如果为None则同步所有
        
    Returns:
        同步的记录数
    """
    redis = await get_redis_client()
    if not redis:
        # Redis不可用时，同步进程内计数器
        if not _click_counters:
            logger.debug("进程内计数器为空，无需同步")
            return 0
        
        logger.info(f"Redis不可用，同步进程内计数器: {len(_click_counters)} 个短链接")
        
        synced = 0
        failed_codes = []  # 记录同步失败的短链接代码
        
        for short_code, count in _click_counters.items():
            if short_codes and short_code not in short_codes:
                continue
            
            try:
                result = await db.execute(
                    select(ShortLink).where(ShortLink.short_code == short_code)
                )
                short_link = result.scalars().first()
                if short_link:
                    old_count = short_link.click_count
                    short_link.click_count += count
                    new_count = short_link.click_count
                    
                    logger.debug(
                        f"更新短链接点击次数（进程内）: short_code={short_code}, "
                        f"旧值={old_count}, 增量={count}, 新值={new_count}"
                    )
                    synced += 1
                else:
                    logger.warning(f"短链接不存在（进程内）: short_code={short_code}")
            except Exception as e:
                logger.error(
                    f"同步点击次数失败（进程内）: short_code={short_code}, error={e}",
                    exc_info=True
                )
                failed_codes.append(short_code)
        
        # 提交所有成功的更新
        if synced > 0:
            try:
                await db.commit()
                logger.info(f"成功同步 {synced} 个短链接的点击次数到数据库（进程内）")
            except Exception as e:
                logger.error(f"提交数据库事务失败（进程内）: {e}", exc_info=True)
                await db.rollback()
                synced = 0
        
        # 只清空成功同步的计数器
        if synced > 0:
            if short_codes:
                # 只清空指定列表中成功同步的
                for code in short_codes:
                    if code not in failed_codes:
                        _click_counters.pop(code, None)
            else:
                # 清空所有成功同步的，但保留失败的
                for code in list(_click_counters.keys()):
                    if code not in failed_codes:
                        _click_counters.pop(code, None)
        
        if failed_codes:
            logger.warning(f"有 {len(failed_codes)} 个短链接同步失败，将在下次同步时重试")
        
        return synced
    
    try:
        # 获取所有计数器键
        pattern = f"{CLICK_COUNTER_PREFIX}*"
        keys = await redis.keys(pattern)
        
        if not keys:
            logger.debug("没有需要同步的短链接点击计数器")
            return 0
        
        logger.info(f"找到 {len(keys)} 个短链接点击计数器需要同步")
        
        synced = 0
        failed_keys = []  # 记录同步失败的键，稍后重试
        
        for key in keys:
            short_code = key.replace(CLICK_COUNTER_PREFIX, "")
            if short_codes and short_code not in short_codes:
                continue
            
            try:
                # 先获取计数器值（不删除）
                count = await redis.get(key)
                if not count or int(count) <= 0:
                    # 计数器为0或不存在，直接删除
                    await redis.delete(key)
                    continue
                
                count_value = int(count)
                logger.info(f"准备同步短链接点击次数: short_code={short_code}, count={count_value}")
                
                # 更新数据库
                result = await db.execute(
                    select(ShortLink).where(ShortLink.short_code == short_code)
                )
                short_link = result.scalars().first()
                
                if short_link:
                    # 更新点击次数
                    old_count = short_link.click_count
                    short_link.click_count += count_value
                    new_count = short_link.click_count
                    
                    logger.info(
                        f"✅ 更新短链接点击次数: short_code={short_code}, "
                        f"旧值={old_count}, 增量={count_value}, 新值={new_count}"
                    )
                    
                    # 数据库更新成功后才删除Redis中的计数器（避免数据丢失）
                    await redis.delete(key)
                    synced += 1
                else:
                    # 短链接不存在，删除计数器
                    logger.warning(f"短链接不存在，删除计数器: short_code={short_code}")
                    await redis.delete(key)
                    
            except Exception as e:
                # 同步失败，保留计数器以便下次重试
                logger.error(
                    f"同步点击次数失败: short_code={short_code}, key={key}, error={e}",
                    exc_info=True
                )
                failed_keys.append(key)
        
        # 提交所有成功的更新
        if synced > 0:
            try:
                await db.commit()
                logger.info(f"成功同步 {synced} 个短链接的点击次数到数据库")
            except Exception as e:
                logger.error(f"提交数据库事务失败: {e}", exc_info=True)
                await db.rollback()
                # 注意：这里已经删除了Redis中的计数器，但数据库更新失败
                # 这是数据不一致的情况，需要记录警告
                logger.warning(
                    f"警告：已删除 {synced} 个Redis计数器，但数据库更新失败。"
                    f"可能导致点击次数丢失。"
                )
                synced = 0
        
        if failed_keys:
            logger.warning(f"有 {len(failed_keys)} 个计数器同步失败，将在下次同步时重试")
        
        return synced
    except Exception as e:
        logger.error(f"同步点击次数到数据库失败: {e}", exc_info=True)
        return 0

