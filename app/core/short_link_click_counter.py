"""
短链接点击次数异步更新模块
使用Redis计数器异步批量更新点击次数，减少数据库压力
"""
import logging
import asyncio
import random
from typing import Dict, List, Tuple
from datetime import datetime, timezone
from app.core.redis_client import get_redis_client
from app.core.short_link_cache import invalidate_short_link_cache
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, text
from sqlalchemy.exc import OperationalError
from app.models.models import ShortLink
import uuid

logger = logging.getLogger(__name__)

# 死锁重试配置
MAX_DEADLOCK_RETRIES = 5  # 增加重试次数
DEADLOCK_RETRY_BASE_DELAY = 0.3  # 增加基础延迟（秒），减少并发冲突
MAX_RECURSION_DEPTH = 10  # 批次拆分最大递归深度，防止栈溢出（批次大小5最多递归3次）

# 死锁统计（用于监控）
_deadlock_stats = {
    "total_deadlocks": 0,
    "deadlocks_by_batch_size": {},
    "last_deadlock_time": None,
}

# 死锁统计的异步锁（保护并发访问）
_deadlock_stats_lock = asyncio.Lock()

# Redis键前缀
CLICK_COUNTER_PREFIX = "short_link:click:"
SYNC_LOCK_PREFIX = "short_link:sync_lock:"  # 分布式锁前缀（全局同步锁）
SYNC_LOCK_TIMEOUT = 300  # 锁超时时间（秒），5分钟
ITEM_LOCK_PREFIX = "short_link:item_lock:"  # 细粒度分布式锁前缀（每个short_code一个锁）
ITEM_LOCK_TIMEOUT = 10  # 细粒度锁超时时间（秒），10秒足够完成单个更新


async def cleanup_click_counter(short_code: str) -> bool:
    """
    清理短链接的Redis计数器（当短链接被删除时调用）
    
    Args:
        short_code: 短链接代码
        
    Returns:
        是否清理成功
    """
    redis = await get_redis_client()
    if not redis:
        return False
    
    try:
        counter_key = f"{CLICK_COUNTER_PREFIX}{short_code}"
        deleted = await redis.delete(counter_key)
        if deleted:
            logger.debug(f"成功清理短链接Redis计数器: short_code={short_code}")
        return True
    except Exception as e:
        logger.warning(f"清理短链接Redis计数器失败: short_code={short_code}, error={e}")
        return False

# Lua脚本：原子获取计数器值（不删除，避免数据丢失）
# 返回：如果键存在且值>0，返回计数值；否则返回0
# 注意：不再删除键，只有在数据库更新成功后才删除，确保数据不丢失
_GET_COUNTER_LUA = """
local val = redis.call('GET', KEYS[1])
if val and tonumber(val) > 0 then
    return tonumber(val)
else
    return 0
end
"""

# Lua脚本：原子获取并删除计数器值（已废弃，保留用于兼容）
# 注意：此脚本会导致数据丢失风险，已改用_GET_COUNTER_LUA
_GET_AND_DELETE_COUNTER_LUA = """
local val = redis.call('GET', KEYS[1])
if val and tonumber(val) > 0 then
    redis.call('DEL', KEYS[1])
    return tonumber(val)
else
    if val then
        redis.call('DEL', KEYS[1])
    end
    return 0
end
"""

# 批量更新阈值：每10次点击或每5秒更新一次
# 注意：这些配置目前未使用，系统使用定时任务（每5分钟）进行同步
# 保留这些配置以便未来实现基于阈值的自动同步功能
BATCH_UPDATE_THRESHOLD = 10
BATCH_UPDATE_INTERVAL = 5  # 秒

# 全局计数器缓存（进程内）
_click_counters: Dict[str, int] = {}
# 注意：_last_update_time 目前未使用，保留用于未来实现基于时间的自动同步功能
_last_update_time: Dict[str, float] = {}

# 进程内计数器的异步锁（保护并发访问）
_counter_lock = asyncio.Lock()


async def increment_click_count_async(short_code: str) -> None:
    """
    异步增加点击次数（使用Redis计数器）
    
    Args:
        short_code: 短链接代码
    """
    redis = await get_redis_client()
    if not redis:
        # Redis不可用时，使用进程内计数器
        # 使用异步锁保护并发访问，确保计数准确性
        async with _counter_lock:
            old_count = _click_counters.get(short_code, 0)
            _click_counters[short_code] = old_count + 1
            new_count = _click_counters[short_code]
        # 使用debug级别，避免高频点击时产生大量日志
        logger.debug(
            f"短链接点击计数（进程内）: short_code={short_code}, "
            f"旧值={old_count}, 新值={new_count}"
        )
        return
    
    try:
        # 使用Redis原子递增
        counter_key = f"{CLICK_COUNTER_PREFIX}{short_code}"
        new_count = await redis.incr(counter_key)
        # 设置过期时间（48小时）- 如果失败不影响计数，但记录警告
        try:
            await redis.expire(counter_key, 48 * 3600)
        except Exception as expire_error:
            logger.warning(
                f"设置Redis计数器过期时间失败（不影响计数）: "
                f"short_code={short_code}, key={counter_key}, error={expire_error}"
            )
        # 使用debug级别，避免高频点击时产生大量日志
        logger.debug(
            f"短链接点击计数（Redis）: short_code={short_code}, "
            f"计数器键={counter_key}, 当前值={new_count}"
        )
    except Exception as e:
        logger.warning(f"Redis点击计数递增失败: short_code={short_code}, error={e}")
        # 降级到进程内计数器
        # 使用异步锁保护并发访问，确保计数准确性
        async with _counter_lock:
            old_count = _click_counters.get(short_code, 0)
            _click_counters[short_code] = old_count + 1
            new_count = _click_counters[short_code]
        # 使用debug级别，避免高频点击时产生大量日志
        logger.debug(
            f"短链接点击计数（降级到进程内）: short_code={short_code}, "
            f"旧值={old_count}, 新值={new_count}"
        )


