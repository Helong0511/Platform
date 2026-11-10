"""
短链接点击计数异步刷盘模块。

职责：Redis 原子递增 + pending batch + DB 唯一账本，安全刷盘到 ``short_links.click_count``，并失效短链缓存。

在系统中的位置：``app.core.short_link_click_counter``，由短链跳转路由与定时任务调用。
"""
import logging
import asyncio
import random
from typing import Dict, List, Tuple
from datetime import datetime, timezone, timedelta
from app.core.redis_client import get_redis_client
from app.core.database import AsyncSessionLocal
from app.core.short_link_cache import invalidate_short_link_cache
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete, update, text
from sqlalchemy.exc import OperationalError, IntegrityError
from app.models.models import ShortLink, ShortLinkClickSyncBatch
import uuid
import json
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 死锁重试配置
MAX_DEADLOCK_RETRIES = 5  # 增加重试次数
DEADLOCK_RETRY_BASE_DELAY = 0.3  # 增加基础延迟（秒），减少并发冲突
MAX_RECURSION_DEPTH = 10  # 批次拆分最大递归深度，防止栈溢出（批次大小5最多递归3次）

# 记录锁定重试配置
LOCK_RETRY_MAX_ATTEMPTS = 2  # 记录被锁定时最大重试次数
LOCK_RETRY_DELAY = 0.05  # 记录被锁定时重试延迟（秒），50毫秒

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
# 每轮同步最多处理的 Redis 计数器数量，避免单次任务超过 Gunicorn worker 超时
MAX_KEYS_PER_SYNC = int(os.getenv("SHORT_LINK_SYNC_MAX_KEYS", "500"))
ITEM_LOCK_PREFIX = "short_link:item_lock:"  # 细粒度分布式锁前缀（每个short_code一个锁）
ITEM_LOCK_TIMEOUT = 10  # 细粒度锁超时时间（秒），10秒足够完成单个更新

# MySQL 默认 innodb_lock_wait_timeout；刷盘临时调低后必须还原，避免连接池污染
MYSQL_DEFAULT_LOCK_WAIT_TIMEOUT = 50


async def _tune_session_for_click_sync(
    db: AsyncSession,
    *,
    lock_wait_timeout: int,
) -> None:
    """
    为点击刷盘临时调整事务参数。

    - 隔离级别用 SET TRANSACTION（仅下一事务），避免 SET SESSION 污染连接池
    - lock_wait 仍为 SESSION 级，调用方必须在 finally 中 _restore_session_after_click_sync
    """
    try:
        # 不带 SESSION：只影响紧接着开始的下一个事务
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
    except Exception as e:
        logger.debug(f"设置事务隔离级别失败（可忽略）: {e}")
    try:
        await db.execute(
            text(f"SET SESSION innodb_lock_wait_timeout = {int(lock_wait_timeout)}")
        )
    except Exception as e:
        logger.debug(f"设置锁等待超时失败（可忽略）: {e}")


async def _restore_session_after_click_sync(db: AsyncSession) -> None:
    """还原刷盘临时改动的 SESSION 级参数，防止连接归还池后污染其它请求。"""
    try:
        await db.execute(
            text(f"SET SESSION innodb_lock_wait_timeout = {MYSQL_DEFAULT_LOCK_WAIT_TIMEOUT}")
        )
    except Exception as e:
        logger.debug(f"还原锁等待超时失败（可忽略）: {e}")


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

