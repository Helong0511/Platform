"""
点击记录 Redis 队列模块（高并发写库削峰）。

职责：将点击先入 ``clicks:queue``，由定时任务批量落库；令牌模式且关闭落库时直接 no-op。

在系统中的位置：``app.core.clicks_queue``，与 ``tracking.click_persist`` 策略联动。
"""
import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Redis 队列键：主队列 + 处理中 + 死信
CLICKS_QUEUE_KEY = "clicks:queue"
CLICKS_PROCESSING_KEY = "clicks:processing"
CLICKS_DLQ_KEY = "clicks:dead"
# 队列最大长度（防止内存溢出）
MAX_QUEUE_SIZE = 100000
# 批量处理大小
BATCH_SIZE = 1000
# 默认最大重试（可被 settings.CLICKS_QUEUE_MAX_RETRIES 覆盖）
DEFAULT_MAX_RETRIES = 5
_RETRY_FIELD = "_queue_retry"


async def enqueue_click(click_data: Dict[str, Any]) -> bool:
    """
    将点击记录加入Redis队列（非阻塞，高并发优化）
    
    Args:
        click_data: 点击记录数据字典
        
    Returns:
        是否成功加入队列
    """
    from app.core.tracking.click_persist import should_persist_clicks_to_db

    if not should_persist_clicks_to_db():
        return True

    redis = await get_redis_client()
    if not redis:
        logger.warning("Redis不可用，无法使用队列缓冲，点击记录可能丢失")
        return False
    
    try:
        # 序列化点击数据
        click_json = json.dumps(click_data, default=str)
        
        # 检查队列长度，防止内存溢出
        queue_length = await redis.llen(CLICKS_QUEUE_KEY)
        if queue_length >= MAX_QUEUE_SIZE:
            logger.error(
                f"点击队列已满（{queue_length}/{MAX_QUEUE_SIZE}），"
                f"点击记录可能丢失: click_id={click_data.get('click_id')}"
            )
            return False
        
        # 将点击记录加入队列（右侧推入，左侧弹出）
        await redis.rpush(CLICKS_QUEUE_KEY, click_json)
        
        logger.debug(
            f"点击记录已加入队列: click_id={click_data.get('click_id')}, "
            f"队列长度={queue_length + 1}"
        )
        return True
    except Exception as e:
        logger.error(
            f"加入点击队列失败: click_id={click_data.get('click_id')}, error={e}",
            exc_info=True
        )
        return False


def _decode_click_payload(click_json: str) -> Optional[Dict[str, Any]]:
    """解析队列中的 JSON 载荷；失败返回 None。"""
    try:
        return json.loads(click_json)
    except json.JSONDecodeError as e:
        logger.warning("反序列化点击记录失败: %s, error=%s", click_json[:100], e)
        return None


def _max_retries() -> int:
    try:
        from app.core.config import settings

        return int(getattr(settings, "CLICKS_QUEUE_MAX_RETRIES", DEFAULT_MAX_RETRIES))
    except Exception:
        return DEFAULT_MAX_RETRIES


async def move_to_dead_letter(raw: str, reason: str = "") -> bool:
    """将原始消息移入死信队列并移出 processing。"""
    redis = await get_redis_client()
    if not redis:
        return False
    try:
        envelope = {
            "reason": reason or "unknown",
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "raw": raw,
        }
        await redis.lrem(CLICKS_PROCESSING_KEY, 1, raw)
        await redis.rpush(CLICKS_DLQ_KEY, json.dumps(envelope, default=str))
        logger.error("点击消息已入死信队列: reason=%s raw=%s", reason, raw[:120])
        return True
    except Exception as e:
        logger.error("写入死信队列失败: %s", e, exc_info=True)
        return False


async def reserve_clicks(count: int = BATCH_SIZE) -> list[tuple[str, Dict[str, Any]]]:
    """
    从主队列原子挪到 processing 队列（RPOPLPUSH），供批量落库。

    Returns:
        [(raw_json, click_data), ...]；解析失败的条目进入 DLQ。
    """
    redis = await get_redis_client()
    if not redis:
        return []

    reserved: list[tuple[str, Dict[str, Any]]] = []
    try:
        queue_length = await redis.llen(CLICKS_QUEUE_KEY)
        take = min(count, queue_length)
        for _ in range(take):
            click_json = await redis.rpoplpush(CLICKS_QUEUE_KEY, CLICKS_PROCESSING_KEY)
            if not click_json:
                break
            if isinstance(click_json, bytes):
                click_json = click_json.decode("utf-8")
            click_data = _decode_click_payload(click_json)
            if click_data is None:
                await move_to_dead_letter(click_json, reason="invalid_json")
                continue
            reserved.append((click_json, click_data))

        if reserved:
            logger.debug("从队列预留 %s 条点击记录（processing）", len(reserved))
        return reserved
    except Exception as e:
        logger.error("预留点击记录失败: error=%s", e, exc_info=True)
        return []


