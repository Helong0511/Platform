"""
Postback 通知服务
负责按客户和产品发送转化通知
支持通知配置、高价值转化通知、通知频率控制等功能
"""
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import (
    PostbackConversion, Client, Product, User,
    ClientNotificationConfig, ProductNotificationConfig, PostbackNotification
)
from app.core.auto_bot import send_telegram_message
from app.core.utils import get_app_now_naive
from app.core.redis_client import get_redis_client
from app.services.telegram_notification_service import TelegramNotificationService
import httpx

logger = logging.getLogger(__name__)

# Redis 通知队列配置
NOTIFICATION_QUEUE_MAX_SIZE = 10000  # 每个客户队列最大长度（防止内存溢出）


class PostbackNotifier:
    """Postback 通知器"""
    
    @staticmethod
    async def notify_conversion(
        conversion: PostbackConversion,
        db: AsyncSession,
        product: Optional[Product] = None,
        client: Optional[Client] = None
    ) -> None:
        """
        通知转化事件（根据配置决定是否发送）
        
        优先级：
        1. 客户通知配置（ClientNotificationConfig）- 优先使用
        2. 产品通知配置（ProductNotificationConfig）
        3. 产品表中的通知地址（Product.notification_address）- 向后兼容
        
        Args:
            conversion: 转化记录
            db: 数据库会话
            product: 产品对象（如果提供）
            client: 客户对象（如果提供）
        """
        try:
            # 1. 获取客户和产品信息
            if not product and conversion.product_id:
                result = await db.execute(
                    select(Product).where(Product.id == conversion.product_id)
                )
                product = result.scalars().first()
            
            if not client:
                if product and product.client_id:
                    result = await db.execute(
                        select(Client).where(Client.id == product.client_id)
                    )
                    client = result.scalars().first()
                elif conversion.client_id:
                    result = await db.execute(
                        select(Client).where(Client.id == conversion.client_id)
                    )
                    client = result.scalars().first()
            
            if not client:
                logger.debug(
                    f"无法获取客户信息，跳过通知: conversion_id={conversion.id}, "
                    f"product_id={conversion.product_id}, client_id={conversion.client_id}"
                )
                return
            
            # 2. 获取客户和产品通知配置
            client_config = None
            product_config = None
            
            if client:
                result = await db.execute(
                    select(ClientNotificationConfig).where(
                        ClientNotificationConfig.client_id == client.id
                    )
                )
                client_config = result.scalars().first()
            
            if product:
                result = await db.execute(
                    select(ProductNotificationConfig).where(
                        ProductNotificationConfig.product_id == product.id
                    )
                )
                product_config = result.scalars().first()
            
            # 3. 检查是否需要发送通知
            should_notify, notification_type = PostbackNotifier._should_notify(
                conversion=conversion,
                product_config=product_config,
                client_config=client_config
            )
            
            if not should_notify:
                logger.debug(
                    f"根据配置不需要发送通知: conversion_id={conversion.id}, "
                    f"notification_type={notification_type}"
                )
                return
            
            # 4. 获取通知渠道和地址
            # 优先使用客户配置，如果没有则使用产品配置，最后使用产品表中的通知地址
            config = client_config if client_config else product_config
            channels = PostbackNotifier._get_notification_channels(config)
            
            # 获取 Telegram Chat ID（优先使用配置中的）
            telegram_chat_id = None
            if config:
                if config.telegram_chat_id:
                    telegram_chat_id = config.telegram_chat_id.strip()
            elif product and product.notification_address:
                # 向后兼容：如果产品表中的通知地址是纯数字，作为 Telegram Chat ID
                notification_address = product.notification_address.strip()
                if notification_address and notification_address.replace('-', '').isdigit():
                    telegram_chat_id = notification_address
            
            # 如果没有 Telegram Chat ID，且没有其他渠道，跳过通知
            if 'telegram' in channels and not telegram_chat_id:
                logger.debug(
                    f"未配置 Telegram Chat ID，跳过通知: conversion_id={conversion.id}, "
                    f"client_id={client.id if client else None}"
                )
                return
            
            # 5. 获取客户和产品信息（用于通知）
            client_name, user_full_name = await PostbackNotifier._get_client_info(client, db)
            product_name = PostbackNotifier._get_product_name(product)
            
            # 6. 构建通知消息（使用 TelegramNotificationService）
            
            if notification_type == 'high_value' and config and config.high_value_threshold:
                message = TelegramNotificationService.build_client_high_value_message(
                    conversion=conversion,
                    client_name=client_name,
                    product_name=product_name,
                    threshold=config.high_value_threshold,
                    user_full_name=user_full_name
                )
            else:
                message = TelegramNotificationService.build_client_conversion_message(
                    conversion=conversion,
                    client_name=client_name,
                    product_name=product_name,
                    user_full_name=user_full_name
                )
            
            # 7. 根据通知频率决定发送方式
            notification_frequency = config.notification_frequency if config else 'realtime'
            
            if notification_frequency == 'realtime':
                # 实时通知：立即发送
                if 'telegram' in channels and telegram_chat_id:
                    asyncio.create_task(
                        TelegramNotificationService.send_client_notification(
                            message=message,
                            telegram_chat_id=telegram_chat_id,
                            conversion=conversion,
                            db=db
                        )
                    )
            else:
                # 汇总通知（hourly/daily）：将通知放入队列，由定时任务汇总发送
                # 使用 Redis 队列存储待汇总的通知
                try:
                    redis_client = await get_redis_client()
                    if redis_client:
                        # 构建通知队列项
                        notification_item = {
                            'conversion_id': conversion.id,
                            'client_id': client.id if client else None,
                            'product_id': product.id if product else None,
                            'telegram_chat_id': telegram_chat_id,
                            'message': message,
                            'notification_type': notification_type,
                            'frequency': notification_frequency,
                            'created_at': conversion.created_at.isoformat() if conversion.created_at else None,
                            'payout': float(conversion.payout) if conversion.payout else None,
                            'original_payout': float(conversion.original_payout) if conversion.original_payout else None
                        }
                        
                        # 根据频率选择不同的队列
                        if notification_frequency == 'hourly':
                            queue_key = f"notification_queue:hourly:{client.id if client else 'unknown'}"
                        elif notification_frequency == 'daily':
                            queue_key = f"notification_queue:daily:{client.id if client else 'unknown'}"
                        else:
                            # 意外的频率值，记录警告并降级为实时发送
                            logger.warning(
                                f"未知的通知频率: {notification_frequency}，降级为实时发送: "
                                f"conversion_id={conversion.id}, client_id={client.id if client else None}"
                            )
                            if 'telegram' in channels and telegram_chat_id:
                                asyncio.create_task(
                                    TelegramNotificationService.send_client_notification(
                                        message=message,
                                        telegram_chat_id=telegram_chat_id,
                                        conversion=conversion,
                                        db=db
                                    )
                                )
                            return  # 已降级为实时发送，直接返回
                        
                        # 检查队列长度，防止内存溢出
                        queue_length = await redis_client.llen(queue_key)
                        if queue_length >= NOTIFICATION_QUEUE_MAX_SIZE:
                            logger.warning(
                                f"通知队列已满（{queue_length}/{NOTIFICATION_QUEUE_MAX_SIZE}），"
                                f"通知可能丢失: conversion_id={conversion.id}, queue_key={queue_key}"
                            )
                            # 队列已满时，降级为实时发送
                            if 'telegram' in channels and telegram_chat_id:
                                asyncio.create_task(
                                    TelegramNotificationService.send_client_notification(
                                        message=message,
                                        telegram_chat_id=telegram_chat_id,
                                        conversion=conversion,
                                        db=db
                                    )
                                )
                            return  # 队列已满，已降级为实时发送，直接返回
                        
                        # 将通知项添加到 Redis 列表
                        await redis_client.lpush(
                            queue_key,
                            json.dumps(notification_item, ensure_ascii=False)
                        )
                        
                        # 设置过期时间（hourly: 2小时，daily: 2天）
                        # 注意：每次添加新项时都更新过期时间，确保队列不会过早过期
                        if notification_frequency == 'hourly':
                            await redis_client.expire(queue_key, 7200)  # 2小时（足够覆盖1小时汇总周期）
                        elif notification_frequency == 'daily':
                            await redis_client.expire(queue_key, 172800)  # 2天（足够覆盖1天汇总周期）
                        
                        logger.debug(
                            f"通知已加入汇总队列: conversion_id={conversion.id}, "
                            f"frequency={notification_frequency}, queue_key={queue_key}"
                        )
                    else:
                        # Redis 不可用时，降级为实时发送
                        logger.warning(
                            f"Redis 不可用，降级为实时发送通知: conversion_id={conversion.id}"
                        )
                        if 'telegram' in channels and telegram_chat_id:
                            asyncio.create_task(
                                TelegramNotificationService.send_client_notification(
                                    message=message,
                                    telegram_chat_id=telegram_chat_id,
                                    conversion=conversion,
                                    db=db
                                )
                            )
                except Exception as e:
                    # Redis 操作失败时，降级为实时发送
                    logger.warning(
                        f"将通知加入汇总队列失败，降级为实时发送: conversion_id={conversion.id}, "
                        f"error={str(e)}"
                    )
                    if 'telegram' in channels and telegram_chat_id:
                        asyncio.create_task(
                            TelegramNotificationService.send_client_notification(
                                message=message,
                                telegram_chat_id=telegram_chat_id,
                                conversion=conversion,
                                db=db
                            )
                        )
            
            # TODO: 支持其他渠道（email, sms, webhook）
            # 这里可以添加其他渠道的通知发送逻辑
            
        except Exception as e:
            # 通知失败不影响主流程，只记录日志
            logger.warning(
                f"发送转化通知失败: conversion_id={conversion.id}, "
                f"product_id={conversion.product_id}, client_id={conversion.client_id}, "
                f"error={str(e)}",
                exc_info=True
            )
    
    @staticmethod
    def _should_notify(
        conversion: PostbackConversion,
        product_config: Optional[ProductNotificationConfig],
        client_config: Optional[ClientNotificationConfig]
    ) -> tuple[bool, str]:
        """
        判断是否需要发送通知
        
        Args:
            conversion: 转化记录
            product_config: 产品通知配置
            client_config: 客户通知配置
            
        Returns:
            (是否需要通知, 通知类型)
        """
        # 优先使用客户配置，如果没有则使用产品配置（与 notify_conversion 中的优先级保持一致）
        config = client_config if client_config else product_config
        
        # 如果没有配置，默认发送通知（向后兼容）
        if not config:
            return True, 'conversion'
        
        # 检查是否启用通知
        if not config.notification_enabled:
            return False, 'conversion'
        
        # 检查是否通知转化事件
        if not config.notify_on_conversion:
            # 如果配置了高价值通知，检查是否满足条件
            if config.notify_on_high_value and conversion.payout:
                threshold = config.high_value_threshold or 0
                if conversion.payout >= threshold:
                    return True, 'high_value'
            return False, 'conversion'
        
        # 检查高价值转化通知
        if config.notify_on_high_value and conversion.payout:
            threshold = config.high_value_threshold or 0
            if conversion.payout >= threshold:
                return True, 'high_value'
        
        # 普通转化通知
        return True, 'conversion'
    
    @staticmethod
    def _get_notification_channels(
        config: Optional[Any]
    ) -> List[str]:
        """
        获取通知渠道列表
        
        Args:
            config: 通知配置对象
            
        Returns:
            通知渠道列表
        """
        if not config or not config.notify_channels:
            # 默认使用 Telegram（向后兼容）
            return ['telegram']
        
        try:
            channels = json.loads(config.notify_channels)
            if isinstance(channels, list):
                return channels
            return ['telegram']
        except (json.JSONDecodeError, TypeError):
            return ['telegram']
    
    @staticmethod
    async def _get_client_info(
        client: Optional[Client],
        db: AsyncSession
    ) -> tuple[str, Optional[str]]:
        """
        获取客户信息
        
        Args:
            client: 客户对象
            db: 数据库会话
            
        Returns:
            (客户名称, 用户全名)
        """
        if not client:
            return "未知客户", None
        
        client_name = client.company_name or f"客户_{client.id}"
        user_full_name = None
        
        if client.user_id:
            result = await db.execute(
                select(User).where(User.id == client.user_id)
            )
            user = result.scalars().first()
            if user:
                user_full_name = user.full_name or user.username
        
        return client_name, user_full_name
    
    @staticmethod
    def _get_product_name(product: Optional[Product]) -> str:
        """获取产品名称"""
        if not product:
            return "未知产品"
        return product.name or f"产品_{product.id}"
    
    @staticmethod
    def _build_notification_message(
        conversion: PostbackConversion,
        client_name: str,
        product_name: str,
        user_full_name: Optional[str] = None,
        notification_type: str = 'conversion'
    ) -> str:
        """
        构建通知消息（符合文档模板格式）
        
        Args:
            conversion: 转化记录
            client_name: 客户名称
            product_name: 产品名称
            user_full_name: 用户全名（可选）
            notification_type: 通知类型
            
        Returns:
            通知消息文本
        """
        # 根据通知类型选择不同的标题
        if notification_type == 'high_value':
            msg = "💰 高价值转化通知\n\n"
        else:
            msg = "🔔 Postback 转化通知\n\n"
        
        # 客户信息（符合文档模板）
        if user_full_name:
            msg += f"客户：{user_full_name}\n"
        msg += f"产品：{product_name}\n"
        msg += f"平台：{conversion.platform.upper()}\n"
        msg += f"转化ID：{conversion.conversion_id}\n"
        
        if conversion.event_name:
            msg += f"事件：{conversion.event_name}\n"
        
        if conversion.event_value is not None:
            msg += f"价值：${conversion.event_value:.2f}\n"
        
        if conversion.original_payout is not None:
            msg += f"原始收益（PO）：${conversion.original_payout:.2f}\n"
        if conversion.payout is not None:
            msg += f"扣后收益（PO(扣)）：${conversion.payout:.2f}\n"
        
        # 时间信息
        if conversion.created_at:
            time_str = conversion.created_at.strftime("%Y-%m-%d %H:%M:%S")
            msg += f"时间：{time_str}\n"
        
        return msg
    
    @staticmethod
    async def _send_notification_async(
        message: str,
        conversion: PostbackConversion,
        client: Optional[Client],
        product: Optional[Product],
        notification_address: str,
        db: AsyncSession,
        raise_on_failure: bool = False
    ) -> bool:
        """
        异步发送通知（使用产品表中的通知地址）
        
        Args:
            message: 通知消息
            conversion: 转化记录
            client: 客户对象
            product: 产品对象
            notification_address: 通知地址（Telegram Chat ID、邮箱、Webhook URL等）
            db: 数据库会话
            raise_on_failure: 如果为True，通知发送失败时抛出异常（用于补发通知场景）
        
        Returns:
            bool: 通知是否发送成功
        """
        try:
            # 判断通知地址类型并发送
            # 1. 如果是纯数字，可能是 Telegram Chat ID
            # 2. 如果包含 @，可能是邮箱地址
            # 3. 如果以 http:// 或 https:// 开头，可能是 Webhook URL
            # 4. 默认作为 Telegram Chat ID 处理
            
            notification_channel = PostbackNotifier._detect_notification_channel(notification_address)
            
            # 发送通知并捕获可能的错误信息
            success = False
            error_msg = None
            try:
                success = await PostbackNotifier._send_to_address(
                    address=notification_address,
                    channel=notification_channel,
                    message=message
                )
                if not success:
                    # 根据渠道类型推断失败原因
                    if notification_channel == 'email':
                        error_msg = "邮件通知功能尚未实现"
                    elif notification_channel == 'sms':
                        error_msg = "短信通知功能尚未实现"
                    elif notification_channel == 'webhook':
                        error_msg = f"Webhook 通知失败: url={notification_address[:50]}"
                    else:
                        error_msg = f"通知发送失败: channel={notification_channel}, address={notification_address[:50]}"
            except Exception as send_error:
                # 发送过程中出现异常
                error_msg = f"通知发送异常: {str(send_error)[:200]}"
                success = False
            
            # 记录通知历史
            notification_record = PostbackNotification(
                conversion_id=conversion.id,
                client_id=client.id if client else None,
                product_id=product.id if product else None,
                notification_type='conversion',
                notification_channel=notification_channel,
                notification_status='sent' if success else 'failed',
                notification_message=message,
                error_message=error_msg,
                auto_notify=True,  # 转化通知是自动通知
                created_at=get_app_now_naive()
            )
            
            db.add(notification_record)
            await db.flush()
            
            if success:
                logger.info(
                    f"转化通知发送成功: conversion_id={conversion.id}, "
                    f"product_id={product.id if product else None}, "
                    f"client_id={client.id if client else None}, "
                    f"address={notification_address[:50]}, channel={notification_channel}"
                )
                return True
            else:
                # 通知发送失败，记录详细错误日志
                logger.error(
                    f"转化通知发送失败: conversion_id={conversion.id}, "
                    f"product_id={product.id if product else None}, "
                    f"client_id={client.id if client else None}, "
                    f"address={notification_address[:50]}, channel={notification_channel}, "
                    f"status=failed"
                )
                if raise_on_failure:
                    raise Exception(f"通知发送失败: channel={notification_channel}, address={notification_address[:50]}")
                return False
                
        except Exception as e:
            # 记录失败的通知
            try:
                notification_record = PostbackNotification(
                    conversion_id=conversion.id,
                    client_id=client.id if client else None,
                    product_id=product.id if product else None,
                    notification_type='conversion',
                    notification_channel=notification_channel if 'notification_channel' in locals() else 'unknown',
                    notification_status='failed',
                    notification_message=message,
                    error_message=str(e)[:500],
                    auto_notify=True,  # 转化通知是自动通知
                    created_at=get_app_now_naive()
                )
                db.add(notification_record)
                await db.commit()
            except Exception as commit_error:
                logger.error(f"保存通知记录失败: {commit_error}")
            
            # 通知发送异常，记录详细错误日志
            logger.error(
                f"发送转化通知异常: conversion_id={conversion.id}, "
                f"product_id={product.id if product else None}, "
                f"client_id={client.id if client else None}, "
                f"address={notification_address[:50]}, "
                f"channel={notification_channel if 'notification_channel' in locals() else 'unknown'}, "
                f"error={str(e)}",
                exc_info=True
            )
            if raise_on_failure:
                raise
            return False
    
    @staticmethod
    def _detect_notification_channel(address: str) -> str:
        """
        检测通知地址类型
        
        Args:
            address: 通知地址
            
        Returns:
            通知渠道类型：telegram, email, webhook
        """
        address = address.strip()
        
        # 如果以 http:// 或 https:// 开头，是 Webhook URL
        if address.startswith('http://') or address.startswith('https://'):
            return 'webhook'
        
        # 如果包含 @，可能是邮箱地址
        if '@' in address:
            return 'email'
        
        # 默认作为 Telegram Chat ID 处理
        return 'telegram'
    
    @staticmethod
    async def _send_to_address(
        address: str,
        channel: str,
        message: str
    ) -> bool:
        """
        发送通知到指定地址
        
        Args:
            address: 通知地址
            channel: 通知渠道类型
            message: 通知消息
            
        Returns:
            是否发送成功
        """
        try:
            if channel == 'telegram':
                # Telegram Chat ID
                await asyncio.wait_for(
                    send_telegram_message(message, chat_id=address),
                    timeout=5.0
                )
                logger.debug(
                    f"Telegram 通知已发送: chat_id={address}, "
                    f"message_length={len(message)}"
                )
                return True
            elif channel == 'email':
                # 邮箱地址
                # TODO: 实现邮件通知
                logger.error(
                    f"邮件通知功能尚未实现: address={address}, "
                    f"channel=email, status=not_implemented"
                )
                return False
            elif channel == 'webhook':
                # Webhook URL
                return await PostbackNotifier._send_webhook_notification(
                    url=address,
                    message=message
                )
            else:
                logger.error(
                    f"不支持的通知渠道: channel={channel}, address={address[:50]}, "
                    f"status=unsupported_channel"
                )
                return False
                
        except asyncio.TimeoutError:
            logger.error(
                f"发送通知超时: channel={channel}, address={address[:50]}, "
                f"timeout=5.0s"
            )
            return False
        except Exception as e:
            logger.error(
                f"发送通知异常: channel={channel}, address={address[:50]}, "
                f"error={str(e)}",
                exc_info=True
            )
            return False
    
    @staticmethod
    async def _send_webhook_notification(
        url: str,
        message: str
    ) -> bool:
        """
        发送 Webhook 通知
        
        Args:
            url: Webhook URL
            message: 通知消息
            
        Returns:
            是否发送成功
        """
        try:
            
            # 构建通知数据
            payload = {
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if 200 <= response.status_code < 300:
                    logger.debug(
                        f"Webhook 通知已发送: url={url[:50]}, "
                        f"status={response.status_code}"
                    )
                    return True
                else:
                    logger.error(
                        f"Webhook 通知返回非成功状态: url={url[:50]}, "
                        f"status={response.status_code}, response={response.text[:200]}"
                    )
                    return False
                    
        except httpx.TimeoutException:
            logger.error(
                f"Webhook 通知超时: url={url[:50]}, timeout=10.0s"
            )
            return False
        except Exception as e:
            logger.error(
                f"Webhook 通知异常: url={url[:50]}, error={str(e)}",
                exc_info=True
            )
            return False
    
    @staticmethod
    async def _send_to_channel(
        channel: str,
        message: str,
        recipient: Optional[str] = None
    ) -> bool:
        """
        发送通知到指定渠道（使用产品配置的通知地址）
        
        Args:
            channel: 通知渠道
            message: 通知消息
            recipient: 接收人信息（Chat ID、邮箱、手机号等）
            
        Returns:
            是否发送成功
        """
        try:
            if channel == 'telegram':
                # 使用产品配置的 Telegram Chat ID
                # 如果提供了 recipient（Chat ID），发送到指定 Chat
                # 如果没有提供，使用默认配置（向后兼容）
                chat_id = recipient if recipient else None
                await asyncio.wait_for(
                    send_telegram_message(message, chat_id=chat_id),
                    timeout=5.0
                )
                logger.debug(
                    f"Telegram 通知已发送: chat_id={chat_id or 'default'}, "
                    f"message_length={len(message)}"
                )
                return True
            elif channel == 'email':
                # 使用产品配置的邮箱地址
                if not recipient:
                    logger.warning("邮件通知需要配置邮箱地址（email_address）")
                    return False
                # TODO: 实现邮件通知
                logger.warning(f"邮件通知功能尚未实现: recipient={recipient}")
                return False
            elif channel == 'sms':
                # 使用产品配置的手机号
                if not recipient:
                    logger.warning("短信通知需要配置手机号（phone_number）")
                    return False
                # TODO: 实现短信通知
                logger.warning(f"短信通知功能尚未实现: recipient={recipient}")
                return False
            else:
                logger.warning(f"不支持的通知渠道: {channel}")
                return False
                
        except asyncio.TimeoutError:
            logger.warning(f"发送通知超时: channel={channel}, recipient={recipient}")
            return False
        except Exception as e:
            logger.warning(
                f"发送通知失败: channel={channel}, recipient={recipient}, error={str(e)}"
            )
            return False
    
    @staticmethod
    async def notify_batch_conversions(
        conversions: List[PostbackConversion],
        db: AsyncSession
    ) -> None:
        """
        批量通知转化事件（用于定时汇总通知）
        
        Args:
            conversions: 转化记录列表
            db: 数据库会话
        """
        if not conversions:
            return
        
        try:
            # 按客户和产品分组
            grouped = {}
            
            for conversion in conversions:
                key = (conversion.client_id, conversion.product_id)
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(conversion)
            
            # 为每个客户-产品组合发送汇总通知
            for (client_id, product_id), conv_list in grouped.items():
                # 获取客户和产品信息
                client = None
                product = None
                
                if client_id:
                    result = await db.execute(
                        select(Client).where(Client.id == client_id)
                    )
                    client = result.scalars().first()
                
                if product_id:
                    result = await db.execute(
                        select(Product).where(Product.id == product_id)
                    )
                    product = result.scalars().first()
                
                # 检查产品是否配置了通知地址
                if not product or not product.notification_address:
                    continue
                
                notification_address = product.notification_address.strip()
                if not notification_address:
                    continue
                
                # 获取客户和产品信息
                client_name, user_full_name = await PostbackNotifier._get_client_info(client, db)
                product_name = PostbackNotifier._get_product_name(product)
                
                # 构建汇总消息
                message = PostbackNotifier._build_batch_notification_message(
                    conversions=conv_list,
                    client_name=client_name,
                    product_name=product_name,
                    user_full_name=user_full_name
                )
                
                # 发送通知（使用产品表中的通知地址）
                asyncio.create_task(
                    PostbackNotifier._send_notification_async(
                        message=message,
                        conversion=conv_list[0],  # 使用第一个作为代表
                        client=client,
                        product=product,
                        notification_address=notification_address,
                        db=db
                    )
                )
                
        except Exception as e:
            logger.warning(
                f"批量通知转化失败: count={len(conversions)}, error={str(e)}",
                exc_info=True
            )
    
    @staticmethod
    def _build_batch_notification_message(
        conversions: List[PostbackConversion],
        client_name: str,
        product_name: str,
        user_full_name: Optional[str] = None
    ) -> str:
        """
        构建批量通知消息
        
        Args:
            conversions: 转化记录列表
            client_name: 客户名称
            product_name: 产品名称
            user_full_name: 用户全名（可选）
            
        Returns:
            通知消息文本
        """
        # 基础信息
        msg = "📊 Postback 转化汇总通知\n\n"
        
        # 客户和产品信息
        if user_full_name:
            msg += f"客户：{user_full_name}\n"
        msg += f"产品：{product_name}\n\n"
        
        # 统计信息
        total_count = len(conversions)
        total_original_payout = sum(c.original_payout or 0 for c in conversions)
        total_payout = sum(c.payout or 0 for c in conversions)
        total_value = sum(c.event_value or 0 for c in conversions)
        
        msg += f"转化数量：{total_count} 条\n"
        msg += f"总价值：${total_value:.2f}\n"
        if total_original_payout > 0:
            msg += f"原始总收益（PO）：${total_original_payout:.2f}\n"
        msg += f"扣后总收益（PO(扣)）：${total_payout:.2f}\n\n"
        
        # 按平台统计
        platform_stats = {}
        for conv in conversions:
            platform = conv.platform
            if platform not in platform_stats:
                platform_stats[platform] = {
                    'count': 0,
                    'original_payout': 0,
                    'payout': 0,
                    'value': 0
                }
            platform_stats[platform]['count'] += 1
            platform_stats[platform]['original_payout'] += conv.original_payout or 0
            platform_stats[platform]['payout'] += conv.payout or 0
            platform_stats[platform]['value'] += conv.event_value or 0
        
        if platform_stats:
            msg += "平台统计：\n"
            for platform, stats in platform_stats.items():
                msg += f"  • {platform.upper()}: {stats['count']} 条"
                if stats['original_payout'] > 0:
                    msg += f", PO: ${stats['original_payout']:.2f}"
                msg += f", PO(扣): ${stats['payout']:.2f}\n"
        
        # 时间范围
        if conversions:
            first_time = conversions[0].created_at
            last_time = conversions[-1].created_at
            if first_time and last_time:
                msg += f"\n时间范围：{first_time.strftime('%Y-%m-%d %H:%M')} "
                msg += f"至 {last_time.strftime('%Y-%m-%d %H:%M')}\n"
        
        return msg