# Lua：数据库成功入账后，只扣减本轮已读取的增量。
# 点击计数器在数据库确认入账前不设置 TTL，避免同步故障超过固定 TTL 后丢失待入账数据。
_DECREMENT_COUNTER_LUA = """
local current = redis.call('GET', KEYS[1])
if not current then
    return 0
end
local decrement = tonumber(ARGV[1])
local current_number = tonumber(current)
if not decrement or decrement <= 0 or not current_number or current_number < decrement then
    return 0
end
local remaining = redis.call('DECRBY', KEYS[1], decrement)
if remaining <= 0 then
    redis.call('DEL', KEYS[1])
end
return 1
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

# 持久化配置
import tempfile
# 使用临时目录存储持久化数据，避免权限问题
COUNTER_PERSIST_FILE = Path(tempfile.gettempdir()) / "click_counters.json"
COUNTER_PERSIST_INTERVAL = 300  # 每5分钟持久化一次

# 不需要创建目录，因为临时目录已存在

# 加载持久化的计数器数据
def load_persisted_counters():
    """加载持久化的计数器数据"""
    global _click_counters
    try:
        if COUNTER_PERSIST_FILE.exists():
            with open(COUNTER_PERSIST_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    valid_data = {}
                    invalid_entries = 0
                    for code, count in data.items():
                        if (
                            not isinstance(code, str)
                            or not code
                            or not isinstance(count, int)
                            or isinstance(count, bool)
                            or count <= 0
                        ):
                            invalid_entries += 1
                            continue
                        valid_data[code] = count
                    _click_counters.update(valid_data)
                    logger.warning(
                        "检测到旧版点击计数快照: %s 个有效计数器、%s 个无效条目；"
                        "因缺少批次幂等键，仅保留供人工核对，不自动重放",
                        len(valid_data),
                        invalid_entries,
                    )
    except Exception as e:
        logger.warning(f"⚠️ 加载持久化计数器数据失败: {e}")

# 持久化计数器数据
async def persist_counters():
    """原子持久化计数器；即使计数器为空也必须覆盖旧文件，防止重启后重复入账。"""
    try:
        async with _counter_lock:
            data = _click_counters.copy()

        # 先写同目录临时文件，再原子替换，避免进程中断留下半截 JSON。
        temp_path = COUNTER_PERSIST_FILE.with_name(
            f"{COUNTER_PERSIST_FILE.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, COUNTER_PERSIST_FILE)
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                logger.warning("清理点击计数临时持久化文件失败: %s", temp_path)

        logger.info("持久化进程内点击计数完成: %s 个计数器", len(data))
    except Exception as e:
        logger.warning("持久化计数器数据失败: %s", e)

# 初始化时加载持久化数据
load_persisted_counters()


async def _increment_click_count_in_db(short_code: str) -> bool:
    """
    Redis 不可用时使用数据库原子自增，避免多 API Worker 的进程内计数无法汇总。

    这是降级路径，正常流量仍由 Redis 聚合；数据库不可用时不阻断短链跳转，
    但必须明确记录计数未能持久化，不能伪称已成功入账。
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(ShortLink)
                .where(
                    ShortLink.short_code == short_code,
                    ShortLink.is_active.is_(True),
                )
                .values(click_count=ShortLink.click_count + 1)
            )
            await db.commit()
            updated = bool(getattr(result, "rowcount", 0))
        if not updated:
            logger.warning("短链接点击计数降级写库未更新记录（短链不存在或已停用）: %s", short_code)
            return False
        try:
            await invalidate_short_link_cache(short_code)
        except Exception as cache_exc:
            # 数据库已经提交；缓存失效失败不能把已入账结果误报成写库失败。
            logger.warning("短链接点击计数已写库，但缓存失效失败: short_code=%s, error=%s", short_code, cache_exc)
        return True
    except Exception as exc:
        logger.error(
            "Redis 不可用且数据库降级自增失败，当前点击无法持久化: short_code=%s, error=%s",
            short_code,
            exc,
            exc_info=True,
        )
        return False


async def increment_click_count_async(short_code: str) -> None:
    """
    增加短链接点击次数：优先 Redis 原子计数，Redis 故障时直接原子写数据库。

    不再把 API Worker 的点击写入各自进程内内存；多 Worker 的本地计数无法由单一
    scheduler 进程可靠汇总，且 Worker 重启会造成未刷盘计数丢失。
    """
    try:
        redis = await get_redis_client()
    except Exception as exc:
        logger.warning("获取 Redis 客户端失败，改用数据库原子自增: short_code=%s, error=%s", short_code, exc)
        await _increment_click_count_in_db(short_code)
        return
    if not redis:
        await _increment_click_count_in_db(short_code)
        return

    try:
        # 仅执行原子 INCR，不设置固定 TTL。
        # 计数器只有在数据库确认入账后才由同步流程扣减/删除；
        # 固定 TTL 会在同步任务长期故障时悄悄丢弃尚未入账的点击。
        counter_key = f"{CLICK_COUNTER_PREFIX}{short_code}"
        new_count = await redis.eval(
            "return redis.call('INCR', KEYS[1])",
            1,
            counter_key,
        )
        logger.debug(
            "短链接点击计数（Redis）: short_code=%s, 计数器键=%s, 当前值=%s",
            short_code,
            counter_key,
            new_count,
        )
    except Exception as exc:
        # Redis eval 超时/连接中断时，服务端可能已经执行 INCR，只是响应未到达。
        # 此时直接写 DB 会与 Redis 中可能存在的增量重复入账；没有事件级幂等流水前，
        # 必须将结果标记为不确定并交由后续对账，而不是盲目双写。
        logger.error(
            "Redis 点击计数执行结果不确定，跳过数据库回退以避免重复计数: "
            "short_code=%s, error=%s",
            short_code,
            exc,
            exc_info=True,
        )


