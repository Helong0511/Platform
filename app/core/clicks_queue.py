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

# Redis队列键
CLICKS_QUEUE_KEY = "clicks:queue"
# 队列最大长度（防止内存溢出）
MAX_QUEUE_SIZE = 100000
# 批量处理大小
BATCH_SIZE = 1000


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


async def dequeue_clicks(count: int = BATCH_SIZE) -> list[Dict[str, Any]]:
    """
    从Redis队列中批量取出点击记录
    
    Args:
        count: 取出的数量
        
    Returns:
        点击记录列表
    """
    redis = await get_redis_client()
    if not redis:
        return []
    
    try:
        # 批量从队列左侧取出（FIFO）
        # 注意：redis-py的lpop不支持count参数，需要循环取出
        clicks = []
        for _ in range(min(count, await redis.llen(CLICKS_QUEUE_KEY))):
            click_json = await redis.lpop(CLICKS_QUEUE_KEY)
            if not click_json:
                break
            
            try:
                click_data = json.loads(click_json)
                clicks.append(click_data)
            except json.JSONDecodeError as e:
                logger.warning(f"反序列化点击记录失败: {click_json[:100]}, error={e}")
        
        if clicks:
            logger.debug(f"从队列取出 {len(clicks)} 条点击记录")
        return clicks
    except Exception as e:
        logger.error(f"从队列取出点击记录失败: error={e}", exc_info=True)
        return []


async def get_queue_length() -> int:
    """
    获取队列长度
    
    Returns:
        队列中的记录数
    """
    redis = await get_redis_client()
    if not redis:
        return 0
    
    try:
        return await redis.llen(CLICKS_QUEUE_KEY)
    except Exception as e:
        logger.error(f"获取队列长度失败: error={e}")
        return 0


async def drain_clicks_queue(max_batches: int = 100) -> int:
    """
    清空 Redis 点击队列（令牌模式不落库时用于丢弃历史积压）。

    Returns:
        丢弃的记录条数
    """
    drained = 0
    for _ in range(max_batches):
        clicks = await dequeue_clicks(BATCH_SIZE)
        if not clicks:
            break
        drained += len(clicks)
    if drained:
        logger.info("已清空 clicks 队列积压 %s 条（不落库模式）", drained)
    return drained

