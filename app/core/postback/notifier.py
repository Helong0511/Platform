"""
Postback 通知服务
负责按客户和产品发送转化通知
支持通知配置、高价值转化通知、通知频率控制等功能
"""
import asyncio
import json
import logging
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import (
    PostbackConversion, Client, Product,
    ClientNotificationConfig, ProductNotificationConfig,
)
from app.core.redis_client import get_redis_client
from app.core.database import AsyncSessionLocal
from app.services.telegram_notification_service import TelegramNotificationService
from app.core.postback.notification.config_helpers import (
    should_notify,
    get_notification_channels,
    get_client_info,
    get_product_name,
    detect_notification_channel,
)
from app.core.postback.notification.message_builder import (
    build_notification_message,
    build_batch_notification_message,
)
from app.core.postback.notification.sender import (
    send_notification_async,
    send_to_address,
    send_webhook_notification,
    send_to_channel,
)

logger = logging.getLogger(__name__)

NOTIFICATION_QUEUE_MAX_SIZE = 10000


class PostbackNotifier:
    """Postback 通知器（向后兼容门面）"""

    _should_notify = staticmethod(should_notify)
    _get_notification_channels = staticmethod(get_notification_channels)
    _get_client_info = staticmethod(get_client_info)
    _get_product_name = staticmethod(get_product_name)
    _detect_notification_channel = staticmethod(detect_notification_channel)
    _build_notification_message = staticmethod(build_notification_message)
    _build_batch_notification_message = staticmethod(build_batch_notification_message)
    _send_notification_async = staticmethod(send_notification_async)
    _send_to_address = staticmethod(send_to_address)
    _send_webhook_notification = staticmethod(send_webhook_notification)
    _send_to_channel = staticmethod(send_to_channel)

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
            should_notify, notification_type = should_notify(
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
            channels = get_notification_channels(config)

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
            client_name, user_full_name = await get_client_info(client, db)
            product_name = get_product_name(product)

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
                # 实时通知：独立会话 + 按 ID 重载转化，避免请求 session 关闭后写库失败
                if 'telegram' in channels and telegram_chat_id:
                    conversion_id = conversion.id
                    notify_message = message
                    notify_chat_id = telegram_chat_id

                    async def _notify_with_fresh_session() -> None:
                        async with AsyncSessionLocal() as notify_db:
                            result = await notify_db.execute(
                                select(PostbackConversion).where(
                                    PostbackConversion.id == conversion_id
                                )
                            )
                            conv = result.scalar_one_or_none()
                            if not conv:
                                logger.warning(
                                    "实时通知跳过：转化不存在 conversion_id=%s",
                                    conversion_id,
                                )
                                return
                            await TelegramNotificationService.send_client_notification(
                                message=notify_message,
                                telegram_chat_id=notify_chat_id,
                                conversion=conv,
                                db=notify_db,
                            )

                    asyncio.create_task(_notify_with_fresh_session())
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
                client_name, user_full_name = await get_client_info(client, db)
                product_name = get_product_name(product)

                # 构建汇总消息
                message = build_batch_notification_message(
                    conversions=conv_list,
                    client_name=client_name,
                    product_name=product_name,
                    user_full_name=user_full_name
                )

                # 发送通知（使用产品表中的通知地址）
                asyncio.create_task(
                    send_notification_async(
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