async def _scan_click_counter_keys(
    redis, max_keys: int = MAX_KEYS_PER_SYNC, pattern: str | None = None
) -> list:
    """有界扫描 Redis key；去重 SCAN 可能重复返回的键，失败时不调用阻塞式 KEYS。"""
    pattern = pattern or f"{CLICK_COUNTER_PREFIX}*"
    keys = []
    seen = set()
    cursor = 0
    max_iterations = 100000
    iteration = 0
    limit = max(1, int(max_keys))

    try:
        while True:
            cursor, batch_keys = await redis.scan(cursor, match=pattern, count=100)
            for key in batch_keys:
                if key in seen:
                    continue
                seen.add(key)
                keys.append(key)
                if len(keys) >= limit:
                    logger.info(
                        "本轮同步已达上限 %s 个计数器，剩余键将在下轮继续处理",
                        limit,
                    )
                    return keys

            iteration += 1
            if iteration >= max_iterations:
                logger.warning(
                    "Redis SCAN 达到最大迭代次数 %s，停止扫描；已收集 %s 个键，游标=%s",
                    max_iterations,
                    len(keys),
                    cursor,
                )
                break
            if cursor == 0:
                break
    except Exception as exc:
        # SCAN 失败时不能用 KEYS 扫描整个 keyspace；已收集的键仍可安全处理，
        # 未扫描到的键留在 Redis 中，等待下一轮任务重试。
        logger.warning(
            "Redis SCAN 失败，保留未扫描计数器供下轮重试；已收集 %s 个键：%s",
            len(keys),
            exc,
        )

    return keys


async def _sync_in_memory_counters_to_db(db: AsyncSession, short_codes: list[str] = None) -> int:
    """
    兼容读取旧版进程内计数快照，但禁止自动刷入 DB。

    旧版快照没有稳定 batch_id；历史 DB COMMIT 响应不确定时，无法判断计数是否
    已经入账。自动重放可能重复累计，因此保留快照并要求部署前人工核对。
    当前点击写入路径已在 Redis 不可用时直接执行 DB 原子自增，不再写入此内存表。
    """
    async with _counter_lock:
        legacy_count = sum(
            max(0, int(value))
            for code, value in _click_counters.items()
            if not short_codes or code in short_codes
        )
    if legacy_count:
        logger.critical(
            "检测到旧版进程内点击计数快照共 %s 次；因缺少批次幂等键，已禁止自动重放。"
            "请在部署前人工核对并归档 click_counters.json",
            legacy_count,
        )
    return 0


# 原子地把活跃计数切换为不可变 pending batch。
# 新点击继续写入 active key；pending key 在数据库确认入账且 ACK 前绝不设置 TTL。
_CLAIM_COUNTER_BATCH_LUA = """
local value = redis.call('GET', KEYS[1])
if not value then
    return 0
end
local count = tonumber(value)
if not count or count <= 0 then
    return 0
end
if redis.call('EXISTS', KEYS[2]) == 1 then
    return -1
end
redis.call('SET', KEYS[2], count)
redis.call('DEL', KEYS[1])
return count
"""


async def _acknowledge_click_batch(db: AsyncSession, redis, batch_id: str, pending_key: str) -> bool:
    """删除 pending key 得到确认后再标记账本 ACK；失败时保留账本供恢复。"""
    try:
        await redis.delete(pending_key)
    except Exception as exc:
        logger.error(
            "短链接点击批次 Redis ACK 失败，保留幂等账本等待重试: batch_id=%s error=%s",
            batch_id, exc, exc_info=True,
        )
        return False

    try:
        await db.execute(
            update(ShortLinkClickSyncBatch)
            .where(ShortLinkClickSyncBatch.batch_id == batch_id)
            .values(acknowledged_at=datetime.now(timezone.utc).replace(tzinfo=None))
        )
        await db.commit()
    except Exception as exc:
        # Redis pending 已删除，DB ACK 标记失败不会造成重复入账；账本暂时保留。
        logger.warning(
            "短链接点击批次已从 Redis 删除，但 ACK 状态写库失败: batch_id=%s error=%s",
            batch_id, exc, exc_info=True,
        )
        try:
            await db.rollback()
        except Exception:
            pass
    return True