async def acknowledge_reserved(raw_items: list[str]) -> None:
    """落库成功后从 processing 队列确认删除。"""
    if not raw_items:
        return
    redis = await get_redis_client()
    if not redis:
        return
    try:
        for raw in raw_items:
            await redis.lrem(CLICKS_PROCESSING_KEY, 1, raw)
    except Exception as e:
        logger.error("确认点击队列条目失败: error=%s", e, exc_info=True)


async def requeue_reserved(raw_items: list[str]) -> int:
    """
    落库失败时回队；超过最大重试次数则进入死信队列。
    """
    if not raw_items:
        return 0
    redis = await get_redis_client()
    if not redis:
        logger.error("Redis 不可用，无法回队 %s 条点击记录", len(raw_items))
        return 0

    max_retries = _max_retries()
    requeued = 0
    dead = 0
    try:
        for raw in raw_items:
            await redis.lrem(CLICKS_PROCESSING_KEY, 1, raw)
            data = _decode_click_payload(raw)
            if data is None:
                await redis.rpush(
                    CLICKS_DLQ_KEY,
                    json.dumps(
                        {
                            "reason": "invalid_json_on_requeue",
                            "failed_at": datetime.now(timezone.utc).isoformat(),
                            "raw": raw,
                        },
                        default=str,
                    ),
                )
                dead += 1
                continue

            retry = int(data.get(_RETRY_FIELD, 0) or 0) + 1
            data[_RETRY_FIELD] = retry
            new_raw = json.dumps(data, default=str)
            if retry > max_retries:
                await redis.rpush(
                    CLICKS_DLQ_KEY,
                    json.dumps(
                        {
                            "reason": f"max_retries:{max_retries}",
                            "failed_at": datetime.now(timezone.utc).isoformat(),
                            "raw": new_raw,
                        },
                        default=str,
                    ),
                )
                dead += 1
            else:
                await redis.lpush(CLICKS_QUEUE_KEY, new_raw)
                requeued += 1

        if requeued:
            logger.warning("已将 %s 条点击记录回队等待重试", requeued)
        if dead:
            logger.error("已将 %s 条点击记录移入死信队列", dead)
        return requeued
    except Exception as e:
        logger.error("点击记录回队失败: error=%s", e, exc_info=True)
        return requeued


async def get_dead_letter_length() -> int:
    """死信队列长度。"""
    redis = await get_redis_client()
    if not redis:
        return 0
    try:
        return await redis.llen(CLICKS_DLQ_KEY)
    except Exception as e:
        logger.error("获取死信队列长度失败: error=%s", e)
        return 0


async def recover_processing_queue() -> int:
    """
    将 processing 队列全部移回主队列（worker 崩溃后的启动恢复）。

    调度侧应保证单消费者；多消费者场景勿调用。
    """
    redis = await get_redis_client()
    if not redis:
        return 0
    recovered = 0
    try:
        while True:
            raw = await redis.rpop(CLICKS_PROCESSING_KEY)
            if not raw:
                break
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            await redis.lpush(CLICKS_QUEUE_KEY, raw)
            recovered += 1
        if recovered:
            logger.info("已从 processing 队列恢复 %s 条点击记录到主队列", recovered)
        return recovered
    except Exception as e:
        logger.error("恢复 processing 点击队列失败: error=%s", e, exc_info=True)
        return recovered


async def dequeue_clicks(count: int = BATCH_SIZE) -> list[Dict[str, Any]]:
    """
    从 Redis 队列批量取出点击记录（兼容旧调用方）。

    新代码请使用 reserve_clicks / acknowledge_reserved / requeue_reserved。
    """
    reserved = await reserve_clicks(count)
    if not reserved:
        return []
    raw_items = [raw for raw, _ in reserved]
    await acknowledge_reserved(raw_items)
    return [data for _, data in reserved]


async def get_queue_length() -> int:
    """
    获取主队列长度（不含 processing 中队列）。
    """
    redis = await get_redis_client()
    if not redis:
        return 0

    try:
        return await redis.llen(CLICKS_QUEUE_KEY)
    except Exception as e:
        logger.error("获取队列长度失败: error=%s", e)
        return 0


async def get_processing_queue_length() -> int:
    """获取 processing 队列长度。"""
    redis = await get_redis_client()
    if not redis:
        return 0
    try:
        return await redis.llen(CLICKS_PROCESSING_KEY)
    except Exception as e:
        logger.error("获取 processing 队列长度失败: error=%s", e)
        return 0


async def drain_clicks_queue(max_batches: int = 100) -> int:
    """
    清空 Redis 点击队列（令牌模式不落库时用于丢弃历史积压）。

    Returns:
        丢弃的记录条数
    """
    await recover_processing_queue()
    drained = 0
    for _ in range(max_batches):
        reserved = await reserve_clicks(BATCH_SIZE)
        if not reserved:
            break
        raw_items = [raw for raw, _ in reserved]
        await acknowledge_reserved(raw_items)
        drained += len(reserved)
    if drained:
        logger.info("已清空 clicks 队列积压 %s 条（不落库模式）", drained)
    return drained

