"""
通知汇总任务
定时处理 hourly 和 daily 频率的通知汇总
"""
import json
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.redis_client import get_redis_client
from app.core.postback.notifier import PostbackNotifier
from app.services.telegram_notification_service import TelegramNotificationService
from app.models.models import Client, Product, PostbackConversion
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# 任务执行结果存储（用于保存到last_error字段）
_task_results: dict[str, str] = {}


def get_task_result(task_name: str) -> str | None:
    """获取任务执行结果"""
    return _task_results.get(task_name)


def set_task_result(task_name: str, result: str) -> None:
    """设置任务执行结果"""
    _task_results[task_name] = result


async def process_hourly_notifications(db: AsyncSession) -> Dict[str, Any]:
    """
    处理每小时汇总通知
    
    Args:
        db: 数据库会话
        
    Returns:
        处理结果字典
    """
    result = {
        'success': True,
        'processed_clients': 0,
        'sent_notifications': 0,
        'errors': []
    }
    
    try:
        redis_client = await get_redis_client()
        if not redis_client:
            result['success'] = False
            result['errors'].append('Redis 不可用')
            return result
        
        # 获取所有 hourly 队列的键
        pattern = "notification_queue:hourly:*"
        keys = []
        async for key in redis_client.scan_iter(match=pattern):
            keys.append(key.decode() if isinstance(key, bytes) else key)
        
        if not keys:
            logger.debug("没有待处理的每小时汇总通知")
            return result
        
        # 处理每个客户的队列
        for queue_key in keys:
            try:
                # 提取客户ID
                client_id_str = queue_key.split(':')[-1]
                if client_id_str == 'unknown':
                    continue
                
                client_id = int(client_id_str)
                
                # 从队列中取出所有通知项
                notifications = []
                while True:
                    item_json = await redis_client.rpop(queue_key)
                    if not item_json:
                        break
                    
                    try:
                        item = json.loads(item_json.decode() if isinstance(item_json, bytes) else item_json)
                        notifications.append(item)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"解析通知项失败: {item_json[:100]}, error={e}")
                        continue
                
                if not notifications:
                    continue
                
                # 按产品分组
                grouped_by_product = defaultdict(list)
                for notif in notifications:
                    product_id = notif.get('product_id')
                    grouped_by_product[product_id].append(notif)
                
                # 为每个产品发送汇总通知
                for product_id, notif_list in grouped_by_product.items():
                    try:
                        # 获取客户和产品信息
                        client = None
                        product = None
                        
                        if client_id:
                            client_result = await db.execute(
                                select(Client).where(Client.id == client_id)
                            )
                            client = client_result.scalars().first()
                        
                        if product_id:
                            product_result = await db.execute(
                                select(Product).where(Product.id == product_id)
                            )
                            product = product_result.scalars().first()
                        
                        if not client or not product:
                            continue
                        
                        # 获取客户信息
                        client_name, user_full_name = await PostbackNotifier._get_client_info(client, db)
                        product_name = PostbackNotifier._get_product_name(product)
                        
                        # 构建汇总消息
                        total_count = len(notif_list)
                        total_payout = sum(
                            float(n.get('payout', 0) or 0) for n in notif_list
                        )
                        total_original_payout = sum(
                            float(n.get('original_payout', 0) or 0) for n in notif_list
                        )
                        
                        # 获取第一个和最后一个通知的时间
                        first_time = None
                        last_time = None
                        for notif in notif_list:
                            if notif.get('created_at'):
                                try:
                                    time_obj = datetime.fromisoformat(notif['created_at'].replace('Z', '+00:00'))
                                    if not first_time or time_obj < first_time:
                                        first_time = time_obj
                                    if not last_time or time_obj > last_time:
                                        last_time = time_obj
                                except Exception:
                                    pass
                        
                        # 构建汇总消息
                        msg = "📊 Postback 转化汇总通知（每小时）\n\n"
                        msg += f"产品: {product_name}\n"
                        msg += f"时间范围: {first_time.strftime('%Y-%m-%d %H:%M') if first_time else '未知'} - {last_time.strftime('%Y-%m-%d %H:%M') if last_time else '未知'}\n\n"
                        msg += "💰 汇总信息\n"
                        msg += f"• 转化总数: {total_count}\n"
                        if total_original_payout > 0:
                            msg += f"• 原始总收益: ${total_original_payout:.2f}\n"
                        if total_payout > 0:
                            msg += f"• 扣后总收益: ${total_payout:.2f}\n"
                        
                        msg += "\n---\n"
                        msg += f"客户: {client_name}"
                        if user_full_name:
                            msg += f" ({user_full_name})"
                        
                        # 检查消息长度，如果超过限制则截断（Telegram 最大 4096 字符）
                        from app.core.telegram_utils import truncate_message
                        msg = truncate_message(msg)
                        
                        # 获取 Telegram Chat ID
                        telegram_chat_id = notif_list[0].get('telegram_chat_id')
                        if not telegram_chat_id:
                            continue
                        
                        # 发送汇总通知
                        success = await TelegramNotificationService.send_client_notification(
                            message=msg,
                            telegram_chat_id=telegram_chat_id,
                            conversion=None,  # 汇总通知不关联具体转化
                            client_id=client_id,
                            product_id=product_id,
                            notification_type='summary_hourly',
                            db=db
                        )
                        
                        if success:
                            result['sent_notifications'] += 1
                            logger.info(
                                f"每小时汇总通知已发送: client_id={client_id}, "
                                f"product_id={product_id}, count={total_count}"
                            )
                        else:
                            result['errors'].append(
                                f"发送汇总通知失败: client_id={client_id}, product_id={product_id}"
                            )
                    
                    except Exception as e:
                        error_msg = f"处理产品汇总通知失败: client_id={client_id}, product_id={product_id}, error={str(e)}"
                        logger.error(error_msg, exc_info=True)
                        result['errors'].append(error_msg)
                
                result['processed_clients'] += 1
            
            except Exception as e:
                error_msg = f"处理客户队列失败: queue_key={queue_key}, error={str(e)}"
                logger.error(error_msg, exc_info=True)
                result['errors'].append(error_msg)
        
        return result
    
    except Exception as e:
        error_msg = f"处理每小时汇总通知失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        result['success'] = False
        result['errors'].append(error_msg)
        return result