async def _process_pending_click_batch(
    db: AsyncSession,
    redis,
    *,
    short_code: str,
    batch_id: str,
    pending_key: str,
    click_count: int,
) -> tuple[bool, bool]:
    """
    将一个不可变 pending batch 幂等入账。

    返回 (已安全处理, 本次是否新入账)。DB COMMIT 结果不确定时不 ACK，
    下轮通过唯一 batch_id 判断是否已提交，避免重复累加。
    """
    if click_count <= 0:
        logger.error("拒绝处理非正数短链接点击批次: batch_id=%s count=%s", batch_id, click_count)
        return False, False

    inserted = False
    try:
        link_result = await db.execute(
            select(ShortLink.id)
            .where(
                ShortLink.short_code == short_code,
                ShortLink.is_active.is_(True),
            )
            .limit(1)
        )
        short_link_id = link_result.scalar_one_or_none()
        if short_link_id is None:
            # 短链已删除或停用，与旧逻辑一致：不再为无效短链累计点击。
            await db.commit()
            await redis.delete(pending_key)
            return True, False

        existing_result = await db.execute(
            select(ShortLinkClickSyncBatch.batch_id)
            .where(ShortLinkClickSyncBatch.batch_id == batch_id)
            .limit(1)
        )
        already_committed = existing_result.scalar_one_or_none() is not None

        if not already_committed:
            db.add(ShortLinkClickSyncBatch(
                batch_id=batch_id,
                short_code=short_code,
                click_count=click_count,
            ))
            # 唯一 batch_id 必须先落入当前事务，再更新点击总数。
            await db.flush()
            update_result = await db.execute(
                update(ShortLink)
                .where(ShortLink.id == short_link_id)
                .values(click_count=ShortLink.click_count + click_count)
            )
            if getattr(update_result, "rowcount", 0) != 1:
                raise RuntimeError(
                    f"短链接点击批次更新行数异常: short_code={short_code}, "
                    f"batch_id={batch_id}, rowcount={getattr(update_result, 'rowcount', None)}"
                )
            await db.commit()
            inserted = True
        else:
            # 上次 DB COMMIT 成功但 Redis ACK 未完成；不重复更新 click_count。
            await db.commit()

    except IntegrityError:
        # 可能是全局同步锁租约过期导致两个 worker 同时处理同一 pending batch。
        # 唯一键冲突后回滚，再读取账本；存在即证明另一个 worker 已完成入账。
        try:
            await db.rollback()
            existing_result = await db.execute(
                select(ShortLinkClickSyncBatch.batch_id)
                .where(ShortLinkClickSyncBatch.batch_id == batch_id)
                .limit(1)
            )
            already_committed = existing_result.scalar_one_or_none() is not None
            await db.commit()
            if not already_committed:
                return False, False
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            logger.error(
                "短链接点击批次唯一键冲突后无法确认入账状态，保留 pending: batch_id=%s",
                batch_id, exc_info=True,
            )
            return False, False
    except Exception as exc:
        # 包括 COMMIT 响应丢失：不 ACK pending；重试时由 batch_id 账本去重。
        try:
            await db.rollback()
        except Exception:
            pass
        logger.error(
            "短链接点击批次入账失败或结果不确定，保留 pending 等待幂等恢复: "
            "short_code=%s batch_id=%s error=%s",
            short_code, batch_id, exc, exc_info=True,
        )
        return False, False

    acknowledged = await _acknowledge_click_batch(db, redis, batch_id, pending_key)
    return acknowledged, inserted