async def sync_click_counts_to_db(db: AsyncSession, short_codes: list[str] = None) -> int:
    """
    将Redis中的点击次数同步到数据库
    
    使用分布式锁确保同一时间只有一个进程在执行同步，避免并发死锁
    
    Args:
        db: 数据库会话
        short_codes: 要同步的短链接代码列表，如果为None则同步所有
        
    Returns:
        同步的记录数
    """
    redis = await get_redis_client()
    
    # 使用分布式锁，确保同一时间只有一个进程在执行同步
    lock_key = f"{SYNC_LOCK_PREFIX}global"
    lock_value = str(uuid.uuid4())
    lock_acquired = False
    
    try:
        # 尝试获取分布式锁（如果Redis可用）
        if redis:
            # 使用 SET key value NX EX timeout 实现分布式锁
            lock_acquired = await redis.set(
                lock_key, 
                lock_value, 
                nx=True,  # 只在键不存在时设置
                ex=SYNC_LOCK_TIMEOUT  # 设置过期时间，防止死锁
            )
            
            if not lock_acquired:
                logger.info("另一个进程正在执行同步，跳过本次同步以避免并发死锁")
                return 0
            else:
                logger.debug("成功获取同步锁，开始执行同步")
    except Exception as e:
        logger.warning(f"获取分布式锁失败，继续执行同步（可能发生并发）: {e}")
        # 如果获取锁失败，仍然继续执行（降级处理）
    
    try:
        if not redis:
            # Redis不可用时，同步进程内计数器
            # 使用异步锁保护并发访问
            async with _counter_lock:
                if not _click_counters:
                    logger.debug("进程内计数器为空，无需同步")
                    return 0
                
                # 收集需要更新的数据，按 short_code 排序（统一锁顺序，避免死锁）
                updates: List[Tuple[str, int]] = []
                for short_code, count in _click_counters.items():
                    if short_codes and short_code not in short_codes:
                        continue
                    if count > 0:
                        updates.append((short_code, count))
            
            if not updates:
                logger.debug("没有需要同步的进程内计数器")
                return 0
            
            logger.info(f"Redis不可用，同步进程内计数器: {len(updates)} 个短链接")
            
            # 按 short_code 排序，确保所有进程以相同顺序锁定记录
            updates = sorted(updates, key=lambda x: x[0])
            
            # 使用批量更新，减少死锁风险
            synced = 0
            failed_codes = []  # 记录同步失败的短链接代码
            
            # 第一步：预先验证短链接是否存在，不存在的直接清理（避免无效重试）
            short_codes_to_check = [code for code, _ in updates]
            existing_codes = set()
            try:
                result = await db.execute(
                    select(ShortLink.short_code, ShortLink.is_active).where(
                        ShortLink.short_code.in_(short_codes_to_check)
                    )
                )
                existing_links = result.fetchall()
                existing_codes = {row[0] for row in existing_links if row[1]}  # 只包含激活的短链接
            except Exception as e:
                logger.warning(f"预验证短链接存在性失败（进程内），继续同步: {e}")
                existing_codes = set(short_codes_to_check)  # 如果验证失败，假设都存在
            
            # 分离存在的和不存在的短链接
            valid_updates = [(code, count) for code, count in updates if code in existing_codes]
            invalid_codes = [code for code, _ in updates if code not in existing_codes]
            
            if invalid_codes:
                logger.info(f"发现 {len(invalid_codes)} 个不存在或已禁用的短链接（进程内），已清理其计数器")
                # 清理不存在的短链接的进程内计数器
                async with _counter_lock:
                    for code in invalid_codes:
                        _click_counters.pop(code, None)
            
            if not valid_updates:
                logger.debug("所有短链接都不存在或已禁用（进程内），无需同步")
                return 0
            
            # 批量处理，每批5条（与主函数保持一致）
            BATCH_SIZE = 5
            for batch_idx in range(0, len(valid_updates), BATCH_SIZE):
                batch = valid_updates[batch_idx:batch_idx + BATCH_SIZE]
                
                # 使用原子更新，避免 ORM 方式导致的死锁
                for short_code, count in batch:
                    success = await _update_click_count_with_retry(db, short_code, count)
                    if success:
                        synced += 1
                        logger.debug(
                            f"更新短链接点击次数（进程内）: short_code={short_code}, 增量={count}"
                        )
                    else:
                        failed_codes.append(short_code)
                        logger.warning(f"更新短链接点击次数失败（进程内）: short_code={short_code}")
            
            if synced > 0:
                logger.info(f"成功同步 {synced} 个短链接的点击次数到数据库（进程内）")
            
            # 只清空成功同步的计数器（使用异步锁保护并发访问）
            if synced > 0:
                async with _counter_lock:
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
                # 对失败的更新进行二次验证，不存在的立即清理
                try:
                    result = await db.execute(
                        select(ShortLink.short_code, ShortLink.is_active).where(
                            ShortLink.short_code.in_(failed_codes)
                        )
                    )
                    existing_failed = {row[0] for row in result.fetchall() if row[1]}  # 只包含激活的
                    
                    retry_codes = [code for code in failed_codes if code in existing_failed]
                    cleaned_codes = [code for code in failed_codes if code not in existing_failed]
                    
                    if cleaned_codes:
                        # 清理不存在的短链接的进程内计数器
                        async with _counter_lock:
                            for code in cleaned_codes:
                                _click_counters.pop(code, None)
                        logger.info(
                            f"清理了 {len(cleaned_codes)} 个不存在或已禁用的短链接计数器（进程内）: "
                            f"codes={cleaned_codes}"
                        )
                    
                    if retry_codes:
                        failed_counts = {code: _click_counters.get(code, 0) for code in retry_codes}
                        logger.warning(
                            f"有 {len(retry_codes)} 个短链接同步失败（进程内计数器），将在下次同步时重试。"
                            f"失败的短链接代码: {retry_codes}，"
                            f"失败的计数详情: {failed_counts}"
                        )
                    else:
                        logger.info("所有失败的计数器都已清理（进程内），无需重试")
                except Exception as e:
                    # 如果验证失败，记录所有失败项
                    failed_counts = {code: _click_counters.get(code, 0) for code in failed_codes}
                    logger.warning(
                        f"验证失败短链接存在性失败（进程内），所有失败项将重试: {e}。"
                        f"失败的短链接代码: {failed_codes}，"
                        f"失败的计数详情: {failed_counts}"
                    )
            
            return synced
        
        # Redis可用时，从Redis同步
        # 使用SCAN而不是KEYS，避免在生产环境阻塞
        pattern = f"{CLICK_COUNTER_PREFIX}*"
        keys = []
        cursor = 0
        max_iterations = 10000  # 最大迭代次数，防止无限循环（10000 * 100 = 100万条键）
        iteration = 0
        try:
            while True:
                cursor, batch_keys = await redis.scan(cursor, match=pattern, count=100)
                keys.extend(batch_keys)
                iteration += 1
                
                # 安全检查：防止无限循环
                if iteration >= max_iterations:
                    logger.warning(
                        f"Redis SCAN达到最大迭代次数 {max_iterations}，停止扫描。"
                        f"已收集 {len(keys)} 个键，当前游标: {cursor}"
                    )
                    break
                
                if cursor == 0:
                    break
        except Exception as e:
            # 如果SCAN失败，降级使用KEYS（不推荐，但作为后备方案）
            logger.warning(f"Redis SCAN失败，降级使用KEYS: {e}")
            try:
                keys = await redis.keys(pattern)
            except Exception as keys_error:
                logger.error(f"Redis KEYS也失败: {keys_error}")
                keys = []
        
        if not keys:
            logger.debug("没有需要同步的短链接点击计数器")
            return 0
        
        logger.info(f"找到 {len(keys)} 个短链接点击计数器需要同步")
        
        # 收集所有需要更新的数据
        updates: List[Tuple[str, int, str]] = []  # (short_code, count, redis_key)
        
        for key in keys:
            # 安全地提取 short_code：使用 startswith 检查并移除前缀
            # 这样可以避免 key 中多次出现前缀时提取错误的问题
            if not key.startswith(CLICK_COUNTER_PREFIX):
                logger.warning(f"Redis键格式不符合预期，跳过: key={key}")
                continue
            
            short_code = key[len(CLICK_COUNTER_PREFIX):]
            
            # 验证 short_code 不为空且格式正确
            if not short_code or len(short_code) == 0:
                logger.warning(f"从Redis键提取的short_code为空，跳过: key={key}")
                continue
            
            if short_codes and short_code not in short_codes:
                continue
            
            try:
                # 使用Lua脚本原子获取计数器值（不删除，避免数据丢失）
                # 只有在数据库更新成功后才删除计数器，确保数据不丢失
                count_value = await redis.eval(_GET_COUNTER_LUA, 1, key)
                
                # Lua脚本返回的是数字类型，需要转换为int
                if isinstance(count_value, (int, float)):
                    count_value = int(count_value)
                else:
                    # 如果返回的不是数字，可能是错误，记录并跳过
                    logger.warning(
                        f"Lua脚本返回非数字值: short_code={short_code}, key={key}, "
                        f"value={count_value}, type={type(count_value)}"
                    )
                    continue
                
                if count_value <= 0:
                    # 计数器为0或不存在，跳过（不删除，因为可能正在被其他进程使用）
                    continue
                
                updates.append((short_code, count_value, key))
                
            except Exception as e:
                # 获取计数器值失败，保留以便下次重试
                # 注意：如果Lua脚本执行失败，计数器可能没有被删除，会在下次同步时重试
                logger.error(
                    f"获取计数器值失败: short_code={short_code}, key={key}, error={e}",
                    exc_info=True
                )
        
        if not updates:
            logger.debug("没有需要同步的计数器")
            return 0
        
        logger.info(f"准备批量同步 {len(updates)} 个短链接的点击次数")
        
        # 第一步：预先验证短链接是否存在，不存在的直接清理（避免无效重试）
        short_codes_to_check = [code for code, _, _ in updates]
        existing_codes = set()
        try:
            result = await db.execute(
                select(ShortLink.short_code, ShortLink.is_active).where(
                    ShortLink.short_code.in_(short_codes_to_check)
                )
            )
            existing_links = result.fetchall()
            existing_codes = {row[0] for row in existing_links if row[1]}  # 只包含激活的短链接
        except Exception as e:
            logger.warning(f"预验证短链接存在性失败，继续同步: {e}")
            # 如果验证失败，继续同步流程，让后续逻辑处理
        
        # 分离存在的和不存在的短链接
        valid_updates = []
        invalid_updates = []
        for update_item in updates:
            short_code = update_item[0]
            if short_code in existing_codes:
                valid_updates.append(update_item)
            else:
                invalid_updates.append(update_item)
                # 立即清理不存在的短链接的Redis计数器（如果Lua脚本还没删除）
                if redis:
                    try:
                        redis_key = update_item[2] if len(update_item) > 2 else f"{CLICK_COUNTER_PREFIX}{short_code}"
                        await redis.delete(redis_key)
                        logger.info(f"清理不存在的短链接Redis计数器: short_code={short_code}")
                    except Exception as e:
                        logger.warning(f"清理不存在的短链接Redis计数器失败: short_code={short_code}, error={e}")
        
        if invalid_updates:
            logger.info(f"发现 {len(invalid_updates)} 个不存在的短链接，已清理其Redis计数器")
        
        if not valid_updates:
            logger.debug("所有短链接都不存在或已禁用，无需同步")
            return 0
        
        logger.info(f"实际需要同步 {len(valid_updates)} 个有效短链接的点击次数")
        
        # 使用批量更新（分批处理，减少死锁风险）
        # 减小批量大小，进一步降低死锁风险
        BATCH_SIZE = 5  # 每批处理5条记录（进一步减小批量大小，减少锁竞争）
        synced = 0
        failed_updates = []  # 记录失败的更新
        
        for batch_idx in range(0, len(valid_updates), BATCH_SIZE):
            batch = valid_updates[batch_idx:batch_idx + BATCH_SIZE]
            
            try:
                # 按 short_code 排序，确保更新顺序一致，减少死锁
                batch = sorted(batch, key=lambda x: x[0])
                
                # 尝试使用批量更新（一次性更新多条记录，减少锁持有时间）
                batch_synced, batch_keys_to_delete, batch_failed = await _batch_update_click_counts_with_retry(
                    db, batch, redis
                )
                
                if batch_synced > 0:
                    synced += batch_synced
                    # 注意：Redis计数器已经在获取时通过Lua脚本原子删除了
                    # 这里只需要处理删除失败的情况（如果Lua脚本执行失败）
                    # 但实际上Lua脚本已经处理了删除，所以这里主要是日志记录
                    if batch_keys_to_delete:
                        logger.debug(
                            f"批次 {batch_idx // BATCH_SIZE + 1} 成功同步，"
                            f"Redis计数器已通过Lua脚本原子删除: {len(batch_keys_to_delete)} 个"
                        )
                
                # 记录失败的更新
                if batch_failed:
                    failed_updates.extend(batch_failed)
                    
            except Exception as e:
                # 批次处理失败，保留计数器以便下次重试
                logger.error(
                    f"批量同步点击次数失败（批次 {batch_idx // BATCH_SIZE + 1}）: {e}",
                    exc_info=True
                )
                failed_updates.extend(batch)
                try:
                    await db.rollback()
                except:
                    pass
        
        if synced > 0:
            logger.info(f"成功同步 {synced} 个短链接的点击次数到数据库")
        
        if failed_updates:
            # 对失败的更新进行二次验证，不存在的立即清理
            failed_codes = [code for code, _, _ in failed_updates]
            retry_updates = []
            cleaned_updates = []
            
            try:
                # 验证失败的短链接是否存在
                result = await db.execute(
                    select(ShortLink.short_code, ShortLink.is_active).where(
                        ShortLink.short_code.in_(failed_codes)
                    )
                )
                existing_failed = {row[0] for row in result.fetchall() if row[1]}  # 只包含激活的
                
                for update_item in failed_updates:
                    short_code = update_item[0]
                    if short_code in existing_failed:
                        # 短链接存在且激活，加入重试列表
                        retry_updates.append(update_item)
                    else:
                        # 短链接不存在或已禁用，清理Redis计数器
                        # 注意：由于短链接不存在，不会有新的点击，可以直接删除
                        cleaned_updates.append(update_item)
                        if redis:
                            try:
                                redis_key = update_item[2] if len(update_item) > 2 else f"{CLICK_COUNTER_PREFIX}{short_code}"
                                # 直接删除计数器（短链接不存在，不会有新点击）
                                deleted = await redis.delete(redis_key)
                                if deleted:
                                    logger.info(f"清理失败且不存在的短链接Redis计数器: short_code={short_code}")
                            except Exception as e:
                                logger.warning(f"清理失败短链接Redis计数器失败: short_code={short_code}, error={e}")
            except Exception as e:
                logger.warning(f"验证失败短链接存在性失败，所有失败项将重试: {e}")
                retry_updates = failed_updates
            
            # 记录日志
            if cleaned_updates:
                cleaned_codes = [code for code, _, _ in cleaned_updates]
                cleaned_counts = {code: count for code, count, _ in cleaned_updates}
                logger.info(
                    f"清理了 {len(cleaned_updates)} 个不存在或已禁用的短链接计数器: "
                    f"codes={cleaned_codes}, counts={cleaned_counts}"
                )
            
            if retry_updates:
                retry_codes = [code for code, _, _ in retry_updates]
                retry_counts = {code: count for code, count, _ in retry_updates}
                logger.warning(
                    f"有 {len(retry_updates)} 个计数器同步失败，将在下次同步时重试。"
                    f"失败的短链接代码: {retry_codes}，"
                    f"失败的计数详情: {retry_counts}"
                )
            else:
                logger.info("所有失败的计数器都已清理，无需重试")
        
        return synced
    except Exception as e:
        logger.error(f"同步点击次数到数据库失败: {e}", exc_info=True)
        return 0
    finally:
        # 释放分布式锁
        if redis and lock_acquired:
            try:
                # 使用 Lua 脚本确保只删除自己设置的锁
                lua_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                await redis.eval(lua_script, 1, lock_key, lock_value)
                logger.debug("成功释放同步锁")
            except Exception as e:
                logger.warning(f"释放分布式锁失败: {e}")


