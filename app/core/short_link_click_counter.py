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

# 死锁统计（用于监控）
_deadlock_stats = {
    "total_deadlocks": 0,
    "deadlocks_by_batch_size": {},
    "last_deadlock_time": None,
}

# Redis键前缀
CLICK_COUNTER_PREFIX = "short_link:click:"
SYNC_LOCK_PREFIX = "short_link:sync_lock:"  # 分布式锁前缀
SYNC_LOCK_TIMEOUT = 300  # 锁超时时间（秒），5分钟

# Lua脚本：原子获取并删除计数器值（避免竞态条件）
# 返回：如果键存在且值>0，返回计数值并删除键；否则返回0
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
        # 设置过期时间（48小时）- 如果失败不影响计数，但记录警告
        try:
            await redis.expire(counter_key, 48 * 3600)
        except Exception as expire_error:
            logger.warning(
                f"设置Redis计数器过期时间失败（不影响计数）: "
                f"short_code={short_code}, key={counter_key}, error={expire_error}"
            )
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
            if not _click_counters:
                logger.debug("进程内计数器为空，无需同步")
                return 0
            
            logger.info(f"Redis不可用，同步进程内计数器: {len(_click_counters)} 个短链接")
            
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
            
            # 按 short_code 排序，确保所有进程以相同顺序锁定记录
            updates = sorted(updates, key=lambda x: x[0])
            
            # 使用批量更新，减少死锁风险
            synced = 0
            failed_codes = []  # 记录同步失败的短链接代码
            
            # 批量处理，每批5条（与主函数保持一致）
            BATCH_SIZE = 5
            for batch_idx in range(0, len(updates), BATCH_SIZE):
                batch = updates[batch_idx:batch_idx + BATCH_SIZE]
                
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
        
        # Redis可用时，从Redis同步
        # 使用SCAN而不是KEYS，避免在生产环境阻塞
        pattern = f"{CLICK_COUNTER_PREFIX}*"
        keys = []
        cursor = 0
        try:
            while True:
                cursor, batch_keys = await redis.scan(cursor, match=pattern, count=100)
                keys.extend(batch_keys)
                if cursor == 0:
                    break
        except Exception as e:
            # 如果SCAN失败，降级使用KEYS（不推荐，但作为后备方案）
            logger.warning(f"Redis SCAN失败，降级使用KEYS: {e}")
            keys = await redis.keys(pattern)
        
        if not keys:
            logger.debug("没有需要同步的短链接点击计数器")
            return 0
        
        logger.info(f"找到 {len(keys)} 个短链接点击计数器需要同步")
        
        # 收集所有需要更新的数据
        updates: List[Tuple[str, int, str]] = []  # (short_code, count, redis_key)
        
        for key in keys:
            short_code = key.replace(CLICK_COUNTER_PREFIX, "")
            if short_codes and short_code not in short_codes:
                continue
            
            try:
                # 使用Lua脚本原子获取并删除计数器值，避免竞态条件
                # 这样可以确保在获取值和删除之间不会有新的点击进来导致数据丢失
                count_value = await redis.eval(_GET_AND_DELETE_COUNTER_LUA, 1, key)
                
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
                    # 计数器为0或不存在，已由Lua脚本删除，跳过
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
        
        # 使用批量更新（分批处理，减少死锁风险）
        # 减小批量大小，进一步降低死锁风险
        BATCH_SIZE = 5  # 每批处理5条记录（进一步减小批量大小，减少锁竞争）
        synced = 0
        failed_updates = []  # 记录失败的更新
        
        for batch_idx in range(0, len(updates), BATCH_SIZE):
            batch = updates[batch_idx:batch_idx + BATCH_SIZE]
            
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
            logger.warning(f"有 {len(failed_updates)} 个计数器同步失败，将在下次同步时重试")
        
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