async def process_daily_notifications(db: AsyncSession) -> Dict[str, Any]:
    """
    处理每天汇总通知
    
    Args:
        db: 数据库会话
        
    Returns:
        处理结果字典
    """
    result = {
        'success': True,
        'processed_clients': 0,
        'sent_notifications': 0,
        'errors': []
    }
    
    try:
        redis_client = await get_redis_client()
        if not redis_client:
            result['success'] = False
            result['errors'].append('Redis 不可用')
            return result
        
        # 获取所有 daily 队列的键
        pattern = "notification_queue:daily:*"
        keys = []
        async for key in redis_client.scan_iter(match=pattern):
            keys.append(key.decode() if isinstance(key, bytes) else key)
        
        if not keys:
            logger.debug("没有待处理的每天汇总通知")
            return result
        
        # 处理每个客户的队列
        for queue_key in keys:
            try:
                # 提取客户ID
                client_id_str = queue_key.split(':')[-1]
                if client_id_str == 'unknown':
                    continue
                
                client_id = int(client_id_str)
                
                # 从队列中取出所有通知项
                notifications = []
                while True:
                    item_json = await redis_client.rpop(queue_key)
                    if not item_json:
                        break
                    
                    try:
                        item = json.loads(item_json.decode() if isinstance(item_json, bytes) else item_json)
                        notifications.append(item)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"解析通知项失败: {item_json[:100]}, error={e}")
                        continue
                
                if not notifications:
                    continue
                
                # 按产品分组
                grouped_by_product = defaultdict(list)
                for notif in notifications:
                    product_id = notif.get('product_id')
                    grouped_by_product[product_id].append(notif)
                
                # 为每个产品发送汇总通知
                for product_id, notif_list in grouped_by_product.items():
                    try:
                        # 获取客户和产品信息
                        client = None
                        product = None
                        
                        if client_id:
                            client_result = await db.execute(
                                select(Client).where(Client.id == client_id)
                            )
                            client = client_result.scalars().first()
                        
                        if product_id:
                            product_result = await db.execute(
                                select(Product).where(Product.id == product_id)
                            )
                            product = product_result.scalars().first()
                        
                        if not client or not product:
                            continue
                        
                        # 获取客户信息
                        client_name, user_full_name = await PostbackNotifier._get_client_info(client, db)
                        product_name = PostbackNotifier._get_product_name(product)
                        
                        # 构建汇总消息
                        total_count = len(notif_list)
                        total_payout = sum(
                            float(n.get('payout', 0) or 0) for n in notif_list
                        )
                        total_original_payout = sum(
                            float(n.get('original_payout', 0) or 0) for n in notif_list
                        )
                        
                        # 获取第一个和最后一个通知的时间
                        first_time = None
                        last_time = None
                        for notif in notif_list:
                            if notif.get('created_at'):
                                try:
                                    time_obj = datetime.fromisoformat(notif['created_at'].replace('Z', '+00:00'))
                                    if not first_time or time_obj < first_time:
                                        first_time = time_obj
                                    if not last_time or time_obj > last_time:
                                        last_time = time_obj
                                except Exception:
                                    pass
                        
                        # 构建汇总消息
                        msg = "📊 Postback 转化汇总通知（每天）\n\n"
                        msg += f"产品: {product_name}\n"
                        msg += f"日期: {first_time.strftime('%Y-%m-%d') if first_time else '未知'}\n\n"
                        msg += "💰 汇总信息\n"
                        msg += f"• 转化总数: {total_count}\n"
                        if total_original_payout > 0:
                            msg += f"• 原始总收益: ${total_original_payout:.2f}\n"
                        if total_payout > 0:
                            msg += f"• 扣后总收益: ${total_payout:.2f}\n"
                        
                        msg += "\n---\n"
                        msg += f"客户: {client_name}"
                        if user_full_name:
                            msg += f" ({user_full_name})"
                        
                        # 检查消息长度，如果超过限制则截断（Telegram 最大 4096 字符）
                        from app.core.telegram_utils import truncate_message
                        msg = truncate_message(msg)
                        
                        # 获取 Telegram Chat ID
                        telegram_chat_id = notif_list[0].get('telegram_chat_id')
                        if not telegram_chat_id:
                            continue
                        
                        # 发送汇总通知
                        success = await TelegramNotificationService.send_client_notification(
                            message=msg,
                            telegram_chat_id=telegram_chat_id,
                            conversion=None,  # 汇总通知不关联具体转化
                            client_id=client_id,
                            product_id=product_id,
                            notification_type='summary_daily',
                            db=db
                        )
                        
                        if success:
                            result['sent_notifications'] += 1
                            logger.info(
                                f"每天汇总通知已发送: client_id={client_id}, "
                                f"product_id={product_id}, count={total_count}"
                            )
                        else:
                            result['errors'].append(
                                f"发送汇总通知失败: client_id={client_id}, product_id={product_id}"
                            )
                    
                    except Exception as e:
                        error_msg = f"处理产品汇总通知失败: client_id={client_id}, product_id={product_id}, error={str(e)}"
                        logger.error(error_msg, exc_info=True)
                        result['errors'].append(error_msg)
                
                result['processed_clients'] += 1
            
            except Exception as e:
                error_msg = f"处理客户队列失败: queue_key={queue_key}, error={str(e)}"
                logger.error(error_msg, exc_info=True)
                result['errors'].append(error_msg)
        
        return result
    
    except Exception as e:
        error_msg = f"处理每天汇总通知失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        result['success'] = False
        result['errors'].append(error_msg)
        return result