async def _cleanup_click_sync_batch_ledger(
    db: AsyncSession,
    redis,
    *,
    max_unacked: int = 100,
    max_delete: int = 500,
    retention_days: int = 30,
) -> None:
    """
    有界清理已确认 ACK 的账本记录。

    对 DB 已提交但 Redis DEL 响应丢失的记录，账本行本身证明 DB 已入账；
    若 pending key 已不存在，可安全补记 ACK。未确认 ACK 的行绝不按时间直接删除。
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        unacked_result = await db.execute(
            select(
                ShortLinkClickSyncBatch.batch_id,
                ShortLinkClickSyncBatch.short_code,
            )
            .where(ShortLinkClickSyncBatch.acknowledged_at.is_(None))
            .order_by(ShortLinkClickSyncBatch.created_at)
            .limit(max_unacked)
        )
        for batch_id, short_code in unacked_result.fetchall():
            pending_key = f"{CLICK_COUNTER_PREFIX}pending:{short_code}:{batch_id}"
            try:
                pending_exists = await redis.exists(pending_key)
            except Exception:
                # Redis 状态未知时不猜测 ACK 状态。
                continue
            if not pending_exists:
                await db.execute(
                    update(ShortLinkClickSyncBatch)
                    .where(ShortLinkClickSyncBatch.batch_id == batch_id)
                    .values(acknowledged_at=now)
                )

        cutoff = now - timedelta(days=max(1, retention_days))
        old_ack_result = await db.execute(
            select(ShortLinkClickSyncBatch.batch_id)
            .where(
                ShortLinkClickSyncBatch.acknowledged_at.is_not(None),
                ShortLinkClickSyncBatch.acknowledged_at < cutoff,
            )
            .order_by(ShortLinkClickSyncBatch.acknowledged_at)
            .limit(max_delete)
        )
        old_ids = old_ack_result.scalars().all()
        if old_ids:
            await db.execute(
                delete(ShortLinkClickSyncBatch)
                .where(ShortLinkClickSyncBatch.batch_id.in_(old_ids))
            )
        await db.commit()
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning("短链接点击刷盘幂等账本清理失败（不影响 pending 重试）: %s", exc, exc_info=True)



async def _sync_redis_click_counter_batches(
    db: AsyncSession,
    redis,
    short_codes: list[str] | None = None,
    max_keys: int = MAX_KEYS_PER_SYNC,
) -> int:
    """通过 Redis pending batch + DB 唯一账本完成可恢复的短链接点击刷盘。"""
    processed = 0
    inserted_codes: set[str] = set()
    pending_pattern = f"{CLICK_COUNTER_PREFIX}pending:*"
    pending_keys = await _scan_click_counter_keys(redis, max_keys, pattern=pending_pattern)
    pending_seen = set(pending_keys)

    # 优先处理上轮遗留 pending；这些 key 可能已在 DB 入账，只差 ACK。
    for pending_key in pending_keys:
        suffix = pending_key[len(pending_pattern.split("*", 1)[0]):]
        try:
            short_code, batch_id = suffix.rsplit(":", 1)
            if short_codes and short_code not in short_codes:
                continue
            raw_count = await redis.get(pending_key)
            click_count = int(raw_count) if raw_count is not None else 0
        except Exception as exc:
            logger.error("读取 pending 点击批次失败，保留待下轮处理: key=%s error=%s", pending_key, exc)
            continue
        if click_count <= 0:
            logger.error("pending 点击批次数值无效，保留人工核验: key=%s value=%s", pending_key, raw_count)
            continue
        ok, inserted = await _process_pending_click_batch(
            db, redis, short_code=short_code, batch_id=batch_id,
            pending_key=pending_key, click_count=click_count,
        )
        if ok:
            processed += 1
            if inserted:
                inserted_codes.add(short_code)

    # 再把 active counter 原子切换成 pending；切换后并发新点击写入新的 active key。
    active_keys = await _scan_click_counter_keys(redis, max_keys, pattern=f"{CLICK_COUNTER_PREFIX}*")
    for active_key in active_keys:
        if ":pending:" in active_key or active_key in pending_seen:
            continue
        short_code = active_key[len(CLICK_COUNTER_PREFIX):]
        if not short_code or short_codes and short_code not in short_codes:
            continue
        batch_id = uuid.uuid4().hex
        pending_key = f"{CLICK_COUNTER_PREFIX}pending:{short_code}:{batch_id}"
        try:
            claimed = int(await redis.eval(
                _CLAIM_COUNTER_BATCH_LUA, 2, active_key, pending_key
            ))
        except Exception as exc:
            # Redis 执行结果不确定时，pending 可能已创建；下轮扫描 pending 自动恢复。
            logger.error(
                "切换短链接点击计数为 pending 结果不确定: short_code=%s batch_id=%s error=%s",
                short_code, batch_id, exc, exc_info=True,
            )
            continue
        if claimed <= 0:
            continue

        ok, inserted = await _process_pending_click_batch(
            db, redis, short_code=short_code, batch_id=batch_id,
            pending_key=pending_key, click_count=claimed,
        )
        if ok:
            processed += 1
            if inserted:
                inserted_codes.add(short_code)

    await _cleanup_click_sync_batch_ledger(db, redis)
    logger.info(
        "短链接点击幂等刷盘完成: processed_batches=%s newly_updated_links=%s",
        processed, len(inserted_codes),
    )
    return len(inserted_codes)



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
    try:
        redis = await get_redis_client()
    except Exception as exc:
        # 无法确认 Redis 状态时也无法确认全局锁是否可用。
        # 旧的进程内计数仅是兼容恢复路径，不能在多 Worker 下无锁同步。
        logger.error("获取 Redis 客户端失败，跳过短链接计数同步以避免无锁并发入账: %s", exc)
        return 0

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
        # Redis 已连接但分布式锁操作失败时，无法证明当前进程拥有同步权。
        # 必须 fail-closed；继续执行会让多个 Worker 同时读取同一批计数并重复入账。
        logger.error("获取短链接点击同步分布式锁失败，本轮安全跳过并等待下次重试: %s", e)
        return 0
    
    try:
        if not redis:
            # 新版点击写入在 Redis 不可用时直接走 DB 原子自增。
            # 旧版本地快照缺少稳定幂等键，禁止自动刷盘，避免 COMMIT 结果不确定时重复累计。
            async with _counter_lock:
                has_legacy_snapshot = bool(_click_counters)
            if has_legacy_snapshot:
                await _sync_in_memory_counters_to_db(db, short_codes)
            return 0

        # Redis 恢复后先补写历史进程内快照；随后使用 pending batch + DB 唯一账本刷盘。
        await _sync_in_memory_counters_to_db(db, short_codes)
        await persist_counters()
        return await _sync_redis_click_counter_batches(db, redis, short_codes)

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
        # 所有锁都获取失败，检查短链接是否存在
        # 如果不存在，清理计数器；如果存在，保留以便重试
        try:
            result = await db.execute(
                select(ShortLink.short_code, ShortLink.is_active).where(
                    ShortLink.short_code.in_(short_codes)
                )
            )
            existing_codes = {row[0] for row in result.fetchall() if row[1]}
            await db.commit()
            
            # 清理不存在的短链接计数器
            for code, count, redis_key in batch:
                if code not in existing_codes:
                    if redis and redis_key:
                        try:
                            await redis.delete(redis_key)
                            logger.info(f"清理不存在短链接的Redis计数器（锁获取失败但不存在）: short_code={code}")
                        except Exception as e:
                            logger.warning(f"清理Redis计数器失败: short_code={code}, error={e}")
            
            # 只保留存在的短链接用于重试
            batch = [item for item in batch if item[0] in existing_codes]
            
            if batch:
                failed_codes = [code for code, _, _ in batch]
                failed_counts = {code: count for code, count, _ in batch}
                logger.warning(
                    f"无法获取任何短链接锁，将在下次同步时重试: "
                    f"failed_codes={failed_codes}, failed_counts={failed_counts}"
                )
            else:
                logger.info("所有短链接都不存在，已清理计数器")
        except Exception as e:
            logger.warning(f"检查短链接存在性失败（锁获取失败）: {e}")
            try:
                await db.rollback()
            except Exception:
                pass
            failed_codes = [code for code, _, _ in batch]
            failed_counts = {code: count for code, count, _ in batch}
            logger.warning(
                f"无法获取任何短链接锁，将在下次同步时重试: "
                f"failed_codes={failed_codes}, failed_counts={failed_counts}"
            )
        
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
        # 事务级 RC + 临时锁等待；finally 必须还原 SESSION，避免连接池污染
        await _tune_session_for_click_sync(db, lock_wait_timeout=0)
        
        # 使用SELECT FOR UPDATE SKIP LOCKED先锁定记录，避免死锁
        # 这样可以确保只更新能够立即锁定的记录，跳过已被其他事务锁定的记录
        # 增加重试机制：如果记录被锁定，等待一小段时间后重试，而不是立即跳过
        locked_short_codes = [code for code, _, _ in locked_batch]
        
        # 尝试锁定记录，带重试机制
        # 如果记录被短暂锁定，等待一小段时间后重试，而不是立即跳过
        successfully_locked_batch = []
        skipped_batch = []
        remaining_batch = locked_batch.copy()
        
        for lock_attempt in range(LOCK_RETRY_MAX_ATTEMPTS + 1):
            if not remaining_batch:
                break
            
            # 先查询并锁定记录（使用SKIP LOCKED跳过已被锁定的记录）
            current_codes = [code for code, _, _ in remaining_batch]
            current_placeholders = ", ".join([f":code_{i}" for i in range(len(current_codes))])
            current_params = {f"code_{i}": code for i, code in enumerate(current_codes)}
            
            select_result = await db.execute(
                text(f"""
                    SELECT short_code 
                    FROM short_links 
                    WHERE short_code IN ({current_placeholders})
                    ORDER BY short_code
                    FOR UPDATE SKIP LOCKED
                """),
                current_params
            )
            
            # 获取成功锁定的short_code
            locked_codes_set = {row[0] for row in select_result.fetchall()}
            
            # 分离成功锁定和仍被锁定的记录
            current_success = [item for item in remaining_batch if item[0] in locked_codes_set]
            current_skipped = [item for item in remaining_batch if item[0] not in locked_codes_set]
            
            # 将成功的记录加入成功列表
            successfully_locked_batch.extend(current_success)
            remaining_batch = current_skipped
            
            # 如果还有被锁定的记录，且不是最后一次尝试，则等待后重试
            if remaining_batch and lock_attempt < LOCK_RETRY_MAX_ATTEMPTS:
                skipped_codes = [code for code, _, _ in remaining_batch]
                logger.debug(
                    f"部分记录被其他事务锁定（第 {lock_attempt + 1} 次尝试），"
                    f"等待 {LOCK_RETRY_DELAY * 1000:.0f} 毫秒后重试: "
                    f"skipped_codes={skipped_codes}"
                )
                # 回滚当前事务，释放锁（即使有成功的记录也回滚，确保一致性）
                await db.rollback()
                # 等待一小段时间，让其他事务完成
                await asyncio.sleep(LOCK_RETRY_DELAY)
                # 回滚后下一事务需重新 SET TRANSACTION（仅下一事务生效）
                await _tune_session_for_click_sync(db, lock_wait_timeout=0)
                # 重置成功列表，因为已经回滚，需要重新锁定
                successfully_locked_batch = []
            elif remaining_batch:
                # 最后一次尝试后仍有被锁定的记录，记录为跳过
                skipped_batch = remaining_batch
                skipped_codes = [code for code, _, _ in skipped_batch]
                skipped_counts = {code: count for code, count, _ in skipped_batch}
                logger.debug(
                    f"部分记录被其他事务锁定（已重试 {LOCK_RETRY_MAX_ATTEMPTS} 次），"
                    f"跳过本次更新，将在下次同步时重试: "
                    f"skipped_codes={skipped_codes}, "
                    f"skipped_counts={skipped_counts}"
                )
        
        if not successfully_locked_batch:
            # 所有记录都被锁定或被跳过，检查短链接是否存在
            # 如果不存在，清理计数器；如果存在，保留以便重试
            await db.rollback()
            
            # 检查被跳过的短链接是否存在
            all_skipped_codes = [code for code, _, _ in skipped_batch]
            if all_skipped_codes:
                try:
                    result = await db.execute(
                        select(ShortLink.short_code, ShortLink.is_active).where(
                            ShortLink.short_code.in_(all_skipped_codes)
                        )
                    )
                    existing_skipped = {row[0] for row in result.fetchall() if row[1]}
                    await db.commit()
                    
                    # 清理不存在的短链接计数器
                    for code, count, redis_key in skipped_batch:
                        if code not in existing_skipped:
                            if redis and redis_key:
                                try:
                                    await redis.delete(redis_key)
                                    logger.info(f"清理不存在短链接的Redis计数器（记录被锁定但不存在）: short_code={code}")
                                except Exception as e:
                                    logger.warning(f"清理Redis计数器失败: short_code={code}, error={e}")
                    
                    # 只保留存在的短链接用于重试
                    skipped_batch = [item for item in skipped_batch if item[0] in existing_skipped]
                except Exception as e:
                    logger.warning(f"检查被跳过短链接存在性失败: {e}")
                    await db.rollback()
            
            # 释放已获取的分布式锁
            await _release_item_locks(redis, acquired_locks)
            
            # 合并所有失败的批次项（锁获取失败 + 记录被跳过）
            all_failed = failed_batch + skipped_batch
            if all_failed:
                failed_reason = "记录被其他事务锁定" if skipped_batch else "无法获取分布式锁"
                failed_codes = [code for code, _, _ in all_failed]
                failed_counts = {code: count for code, count, _ in all_failed}
                logger.warning(
                    f"批量更新失败（{failed_reason}），将在下次同步时重试: "
                    f"failed_codes={failed_codes}, failed_counts={failed_counts}"
                )
            
            return 0, [], all_failed
        
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
                        # DECRBY 会保留 Redis key 原有 TTL；不能用 SET 覆盖剩余计数，
                        # 否则并发新点击留下的计数会变成永久 key。
                        delete_lua = _DECREMENT_COUNTER_LUA
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
            # 没有记录被更新，可能是所有短链接都不存在或已禁用
            # 需要检查哪些短链接不存在，以便清理Redis计数器
            logger.warning(f"批量更新没有更新任何记录，检查短链接是否存在")
            
            # 回滚事务，因为更新失败
            await db.rollback()
            
            # 释放分布式锁
            await _release_item_locks(redis, acquired_locks)
            
            # 查询哪些短链接存在且激活（需要新的事务）
            # 注意：由于已经回滚，SQLAlchemy会在下次查询时自动开始新事务
            # 使用只读查询，避免锁定记录
            existing_codes = set()
            try:
                # 使用新的查询，SQLAlchemy会自动开始新事务
                result = await db.execute(
                    select(ShortLink.short_code, ShortLink.is_active).where(
                        ShortLink.short_code.in_(locked_short_codes)
                    )
                )
                existing_codes = {row[0] for row in result.fetchall() if row[1]}  # 只包含激活的
                # 查询后立即提交，释放连接
                await db.commit()
            except Exception as query_error:
                # 如果查询失败，记录错误但继续处理
                logger.warning(f"查询短链接存在性失败: {query_error}")
                try:
                    await db.rollback()
                except Exception:
                    pass
                existing_codes = set()
            
            # 删除不存在的短链接的Redis计数器
            # 注意：由于短链接不存在，不会有新的点击，可以直接删除
            cleaned_codes = []
            retry_batch = []
            for short_code, count_value, redis_key in successfully_locked_batch:
                if short_code not in existing_codes:
                    cleaned_codes.append(short_code)
                    logger.warning(f"短链接不存在或已禁用，删除Redis计数器: short_code={short_code}")
                    if redis_key:  # 只有在redis_key存在时才尝试删除
                        try:
                            deleted = await redis.delete(redis_key)
                            if deleted:
                                logger.info(f"成功删除不存在的短链接的Redis计数器: short_code={short_code}")
                        except Exception as e:
                            logger.warning(f"删除Redis计数器失败: key={redis_key}, error={e}")
                else:
                    # 短链接存在，加入重试列表
                    retry_batch.append((short_code, count_value, redis_key))
            
            if cleaned_codes:
                logger.info(f"清理了 {len(cleaned_codes)} 个不存在或已禁用的短链接计数器: codes={cleaned_codes}")
            
            # 合并所有失败的批次项（锁获取失败 + 记录被跳过 + 更新失败但存在的）
            all_failed = failed_batch + skipped_batch + retry_batch
            if all_failed:
                failed_codes = [code for code, _, _ in all_failed]
                failed_counts = {code: count for code, count, _ in all_failed}
                logger.warning(
                    f"批量更新失败（没有记录被更新），将在下次同步时重试: "
                    f"failed_codes={failed_codes}, failed_counts={failed_counts}"
                )
            
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
            except Exception:
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
        except Exception:
            pass
        # 注意：由于现在不再在获取时删除计数器，计数器仍然存在，无需恢复
        # 计数器会在下次同步时重试
        return 0, [], batch
    finally:
        await _restore_session_after_click_sync(db)
    
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
    try:
        for attempt in range(max_retries):
            try:
                await _tune_session_for_click_sync(db, lock_wait_timeout=5)
                
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
                    except Exception:
                        pass
                    return False
            except Exception as e:
                logger.error(
                    f"更新短链接点击次数失败: short_code={short_code}, error={e}",
                    exc_info=True
                )
                try:
                    await db.rollback()
                except Exception:
                    pass
                return False
        
        return False
    finally:
        await _restore_session_after_click_sync(db)


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
    batch_size: int = 5,
) -> int:
    """
    已弃用：调用方传入的裸计数快照没有稳定 batch_id，无法安全处理 COMMIT 响应丢失。

    禁止继续走旧的“DB 自增后 Redis 无幂等 ACK”路径。调用方应改用
    sync_click_counts_to_db()，由该函数通过 Redis pending batch 生成稳定幂等键。
    """
    if updates:
        raise RuntimeError(
            "sync_click_counts_to_db_batch 已停用：裸计数快照不具备幂等恢复能力；"
            "请改用 sync_click_counts_to_db()"
        )
    return 0


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

