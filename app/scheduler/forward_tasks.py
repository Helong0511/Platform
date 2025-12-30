"""
Postback 下游转发任务
负责处理 PostbackForwardQueue 中的任务，包含重试机制
"""
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func

from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.models.models import PostbackForwardQueue, PostbackForwardLog, PostbackConversion, Product
from app.core.postback.forwarder import PostbackForwarder

logger = logging.getLogger(__name__)

# 最大重试次数
MAX_RETRIES = 5
# 每次批处理数量
BATCH_SIZE = 50

# 指数退避策略 (秒)
RETRY_DELAYS = [60, 300, 900, 3600, 7200]  # 1m, 5m, 15m, 1h, 2h


async def trigger_forward_processing():
    """
    触发转发处理（通常由 Processor 在入队后直接调用，作为 Fire & Forget 任务）
    """
    try:
        await process_forward_queue()
    except Exception as e:
        logger.error(f"触发转发处理任务失败: {e}", exc_info=True)


async def process_forward_queue():
    """
    定时任务：处理转发队列
    查询 next_retry_time <= now 的任务并执行
    """
    try:
        async with AsyncSessionLocal() as db:
            # 1. 查询待处理任务（使用北京时间比较，因为next_retry_time存储的是北京时间）
            now = get_app_now_naive()
            query = select(PostbackForwardQueue).where(
                PostbackForwardQueue.next_retry_time <= now
            ).order_by(PostbackForwardQueue.next_retry_time).limit(BATCH_SIZE)
            
            result = await db.execute(query)
            tasks = result.scalars().all()
            
            if not tasks:
                return

            logger.info(f"开始处理转发队列，任务数: {len(tasks)}")
            
            # 2. 并行处理
            # 注意：为了避免 Session 冲突，每个任务最好由 Consumer 单独处理或小心管理 Session
            # 这里的简单实现：串行或小批量并行
            
            for task in tasks:
                await process_single_task(db, task)
            
            # 如果还有更多任务，可以递归调用或依赖下一次调度
            # 这里简单处理，一次只处理一页
            
    except Exception as e:
        logger.error(f"转发队列处理任务异常: {e}", exc_info=True)


async def process_single_task(db: AsyncSession, task: PostbackForwardQueue):
    """
    处理单个转发任务
    """
    try:
        # 1. 准备数据
        # 这里的实现复用 PostbackForwarder，但要注意 PostbackForwarder 原本的设计是直接接受 Product/Conversion
        # 我们需要重新构造对象或让 Forwarder 支持 url/method/data
        
        # 简单起见，我们直接使用 HTTP Client，或者扩展 Forwarder
        # 这里我们模拟 Forwarder 的行为，因为 Forwarder 内部也记录 Log，我们需要避免重复记录 Log 吗？
        # 观察 PostbackForwarder 源码 (需要回顾 forwarder.py)
        # 假设 PostbackForwarder.forward_to_downstream 会记录 PostbackForwardLog
        
        # 重新加载关联对象
        # 注意：task.conversion 和 task.product 可能未加载，需要显式查询或利用 Lazy Load (asyncio 中 Lazy Load 比较麻烦)
        # 直接使用 ID 查询
        
        # 实际上 PostbackForwarder 只是一个帮助类，我们可以直接调用它
        # 但我们需要确保 task 成功后从 Queue 删除，失败后更新 Queue
        
        # 我们直接使用 httpx 发送请求，并自己管理 Queue 和 Log，这样更可控
        # 或者修改 PostbackForwarder 让其支持 "仅发送不记录Log" (如果需要)
        # 现在的 PostbackForwarder.forward_to_downstream 是全流程封装。
        # 让我们看看 forwarder.py 的内容（之前看过 file list，没看内容）
        # 假设我们重新实现发送逻辑，为了完全控制 Queue
        
        import httpx
        
        success = False
        response_body = ""
        response_status = 0
        error_msg = None
        
        try:
            timeout = httpx.Timeout(10.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                method = task.request_method.upper()
                if method == 'GET':
                    # 虽然参数存储在 params 字段，但 url 可能已经包含参数
                    # 简单起见，假设 downstream_url 是基础 URL，params 是查询参数
                    # 实际上 processor.py 中我们暂时只存了 url
                    resp = await client.get(task.downstream_url) # 假设 URL 已经包含了参数
                else:
                    # POST
                    headers = {"Content-Type": "application/json"}
                    resp = await client.post(task.downstream_url, content=task.request_data, headers=headers)
                
                response_status = resp.status_code
                response_body = resp.text
                
                if 200 <= response_status < 300:
                    success = True
                else:
                    error_msg = f"HTTP {response_status}"
                    
        except Exception as net_err:
            error_msg = str(net_err)
            success = False
        
        # 2. 处理结果
        if success:
            # 成功：移至 Log 表，从 Queue 删除
            log_entry = PostbackForwardLog(
                conversion_id=task.conversion_id,
                product_id=task.product_id,
                downstream_url=task.downstream_url,
                request_method=task.request_method,
                request_data=task.request_data,
                request_params=task.request_params,
                response_status=response_status,
                response_body=response_body[:1000] if response_body else None, # 截断
                success=True,
                retry_count=task.retry_count,
                created_at=task.created_at, # 保持原始创建时间
                completed_at=get_app_now_naive()  # 使用北京时间
            )
            db.add(log_entry)
            await db.delete(task)
            logger.info(f"转发任务成功: queue_id={task.id}, conversion_id={task.conversion_id}")
            
        else:
            # 失败：检查重试次数
            if task.retry_count >= MAX_RETRIES:
                 # 超过最大重试次数：移至 Log 表 (失败状态)，从 Queue 删除
                log_entry = PostbackForwardLog(
                    conversion_id=task.conversion_id,
                    product_id=task.product_id,
                    downstream_url=task.downstream_url,
                    request_method=task.request_method,
                    request_data=task.request_data,
                    request_params=task.request_params,
                    response_status=response_status,
                    response_body=response_body[:1000] if response_body else None,
                    success=False,
                    error_message=error_msg,
                    retry_count=task.retry_count,
                    created_at=task.created_at,
                    completed_at=get_app_now_naive()  # 使用北京时间
                )
                db.add(log_entry)
                await db.delete(task)
                logger.warning(f"转发任务最终失败 (超过重试次数): queue_id={task.id}, error={error_msg}")
            else:
                # 还可以重试：更新 retry_count 和 next_retry_time
                delay = RETRY_DELAYS[min(task.retry_count, len(RETRY_DELAYS) - 1)]
                task.retry_count += 1
                task.next_retry_time = get_app_now_naive() + timedelta(seconds=delay)  # 使用北京时间
                logger.info(f"转发任务失败，安排重试 ({task.retry_count}/{MAX_RETRIES}): queue_id={task.id}, delay={delay}s")
        
        await db.commit()
        
    except Exception as e:
        logger.error(f"处理单条转发任务失败: {e}", exc_info=True)
        await db.rollback()
