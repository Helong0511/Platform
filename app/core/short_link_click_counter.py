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
DEADLOCK_RETRY_BASE_DELAY = 0.2  # 增加基础延迟（秒）

# Redis键前缀
CLICK_COUNTER_PREFIX = "short_link:click:"
SYNC_LOCK_PREFIX = "short_link:sync_lock:"  # 分布式锁前缀
SYNC_LOCK_TIMEOUT = 300  # 锁超时时间（秒），5分钟

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
        
        # Redis可用时，从Redis同步
        # 获取所有计数器键
        pattern = f"{CLICK_COUNTER_PREFIX}*"
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
                # 先获取计数器值（不删除）
                count = await redis.get(key)
                if not count or int(count) <= 0:
                    # 计数器为0或不存在，直接删除
                    await redis.delete(key)
                    continue
                
                count_value = int(count)
                updates.append((short_code, count_value, key))
                
            except Exception as e:
                # 获取计数器值失败，保留以便下次重试
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
        BATCH_SIZE = 10  # 每批处理10条记录（从20减少到10）
        synced = 0
        failed_updates = []  # 记录失败的更新
        
        for batch_idx in range(0, len(updates), BATCH_SIZE):
            batch = updates[batch_idx:batch_idx + BATCH_SIZE]
            
            try:
                # 使用原子更新（UPDATE ... SET click_count = click_count + ? WHERE short_code = ?）
                # 这样可以避免读取-修改-写入模式导致的死锁
                batch_synced = 0
                batch_keys_to_delete = []  # 成功同步后需要删除的键
                
                # 按 short_code 排序，确保更新顺序一致，减少死锁
                batch = sorted(batch, key=lambda x: x[0])
                
                for short_code, count_value, redis_key in batch:
                    # 使用带重试的更新函数，处理死锁
                    success = await _update_click_count_with_retry(
                        db, short_code, count_value
                    )
                    
                    if success:
                        batch_synced += 1
                        batch_keys_to_delete.append(redis_key)
                    else:
                        # 更新失败，检查是否是短链接不存在
                        # 如果短链接不存在，删除Redis计数器；否则保留以便重试
                        try:
                            result = await db.execute(
                                select(ShortLink).where(ShortLink.short_code == short_code)
                            )
                            short_link = result.scalars().first()
                            if not short_link:
                                # 短链接不存在，删除Redis中的计数器
                                logger.warning(f"短链接不存在，删除Redis计数器: short_code={short_code}")
                                try:
                                    await redis.delete(redis_key)
                                except Exception as e:
                                    logger.warning(f"删除Redis计数器失败: key={redis_key}, error={e}")
                            else:
                                # 短链接存在但更新失败（可能是死锁等），保留以便重试
                                failed_updates.append((short_code, count_value, redis_key))
                        except Exception as e:
                            # 查询失败，保守处理：保留以便重试
                            logger.warning(
                                f"查询短链接状态失败，保留计数器以便重试: short_code={short_code}, error={e}"
                            )
                            failed_updates.append((short_code, count_value, redis_key))
                
                # 提交当前批次（带死锁重试）
                if batch_synced > 0:
                    success = await _commit_with_retry(db, batch_synced)
                    if success:
                        synced += batch_synced
                        # 删除Redis中的计数器（只在成功提交后删除）
                        for key in batch_keys_to_delete:
                            try:
                                await redis.delete(key)
                            except Exception as e:
                                logger.warning(f"删除Redis计数器失败: key={key}, error={e}")
                    else:
                        # 提交失败，保留计数器以便下次重试
                        failed_updates.extend([(code, count, key) for code, count, key in batch 
                                              if (code, count, key) not in failed_updates])
                        logger.warning(f"批次 {batch_idx // BATCH_SIZE + 1} 提交失败，保留计数器以便重试")
                        await db.rollback()
                    
            except Exception as e:
                # 批次处理失败，保留计数器以便下次重试
                logger.error(
                    f"批量同步点击次数失败（批次 {batch_idx // BATCH_SIZE + 1}）: {e}",
                    exc_info=True
                )
                failed_updates.extend(batch)
                await db.rollback()
        
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
            error_code = e.orig.args[0] if hasattr(e.orig, 'args') and e.orig.args else None
            if error_code == 1213:  # Deadlock
                if attempt < max_retries - 1:
                    # 指数退避 + 随机抖动
                    delay = DEADLOCK_RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.2)
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
            error_code = e.orig.args[0] if hasattr(e.orig, 'args') and e.orig.args else None
            if error_code == 1213:  # Deadlock
                if attempt < max_retries - 1:
                    # 指数退避 + 随机抖动（增加延迟时间）
                    delay = DEADLOCK_RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.2)
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
    batch_size: int = 10
) -> int:
    """
    批量同步点击次数到数据库（使用批量更新，减少死锁风险）
    
    Args:
        db: 数据库会话
        updates: (short_code, count) 元组列表
        batch_size: 每批处理的记录数
        
    Returns:
        成功同步的记录数
    """
    if not updates:
        return 0
    
    # 按 short_code 排序，避免死锁
    updates = sorted(updates, key=lambda x: x[0])
    
    synced = 0
    total_batches = (len(updates) + batch_size - 1) // batch_size
    
    for batch_idx in range(total_batches):
        batch = updates[batch_idx * batch_size:(batch_idx + 1) * batch_size]
        
        # 获取所有 short_code
        short_codes = [code for code, _ in batch]
        
        try:
            # 查询所有短链接（按 ID 排序，避免死锁）
            result = await db.execute(
                select(ShortLink)
                .where(ShortLink.short_code.in_(short_codes))
                .order_by(ShortLink.id)
            )
            short_links = result.scalars().all()
            
            # 创建 short_code -> count 映射
            count_map = {code: count for code, count in batch}
            
            # 更新每个短链接
            for short_link in short_links:
                if short_link.short_code in count_map:
                    count_value = count_map[short_link.short_code]
                    old_count = short_link.click_count
                    short_link.click_count += count_value
                    new_count = short_link.click_count
                    
                    logger.debug(
                        f"批量更新短链接点击次数: short_code={short_link.short_code}, "
                        f"旧值={old_count}, 增量={count_value}, 新值={new_count}"
                    )
            
            # 提交当前批次（带重试）
            success = await _commit_with_retry(db, len(batch))
            if success:
                synced += len(batch)
            else:
                # 如果提交失败，回滚并跳过当前批次
                logger.warning(f"批次 {batch_idx + 1}/{total_batches} 提交失败，跳过")
                await db.rollback()
                
        except Exception as e:
            logger.error(
                f"批量同步点击次数失败（批次 {batch_idx + 1}/{total_batches}）: {e}",
                exc_info=True
            )
            await db.rollback()
    
    return synced