async def _acquire_item_locks(redis, short_codes: List[str]) -> Tuple[Dict[str, str], List[str]]:
    """
    为每个short_code获取细粒度分布式锁
    
    Args:
        redis: Redis客户端
        short_codes: 短链接代码列表
        
    Returns:
        (成功获取锁的字典 {short_code: lock_value}, 未获取到锁的short_code列表)
    """
    if not redis:
        # Redis不可用时，返回所有代码（降级处理）
        return {code: "" for code in short_codes}, []
    
    acquired_locks = {}
    failed_codes = []
    
    for short_code in short_codes:
        lock_key = f"{ITEM_LOCK_PREFIX}{short_code}"
        lock_value = str(uuid.uuid4())
        
        try:
            # 尝试获取锁（NX: 只在键不存在时设置，EX: 设置过期时间）
            lock_acquired = await redis.set(
                lock_key,
                lock_value,
                nx=True,  # 只在键不存在时设置
                ex=ITEM_LOCK_TIMEOUT  # 设置过期时间，防止死锁
            )
            
            if lock_acquired:
                acquired_locks[short_code] = lock_value
            else:
                failed_codes.append(short_code)
                logger.debug(f"无法获取短链接锁，可能正在被其他进程更新: short_code={short_code}")
        except Exception as e:
            logger.warning(f"获取短链接锁失败: short_code={short_code}, error={e}")
            failed_codes.append(short_code)
    
    return acquired_locks, failed_codes