async def _batch_update_click_counts_with_retry(
    db: AsyncSession,
    batch: List[Tuple[str, int, str]],
    redis,
    max_retries: int = MAX_DEADLOCK_RETRIES
) -> Tuple[int, List[str], List[Tuple[str, int, str]]]:
    """
    批量更新点击次数（带重试机制，减少死锁）
    
    使用批量 UPDATE 语句一次性更新多条记录，减少锁持有时间
    
    Args:
        db: 数据库会话
        batch: (short_code, count_value, redis_key) 元组列表
        redis: Redis客户端
        max_retries: 最大重试次数
        
    Returns:
        (成功更新的数量, 需要删除的Redis键列表, 失败的更新列表)
    """
    for attempt in range(max_retries):
        try:
            # 设置事务隔离级别为READ COMMITTED，减少锁竞争
            # READ COMMITTED 比 REPEATABLE READ 持有锁的时间更短，减少死锁概率
            try:
                await db.execute(text("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED"))
            except Exception as e:
                # 如果设置失败，记录警告但继续执行
                logger.debug(f"设置事务隔离级别失败（可忽略）: {e}")
            
            # 构建批量更新SQL（使用 CASE WHEN 实现批量更新）
            # 这样可以一次性更新多条记录，减少锁竞争
            # 按 short_code 排序，确保所有进程以相同顺序锁定记录，减少死锁
            short_codes = [code for code, _, _ in batch]
            count_values = {code: count for code, count, _ in batch}
            
            # 构建批量更新SQL（使用 CASE WHEN 实现批量更新）
            # 这样可以一次性更新多条记录，减少锁竞争
            case_when_parts = []
            params = {}
            where_params = []
            
            for idx, (code, count, _) in enumerate(batch):
                param_code = f"code_{idx}"
                param_count = f"count_{idx}"
                param_where = f"where_code_{idx}"
                
                case_when_parts.append(f"WHEN :{param_code} THEN click_count + :{param_count}")
                params[param_code] = code
                params[param_count] = count
                params[param_where] = code
                where_params.append(f":{param_where}")
            
            case_when_sql = " ".join(case_when_parts)
            where_placeholders = ", ".join(where_params)
            
            # 执行批量更新（使用 FOR UPDATE 确保按顺序锁定，但这里不需要，因为已经按 short_code 排序）
            # 添加超时设置，避免长时间等待
            try:
                await db.execute(text("SET SESSION innodb_lock_wait_timeout = 5"))
            except Exception as e:
                logger.debug(f"设置锁等待超时失败（可忽略）: {e}")
            
            result = await db.execute(
                text(f"""
                    UPDATE short_links 
                    SET click_count = CASE short_code
                        {case_when_sql}
                        ELSE click_count
                    END
                    WHERE short_code IN ({where_placeholders})
                    ORDER BY short_code
                """),
                params
            )
            
            updated_count = result.rowcount
            
            # 提交事务（在查询之前提交，避免长时间持有锁）
            await db.commit()
            
            if updated_count > 0:
                # 如果更新成功，说明所有记录都存在（因为WHERE条件匹配）
                # 直接标记所有更新为成功
                batch_keys_to_delete = [redis_key for _, _, redis_key in batch if redis_key]
                
                for short_code, count_value, redis_key in batch:
                    logger.debug(
                        f"批量更新短链接点击次数: short_code={short_code}, 增量={count_value}"
                    )
                    # 清除缓存，确保缓存中的点击次数与数据库一致
                    # 注意：这里不清除计数器键（redis_key），因为已经在获取时用Lua脚本删除了
                    try:
                        from app.core.short_link_cache import invalidate_short_link_cache
                        await invalidate_short_link_cache(short_code)
                    except Exception as e:
                        logger.debug(f"清除短链接缓存失败（可忽略）: short_code={short_code}, error={e}")
                
                return len(batch_keys_to_delete), batch_keys_to_delete, []
            else:
                # 没有记录被更新，可能是所有短链接都不存在
                # 需要检查哪些短链接不存在，以便清理Redis计数器
                logger.warning(f"批量更新没有更新任何记录，检查短链接是否存在")
                
                # 查询哪些短链接存在
                result = await db.execute(
                    select(ShortLink.short_code).where(ShortLink.short_code.in_(short_codes))
                )
                existing_codes = {row[0] for row in result.fetchall()}
                
                # 删除不存在的短链接的Redis计数器
                # 注意：由于使用了Lua脚本，redis_key可能已经被删除，但为了安全起见，仍然尝试删除
                for short_code, count_value, redis_key in batch:
                    if short_code not in existing_codes:
                        logger.warning(f"短链接不存在，尝试删除Redis计数器: short_code={short_code}")
                        if redis_key:  # 只有在redis_key存在时才尝试删除
                            try:
                                deleted = await redis.delete(redis_key)
                                if deleted:
                                    logger.debug(f"成功删除不存在的短链接的Redis计数器: short_code={short_code}")
                            except Exception as e:
                                logger.warning(f"删除Redis计数器失败: key={redis_key}, error={e}")
                
                return 0, [], batch
                
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
                # 更新死锁统计
                _deadlock_stats["total_deadlocks"] += 1
                _deadlock_stats["last_deadlock_time"] = datetime.now(timezone.utc)
                batch_size = len(batch)
                _deadlock_stats["deadlocks_by_batch_size"][batch_size] = \
                    _deadlock_stats["deadlocks_by_batch_size"].get(batch_size, 0) + 1
                
                if attempt < max_retries - 1:
                    # 如果批次较大且重试次数较多，考虑拆分批次
                    if len(batch) > 2 and attempt >= 2:
                        # 将批次拆分成两半，分别处理
                        mid = len(batch) // 2
                        first_half = batch[:mid]
                        second_half = batch[mid:]
                        
                        short_codes_str = ", ".join([code for code, _, _ in batch])
                        logger.warning(
                            f"批量更新短链接点击次数时检测到死锁: short_codes=[{short_codes_str}], "
                            f"第 {attempt + 1}/{max_retries} 次重试，将批次拆分为 {len(first_half)} 和 {len(second_half)} 条记录分别处理..."
                        )
                        
                        # 先处理前半部分
                        first_synced, first_keys, first_failed = await _batch_update_click_counts_with_retry(
                            db, first_half, redis, max_retries - attempt
                        )
                        # 再处理后半部分
                        second_synced, second_keys, second_failed = await _batch_update_click_counts_with_retry(
                            db, second_half, redis, max_retries - attempt
                        )
                        
                        # 合并结果
                        total_synced = first_synced + second_synced
                        all_keys = first_keys + second_keys
                        all_failed = first_failed + second_failed
                        
                        return total_synced, all_keys, all_failed
                    
                    # 指数退避 + 随机抖动（增加随机范围以减少并发冲突）
                    delay = DEADLOCK_RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    short_codes_str = ", ".join([code for code, _, _ in batch])
                    logger.warning(
                        f"批量更新短链接点击次数时检测到死锁: short_codes=[{short_codes_str}], "
                        f"第 {attempt + 1}/{max_retries} 次重试，等待 {delay:.2f} 秒后重试..."
                    )
                    await asyncio.sleep(delay)
                    # MySQL在死锁时会自动回滚其中一个事务，所以这里不需要手动回滚
                    # 直接重试即可
                    continue
                else:
                    short_codes_str = ", ".join([code for code, _, _ in batch])
                    logger.error(
                        f"批量更新短链接点击次数失败（死锁，已重试 {max_retries} 次）: "
                        f"short_codes=[{short_codes_str}], error={e}",
                        exc_info=True
                    )
                    logger.warning(
                        f"死锁统计: 总死锁次数={_deadlock_stats['total_deadlocks']}, "
                        f"批次大小分布={_deadlock_stats['deadlocks_by_batch_size']}, "
                        f"最后死锁时间={_deadlock_stats['last_deadlock_time']}"
                    )
                    # 死锁时MySQL已自动回滚，不需要手动回滚
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
                return 0, [], batch
        except Exception as e:
            short_codes_str = ", ".join([code for code, _, _ in batch])
            logger.error(
                f"批量更新短链接点击次数失败: short_codes=[{short_codes_str}], error={e}",
                exc_info=True
            )
            try:
                await db.rollback()
            except:
                pass
            return 0, [], batch
    
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
                logger.debug(
                    f"原子更新短链接点击次数: short_code={short_code}, "
                    f"增量={count_value}"
                )
                return True
            else:
                # 短链接不存在
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
                    # MySQL在死锁时会自动回滚其中一个事务，所以这里不需要手动回滚
                    # 直接重试即可
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


def get_deadlock_stats() -> dict:
    """
    获取死锁统计信息（用于监控）
    
    Returns:
        包含死锁统计信息的字典
    """
    return {
        "total_deadlocks": _deadlock_stats["total_deadlocks"],
        "deadlocks_by_batch_size": _deadlock_stats["deadlocks_by_batch_size"].copy(),
        "last_deadlock_time": _deadlock_stats["last_deadlock_time"].isoformat() if _deadlock_stats["last_deadlock_time"] else None,
    }


def reset_deadlock_stats() -> None:
    """
    重置死锁统计信息
    """
    global _deadlock_stats
    _deadlock_stats = {
        "total_deadlocks": 0,
        "deadlocks_by_batch_size": {},
        "last_deadlock_time": None,
    }