async def process_hourly_notification_task() -> None:
    """
    每小时汇总通知任务（定时任务入口）
    """
    task_name = "通知汇总任务（每小时）"
    logger.info(f"{task_name} 开始执行")
    
    try:
        async with AsyncSessionLocal() as db:
            result = await process_hourly_notifications(db)
            
            # 构建结果消息
            if result['success']:
                result_msg = (
                    f"成功处理 {result['processed_clients']} 个客户，"
                    f"发送 {result['sent_notifications']} 条汇总通知"
                )
                if result['errors']:
                    result_msg += f"，错误数: {len(result['errors'])}"
            else:
                result_msg = f"处理失败: {', '.join(result['errors'][:3])}"
            
            set_task_result(task_name, result_msg)
            logger.info(f"{task_name} 执行完成: {result_msg}")
    
    except Exception as e:
        error_msg = f"执行失败: {str(e)}"
        set_task_result(task_name, error_msg)
        logger.error(f"{task_name} 执行异常: {error_msg}", exc_info=True)


async def process_daily_notification_task() -> None:
    """
    每天汇总通知任务（定时任务入口）
    """
    task_name = "通知汇总任务（每天）"
    logger.info(f"{task_name} 开始执行")
    
    try:
        async with AsyncSessionLocal() as db:
            result = await process_daily_notifications(db)
            
            # 构建结果消息
            if result['success']:
                result_msg = (
                    f"成功处理 {result['processed_clients']} 个客户，"
                    f"发送 {result['sent_notifications']} 条汇总通知"
                )
                if result['errors']:
                    result_msg += f"，错误数: {len(result['errors'])}"
            else:
                result_msg = f"处理失败: {', '.join(result['errors'][:3])}"
            
            set_task_result(task_name, result_msg)
            logger.info(f"{task_name} 执行完成: {result_msg}")
    
    except Exception as e:
        error_msg = f"执行失败: {str(e)}"
        set_task_result(task_name, error_msg)
        logger.error(f"{task_name} 执行异常: {error_msg}", exc_info=True)