async def _release_item_locks(redis, locks: Dict[str, str]) -> None:
    """
    释放细粒度分布式锁
    
    Args:
        redis: Redis客户端
        locks: {short_code: lock_value} 字典
    """
    if not redis or not locks:
        return
    
    # 使用Lua脚本确保只删除自己设置的锁
    lua_script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    
    for short_code, lock_value in locks.items():
        lock_key = f"{ITEM_LOCK_PREFIX}{short_code}"
        try:
            await redis.eval(lua_script, 1, lock_key, lock_value)
        except Exception as e:
            logger.debug(f"释放短链接锁失败（可忽略）: short_code={short_code}, error={e}")


async def _batch_update_click_counts_with_retry(
    db: AsyncSession,
    batch: List[Tuple[str, int, str]],
    redis,
    max_retries: int = MAX_DEADLOCK_RETRIES,
    _recursion_depth: int = 0  # 内部参数：递归深度，防止无限递归
) -> Tuple[int, List[str], List[Tuple[str, int, str]]]:
    """
    批量更新点击次数（带重试机制，从源头避免死锁）
    
    使用细粒度分布式锁 + SELECT FOR UPDATE SKIP LOCKED 从源头避免死锁
    
    Args:
        db: 数据库会话
        batch: (short_code, count_value, redis_key) 元组列表
        redis: Redis客户端
        max_retries: 最大重试次数
        
    Returns:
        (成功更新的数量, 需要删除的Redis键列表, 失败的更新列表)
    """
    # 边界检查：如果批次为空，直接返回
    if not batch or len(batch) == 0:
        logger.debug("批次为空，跳过更新")
        return 0, [], []
    
    # 重要：必须在每次重试时都排序，确保锁顺序一致
    batch = sorted(batch, key=lambda x: x[0])
    short_codes = [code for code, _, _ in batch]
    
    # 第一步：为每个short_code获取细粒度分布式锁（从源头避免死锁）
    acquired_locks, failed_codes = await _acquire_item_locks(redis, short_codes)
    
    # 过滤出成功获取锁的批次项
    locked_batch = [item for item in batch if item[0] in acquired_locks]
    failed_batch = [item for item in batch if item[0] in failed_codes]
    
    if not locked_batch:
        # 所有锁都获取失败，返回失败
        logger.warning(f"无法获取任何短链接锁，跳过本次更新: short_codes={short_codes}")
        return 0, [], batch
    
    if failed_batch:
        failed_lock_codes = [code for code, _, _ in failed_batch]
        failed_lock_counts = {code: count for code, count, _ in failed_batch}
        logger.debug(
            f"部分短链接锁获取失败，将在下次同步时重试: "
            f"failed_codes={failed_lock_codes}, "
            f"failed_counts={failed_lock_counts}"
        )
    
    try:
        # 设置事务隔离级别为READ COMMITTED，减少锁竞争
        try:
            await db.execute(text("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED"))
        except Exception as e:
            logger.debug(f"设置事务隔离级别失败（可忽略）: {e}")
        
        # 设置锁等待超时为0，使用SKIP LOCKED避免等待
        try:
            await db.execute(text("SET SESSION innodb_lock_wait_timeout = 0"))
        except Exception as e:
            logger.debug(f"设置锁等待超时失败（可忽略）: {e}")
        
        # 使用SELECT FOR UPDATE SKIP LOCKED先锁定记录，避免死锁
        # 这样可以确保只更新能够立即锁定的记录，跳过已被其他事务锁定的记录
        locked_short_codes = [code for code, _, _ in locked_batch]
        where_placeholders = ", ".join([f":code_{i}" for i in range(len(locked_short_codes))])
        select_params = {f"code_{i}": code for i, code in enumerate(locked_short_codes)}
        
        # 先查询并锁定记录（使用SKIP LOCKED跳过已被锁定的记录）
        select_result = await db.execute(
            text(f"""
                SELECT short_code 
                FROM short_links 
                WHERE short_code IN ({where_placeholders})
                ORDER BY short_code
                FOR UPDATE SKIP LOCKED
            """),
            select_params
        )
        
        # 获取成功锁定的short_code
        locked_codes_set = {row[0] for row in select_result.fetchall()}
        
        # 过滤出成功锁定的批次项
        successfully_locked_batch = [item for item in locked_batch if item[0] in locked_codes_set]
        skipped_batch = [item for item in locked_batch if item[0] not in locked_codes_set]
        
        if skipped_batch:
            skipped_codes = [code for code, _, _ in skipped_batch]
            skipped_counts = {code: count for code, count, _ in skipped_batch}
            logger.debug(
                f"部分记录被其他事务锁定，跳过本次更新，将在下次同步时重试: "
                f"skipped_codes={skipped_codes}, "
                f"skipped_counts={skipped_counts}"
            )
        
        if not successfully_locked_batch:
            # 所有记录都被锁定，回滚并返回
            await db.rollback()
            # 释放已获取的分布式锁
            await _release_item_locks(redis, acquired_locks)
            return 0, [], batch
        
        # 构建批量更新SQL（只更新成功锁定的记录）
        case_when_parts = []
        update_params = {}
        update_where_params = []
        
        for idx, (code, count, _) in enumerate(successfully_locked_batch):
            if not code or not isinstance(code, str):
                continue
            if not isinstance(count, int) or count <= 0:
                continue
            
            param_code = f"update_code_{idx}"
            param_count = f"update_count_{idx}"
            param_where = f"update_where_{idx}"
            
            case_when_parts.append(f"WHEN :{param_code} THEN click_count + :{param_count}")
            update_params[param_code] = code
            update_params[param_count] = count
            update_params[param_where] = code
            update_where_params.append(f":{param_where}")
        
        if not case_when_parts:
            await db.rollback()
            await _release_item_locks(redis, acquired_locks)
            return 0, [], batch
        
        case_when_sql = " ".join(case_when_parts)
        update_where_placeholders = ", ".join(update_where_params)
        
        # 执行批量更新（只更新已锁定的记录）
        result = await db.execute(
            text(f"""
                UPDATE short_links 
                SET click_count = CASE short_code
                    {case_when_sql}
                    ELSE click_count
                END
                WHERE short_code IN ({update_where_placeholders})
                ORDER BY short_code
            """),
            update_params
        )
        
        updated_count = result.rowcount
        
        # 提交事务（尽快释放数据库锁）
        await db.commit()
        
        # 释放分布式锁（在提交后立即释放）
        await _release_item_locks(redis, {code: acquired_locks[code] for code, _, _ in successfully_locked_batch})
            
        if updated_count > 0:
            # 如果更新成功，说明所有记录都存在（因为WHERE条件匹配）
            # 现在可以安全地删除Redis计数器（数据库已成功更新）
            batch_keys_to_delete = [redis_key for _, _, redis_key in successfully_locked_batch if redis_key]
            
            # 批量删除Redis计数器（使用原子操作，确保只删除对应值的计数器）
            # 使用Lua脚本原子地检查并删除，避免删除其他进程新增加的计数
            if redis and batch_keys_to_delete:
                delete_tasks = []
                for short_code, count_value, redis_key in successfully_locked_batch:
                    if redis_key:
                        # 使用Lua脚本原子地减少计数器值，如果减到0或以下则删除
                        # 这样可以避免删除其他进程在同步期间新增加的计数
                        delete_lua = """
                        local val = redis.call('GET', KEYS[1])
                        if val and tonumber(val) >= tonumber(ARGV[1]) then
                            local new_val = tonumber(val) - tonumber(ARGV[1])
                            if new_val <= 0 then
                                redis.call('DEL', KEYS[1])
                                return 1
                            else
                                redis.call('SET', KEYS[1], new_val)
                                return 1
                            end
                        else
                            return 0
                        end
                        """
                        delete_tasks.append(
                            redis.eval(delete_lua, 1, redis_key, count_value)
                        )
                
                # 并行执行所有删除操作
                if delete_tasks:
                    try:
                        await asyncio.gather(*delete_tasks, return_exceptions=True)
                        logger.debug(f"成功删除 {len(delete_tasks)} 个Redis计数器")
                    except Exception as e:
                        logger.warning(f"批量删除Redis计数器时发生错误（可忽略，下次同步会重试）: {e}")
            
            # 批量清除缓存，使用并行操作提高性能
            cache_invalidation_tasks = []
            for short_code, count_value, redis_key in successfully_locked_batch:
                logger.debug(
                    f"批量更新短链接点击次数: short_code={short_code}, 增量={count_value}"
                )
                # 创建缓存失效任务（不等待，并行执行）
                cache_invalidation_tasks.append(
                    invalidate_short_link_cache(short_code)
                )
            
            # 并行执行所有缓存失效操作，忽略错误（缓存失效失败不影响主流程）
            if cache_invalidation_tasks:
                try:
                    await asyncio.gather(*cache_invalidation_tasks, return_exceptions=True)
                except Exception as e:
                    logger.debug(f"批量清除短链接缓存时发生错误（可忽略）: {e}")
            
            # 合并失败和跳过的批次项，返回需要重试的项
            all_failed = failed_batch + skipped_batch
            
            return len(successfully_locked_batch), batch_keys_to_delete, all_failed
        else:
            # 没有记录被更新，可能是所有短链接都不存在
            # 需要检查哪些短链接不存在，以便清理Redis计数器
            logger.warning(f"批量更新没有更新任何记录，检查短链接是否存在")
            
            # 回滚事务，因为更新失败
            await db.rollback()
            
            # 释放分布式锁
            await _release_item_locks(redis, acquired_locks)
            
            # 查询哪些短链接存在（需要新的事务）
            # 注意：由于已经回滚，SQLAlchemy会在下次查询时自动开始新事务
            # 使用只读查询，避免锁定记录
            existing_codes = set()
            try:
                # 使用新的查询，SQLAlchemy会自动开始新事务
                result = await db.execute(
                    select(ShortLink.short_code).where(ShortLink.short_code.in_(locked_short_codes))
                )
                existing_codes = {row[0] for row in result.fetchall()}
                # 查询后立即提交，释放连接
                await db.commit()
            except Exception as query_error:
                # 如果查询失败，记录错误但继续处理
                logger.warning(f"查询短链接存在性失败: {query_error}")
                try:
                    await db.rollback()
                except:
                    pass
                existing_codes = set()
            
            # 删除不存在的短链接的Redis计数器
            # 注意：由于短链接不存在，不会有新的点击，可以直接删除
            for short_code, count_value, redis_key in successfully_locked_batch:
                if short_code not in existing_codes:
                    logger.warning(f"短链接不存在，删除Redis计数器: short_code={short_code}")
                    if redis_key:  # 只有在redis_key存在时才尝试删除
                        try:
                            deleted = await redis.delete(redis_key)
                            if deleted:
                                logger.debug(f"成功删除不存在的短链接的Redis计数器: short_code={short_code}")
                        except Exception as e:
                            logger.warning(f"删除Redis计数器失败: key={redis_key}, error={e}")
            
            # 合并所有失败的批次项
            all_failed = failed_batch + skipped_batch + successfully_locked_batch
            return 0, [], all_failed
            
    except OperationalError as e:
        # 检查死锁错误：MySQL错误码1213或错误消息包含"Deadlock"
        error_code = e.orig.args[0] if hasattr(e.orig, 'args') and e.orig.args else None
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        is_deadlock = (
            error_code == 1213 or  # MySQL死锁错误码
            "Deadlock" in error_msg or  # 错误消息包含Deadlock
            "deadlock" in error_msg.lower()  # 错误消息包含deadlock（小写）
        )
        
        # 释放分布式锁（发生错误时也要释放）
        await _release_item_locks(redis, acquired_locks)
        
        if is_deadlock:
            # 更新死锁统计（使用异步锁保护并发访问）
            async with _deadlock_stats_lock:
                _deadlock_stats["total_deadlocks"] += 1
                _deadlock_stats["last_deadlock_time"] = datetime.now(timezone.utc)
                batch_size = len(batch)
                _deadlock_stats["deadlocks_by_batch_size"][batch_size] = \
                    _deadlock_stats["deadlocks_by_batch_size"].get(batch_size, 0) + 1
            
            # 注意：由于使用了细粒度分布式锁和SKIP LOCKED，死锁应该很少发生
            # 但如果仍然发生，可能是由于其他原因（如外键锁等）
            # 在这种情况下，记录错误并返回失败，让下次同步时重试
            short_codes_str = ", ".join([code for code, _, _ in batch])
            logger.error(
                f"检测到死锁（已使用细粒度锁和SKIP LOCKED，理论上不应发生）: "
                f"short_codes=[{short_codes_str}], error={e}",
                exc_info=True
            )
            
            # 死锁时MySQL已自动回滚，不需要手动回滚
            # 注意：由于现在不再在获取时删除计数器，计数器仍然存在，无需恢复
            # 计数器会在下次同步时重试
            
            # 返回所有批次项作为失败项，让下次同步时重试
            return 0, [], batch
        else:
            # 其他数据库错误，需要回滚
            short_codes_str = ", ".join([code for code, _, _ in batch])
            logger.error(
                f"批量更新短链接点击次数失败: short_codes=[{short_codes_str}], error={e}",
                exc_info=True
            )
            try:
                await db.rollback()
            except:
                pass
            # 注意：由于现在不再在获取时删除计数器，计数器仍然存在，无需恢复
            # 计数器会在下次同步时重试
            return 0, [], batch
    except Exception as e:
        # 释放分布式锁（发生异常时也要释放）
        await _release_item_locks(redis, acquired_locks)
        
        short_codes_str = ", ".join([code for code, _, _ in batch])
        logger.error(
            f"批量更新短链接点击次数失败: short_codes=[{short_codes_str}], error={e}",
            exc_info=True
        )
        try:
            await db.rollback()
        except:
            pass
        # 注意：由于现在不再在获取时删除计数器，计数器仍然存在，无需恢复
        # 计数器会在下次同步时重试
        return 0, [], batch
    
    # 如果所有重试都失败，返回失败
    await _release_item_locks(redis, acquired_locks)
    return 0, [], batch


