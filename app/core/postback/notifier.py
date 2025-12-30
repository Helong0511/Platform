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

logger = logging.getLogger(__name__)


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
            
            # 2. 检查产品是否配置了通知地址
            if not product or not product.notification_address:
                logger.debug(
                    f"产品未配置通知地址，跳过通知: conversion_id={conversion.id}, "
                    f"product_id={conversion.product_id}"
                )
                return
            
            # 3. 获取通知地址（优先使用产品表中的通知地址）
            notification_address = product.notification_address.strip()
            
            if not notification_address:
                logger.debug(
                    f"产品通知地址为空，跳过通知: conversion_id={conversion.id}, "
                    f"product_id={conversion.product_id}"
                )
                return
            
            # 4. 获取客户和产品信息（用于通知）
            client_name, user_full_name = await PostbackNotifier._get_client_info(client, db)
            product_name = PostbackNotifier._get_product_name(product)
            
            # 5. 构建通知消息
            message = PostbackNotifier._build_notification_message(
                conversion=conversion,
                client_name=client_name,
                product_name=product_name,
                user_full_name=user_full_name,
                notification_type='conversion'
            )
            
            # 6. 发送通知（异步，不阻塞主流程）
            # 使用产品表中的通知地址
            asyncio.create_task(
                PostbackNotifier._send_notification_async(
                    message=message,
                    conversion=conversion,
                    client=client,
                    product=product,
                    notification_address=notification_address,
                    db=db
                )
            )
            
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
        # 优先使用产品配置，如果没有则使用客户配置
        config = product_config if product_config else client_config
        
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
        
        if conversion.payout is not None:
            msg += f"收益：${conversion.payout:.2f}\n"
        
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
        db: AsyncSession
    ) -> None:
        """
        异步发送通知（使用产品表中的通知地址）
        
        Args:
            message: 通知消息
            conversion: 转化记录
            client: 客户对象
            product: 产品对象
            notification_address: 通知地址（Telegram Chat ID、邮箱、Webhook URL等）
            db: 数据库会话
        """
        try:
            # 判断通知地址类型并发送
            # 1. 如果是纯数字，可能是 Telegram Chat ID
            # 2. 如果包含 @，可能是邮箱地址
            # 3. 如果以 http:// 或 https:// 开头，可能是 Webhook URL
            # 4. 默认作为 Telegram Chat ID 处理
            
            notification_channel = PostbackNotifier._detect_notification_channel(notification_address)
            
            # 发送通知
            success = await PostbackNotifier._send_to_address(
                address=notification_address,
                channel=notification_channel,
                message=message
            )
            
            # 记录通知历史
            notification_record = PostbackNotification(
                conversion_id=conversion.id,
                client_id=client.id if client else None,
                product_id=product.id if product else None,
                notification_type='conversion',
                notification_channel=notification_channel,
                notification_status='sent' if success else 'failed',
                notification_message=message,
                created_at=get_app_now_naive()
            )
            
            db.add(notification_record)
            await db.commit()
            
            if success:
                logger.info(
                    f"转化通知发送成功: conversion_id={conversion.id}, "
                    f"product_id={product.id if product else None}, "
                    f"address={notification_address[:50]}, channel={notification_channel}"
                )
            else:
                logger.warning(
                    f"转化通知发送失败: conversion_id={conversion.id}, "
                    f"product_id={product.id if product else None}, "
                    f"address={notification_address[:50]}, channel={notification_channel}"
                )
                
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
                    created_at=get_app_now_naive()
                )
                db.add(notification_record)
                await db.commit()
            except Exception as commit_error:
                logger.error(f"保存通知记录失败: {commit_error}")
            
            logger.warning(
                f"发送转化通知失败: conversion_id={conversion.id}, "
                f"product_id={product.id if product else None}, "
                f"address={notification_address[:50]}, error={str(e)}",
                exc_info=True
            )
    
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
                logger.warning(f"邮件通知功能尚未实现: address={address}")
                return False
            elif channel == 'webhook':
                # Webhook URL
                return await PostbackNotifier._send_webhook_notification(
                    url=address,
                    message=message
                )
            else:
                logger.warning(f"不支持的通知渠道: {channel}, address={address}")
                return False
                
        except asyncio.TimeoutError:
            logger.warning(f"发送通知超时: channel={channel}, address={address[:50]}")
            return False
        except Exception as e:
            logger.warning(
                f"发送通知失败: channel={channel}, address={address[:50]}, error={str(e)}"
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
            import httpx
            
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
                    logger.warning(
                        f"Webhook 通知返回非成功状态: url={url[:50]}, "
                        f"status={response.status_code}, response={response.text[:200]}"
                    )
                    return False
                    
        except httpx.TimeoutException:
            logger.warning(f"Webhook 通知超时: url={url[:50]}")
            return False
        except Exception as e:
            logger.warning(f"Webhook 通知失败: url={url[:50]}, error={str(e)}")
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
        total_payout = sum(c.payout or 0 for c in conversions)
        total_value = sum(c.event_value or 0 for c in conversions)
        
        msg += f"转化数量：{total_count} 条\n"
        msg += f"总价值：${total_value:.2f}\n"
        msg += f"总收益：${total_payout:.2f}\n\n"
        
        # 按平台统计
        platform_stats = {}
        for conv in conversions:
            platform = conv.platform
            if platform not in platform_stats:
                platform_stats[platform] = {
                    'count': 0,
                    'payout': 0,
                    'value': 0
                }
            platform_stats[platform]['count'] += 1
            platform_stats[platform]['payout'] += conv.payout or 0
            platform_stats[platform]['value'] += conv.event_value or 0
        
        if platform_stats:
            msg += "平台统计：\n"
            for platform, stats in platform_stats.items():
                msg += f"  • {platform.upper()}: {stats['count']} 条, "
                msg += f"${stats['payout']:.2f}\n"
        
        # 时间范围
        if conversions:
            first_time = conversions[0].created_at
            last_time = conversions[-1].created_at
            if first_time and last_time:
                msg += f"\n时间范围：{first_time.strftime('%Y-%m-%d %H:%M')} "
                msg += f"至 {last_time.strftime('%Y-%m-%d %H:%M')}\n"
        
        return msg