async def _update_click_count_with_retry(
    db: AsyncSession, 
    short_code: str, 
    count_value: int,
    max_retries: int = MAX_DEADLOCK_RETRIES
) -> bool:
    """
    带重试机制的单个点击次数更新（处理死锁）
    
    Args:
        db: 数据库会话
        short_code: 短链接代码
        count_value: 要增加的点击次数
        max_retries: 最大重试次数
        
    Returns:
        是否更新成功
    """
    for attempt in range(max_retries):
        try:
            # 设置事务隔离级别为READ COMMITTED，减少锁竞争
            try:
                await db.execute(text("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED"))
            except Exception as e:
                logger.debug(f"设置事务隔离级别失败（可忽略）: {e}")
            
            # 设置锁等待超时，避免长时间等待
            try:
                await db.execute(text("SET SESSION innodb_lock_wait_timeout = 5"))
            except Exception as e:
                logger.debug(f"设置锁等待超时失败（可忽略）: {e}")
            
            # 使用原子更新，按 short_code 排序（虽然只有一条，但保持一致性）
            result = await db.execute(
                text("""
                    UPDATE short_links 
                    SET click_count = click_count + :count
                    WHERE short_code = :code
                """),
                {"count": count_value, "code": short_code}
            )
            
            if result.rowcount > 0:
                # 提交事务，确保更新立即生效
                # 注意：这里提交是为了避免长时间持有锁，减少死锁概率
                await db.commit()
                logger.debug(
                    f"原子更新短链接点击次数: short_code={short_code}, "
                    f"增量={count_value}"
                )
                return True
            else:
                # 短链接不存在，回滚事务
                await db.rollback()
                logger.warning(f"短链接不存在: short_code={short_code}")
                return False
                
        except OperationalError as e:
            # 检查死锁错误：MySQL错误码1213或错误消息包含"Deadlock"
            error_code = e.orig.args[0] if hasattr(e.orig, 'args') and e.orig.args else None
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            is_deadlock = (
                error_code == 1213 or  # MySQL死锁错误码
                "Deadlock" in error_msg or  # 错误消息包含Deadlock
                "deadlock" in error_msg.lower()  # 错误消息包含deadlock（小写）
            )
            
            if is_deadlock:
                if attempt < max_retries - 1:
                    # 指数退避 + 随机抖动（增加随机范围，减少并发冲突）
                    delay = DEADLOCK_RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.3)
                    logger.warning(
                        f"更新短链接点击次数时检测到死锁: short_code={short_code}, "
                        f"第 {attempt + 1}/{max_retries} 次重试，等待 {delay:.2f} 秒后重试..."
                    )
                    await asyncio.sleep(delay)
                    # MySQL在死锁时会自动回滚其中一个事务，但为了安全起见，显式回滚
                    try:
                        await db.rollback()
                    except Exception as rollback_error:
                        logger.debug(f"死锁重试时回滚失败（可忽略）: {rollback_error}")
                    # 继续重试
                    continue
                else:
                    logger.error(
                        f"更新短链接点击次数失败（死锁，已重试 {max_retries} 次）: "
                        f"short_code={short_code}, error={e}",
                        exc_info=True
                    )
                    # 死锁时MySQL已自动回滚，不需要手动回滚
                    return False
            else:
                # 其他数据库错误，需要回滚
                logger.error(
                    f"更新短链接点击次数失败: short_code={short_code}, error={e}",
                    exc_info=True
                )
                try:
                    await db.rollback()
                except:
                    pass
                return False
        except Exception as e:
            logger.error(
                f"更新短链接点击次数失败: short_code={short_code}, error={e}",
                exc_info=True
            )
            try:
                await db.rollback()
            except:
                pass
            return False
    
    return False


async def _commit_with_retry(db: AsyncSession, synced_count: int, max_retries: int = MAX_DEADLOCK_RETRIES) -> bool:
    """
    带重试机制的数据库提交（处理死锁）
    
    Args:
        db: 数据库会话
        synced_count: 已同步的记录数
        max_retries: 最大重试次数
        
    Returns:
        是否提交成功
    """
    for attempt in range(max_retries):
        try:
            await db.commit()
            logger.info(f"成功同步 {synced_count} 个短链接的点击次数到数据库")
            return True
        except OperationalError as e:
            # 检查死锁错误：MySQL错误码1213或错误消息包含"Deadlock"
            error_code = e.orig.args[0] if hasattr(e.orig, 'args') and e.orig.args else None
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            is_deadlock = (
                error_code == 1213 or  # MySQL死锁错误码
                "Deadlock" in error_msg or  # 错误消息包含Deadlock
                "deadlock" in error_msg.lower()  # 错误消息包含deadlock（小写）
            )
            
            if is_deadlock:
                if attempt < max_retries - 1:
                    # 指数退避 + 随机抖动（增加延迟时间，减少并发冲突）
                    delay = DEADLOCK_RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.3)
                    logger.warning(
                        f"检测到死锁，第 {attempt + 1}/{max_retries} 次重试，"
                        f"等待 {delay:.2f} 秒后重试..."
                    )
                    await asyncio.sleep(delay)
                    # 注意：这里不需要rollback，因为事务已经因为死锁而回滚了
                    continue
                else:
                    logger.error(
                        f"提交数据库事务失败（死锁，已重试 {max_retries} 次）: {e}",
                        exc_info=True
                    )
                    await db.rollback()
                    logger.warning(
                        f"警告：已删除 {synced_count} 个Redis计数器，但数据库更新失败。"
                        f"可能导致点击次数丢失。"
                    )
                    return False
            else:
                # 其他数据库错误
                logger.error(f"提交数据库事务失败: {e}", exc_info=True)
                await db.rollback()
                logger.warning(
                    f"警告：已删除 {synced_count} 个Redis计数器，但数据库更新失败。"
                    f"可能导致点击次数丢失。"
                )
                return False
        except Exception as e:
            logger.error(f"提交数据库事务失败: {e}", exc_info=True)
            await db.rollback()
            logger.warning(
                f"警告：已删除 {synced_count} 个Redis计数器，但数据库更新失败。"
                f"可能导致点击次数丢失。"
            )
            return False
    
    return False


async def sync_click_counts_to_db_batch(
    db: AsyncSession, 
    updates: List[Tuple[str, int]],
    batch_size: int = 5
) -> int:
    """
    批量同步点击次数到数据库（使用原子批量更新，减少死锁风险）
    
    注意：此函数已重构为使用原子批量更新，避免 ORM 方式导致的死锁
    
    Args:
        db: 数据库会话
        updates: (short_code, count) 元组列表
        batch_size: 每批处理的记录数（默认5，与主函数保持一致）
        
    Returns:
        成功同步的记录数
    """
    if not updates:
        return 0
    
    # 按 short_code 排序，确保所有进程以相同顺序锁定记录（关键：避免死锁）
    updates = sorted(updates, key=lambda x: x[0])
    
    synced = 0
    total_batches = (len(updates) + batch_size - 1) // batch_size
    
    redis = await get_redis_client()
    
    for batch_idx in range(total_batches):
        batch = updates[batch_idx * batch_size:(batch_idx + 1) * batch_size]
        
        # 转换为 (short_code, count, redis_key) 格式，redis_key 设为空字符串（不使用Redis）
        batch_with_keys = [(code, count, "") for code, count in batch]
        
        try:
            # 使用与主函数相同的批量更新方法（原子更新，带重试机制）
            batch_synced, _, batch_failed = await _batch_update_click_counts_with_retry(
                db, batch_with_keys, redis
            )
            
            if batch_synced > 0:
                synced += batch_synced
                logger.debug(
                    f"批量同步点击次数成功（批次 {batch_idx + 1}/{total_batches}）: "
                    f"成功 {batch_synced} 条"
                )
            
            if batch_failed:
                logger.warning(
                    f"批量同步点击次数部分失败（批次 {batch_idx + 1}/{total_batches}）: "
                    f"失败 {len(batch_failed)} 条"
                )
                
        except Exception as e:
            logger.error(
                f"批量同步点击次数失败（批次 {batch_idx + 1}/{total_batches}）: {e}",
                exc_info=True
            )
            try:
                await db.rollback()
            except:
                pass
    
    return synced


async def get_deadlock_stats() -> dict:
    """
    获取死锁统计信息（用于监控）
    
    Returns:
        包含死锁统计信息的字典
    """
    # 使用异步锁保护并发访问
    async with _deadlock_stats_lock:
        return {
            "total_deadlocks": _deadlock_stats["total_deadlocks"],
            "deadlocks_by_batch_size": _deadlock_stats["deadlocks_by_batch_size"].copy(),
            "last_deadlock_time": _deadlock_stats["last_deadlock_time"].isoformat() if _deadlock_stats["last_deadlock_time"] else None,
        }


async def get_click_counter_stats() -> dict:
    """
    获取进程内计数器统计信息（用于监控）
    
    Returns:
        包含进程内计数器统计信息的字典
    """
    # 使用异步锁保护并发访问
    async with _counter_lock:
        # 获取前100个计数器（键值对），避免响应过大
        counter_items = list(_click_counters.items())[:100]
        return {
            "total_counters": len(_click_counters),
            "counter_keys": [key for key, _ in counter_items],
            "counter_details": [{"short_code": key, "count": count} for key, count in counter_items],
            "total_clicks": sum(_click_counters.values()),
        }


async def reset_deadlock_stats() -> None:
    """
    重置死锁统计信息
    """
    global _deadlock_stats
    # 使用异步锁保护并发访问
    async with _deadlock_stats_lock:
        _deadlock_stats = {
            "total_deadlocks": 0,
            "deadlocks_by_batch_size": {},
            "last_deadlock_time": None,
        }

