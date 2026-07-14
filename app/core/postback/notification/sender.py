"""Postback 通知发送"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telegram import send_telegram_notify_async
from app.core.utils import get_app_now_naive
from app.models.models import PostbackConversion, Client, Product, PostbackNotification
from app.core.postback.notification.config_helpers import detect_notification_channel

logger = logging.getLogger(__name__)


async def send_notification_async(
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

        notification_channel = detect_notification_channel(notification_address)

        # 发送通知并捕获可能的错误信息
        success = False
        error_msg = None
        try:
            success = await send_to_address(
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
            # 仅 flush，避免异常路径中 commit 污染外层 Postback 事务
            await db.flush()
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

async def send_to_address(
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
            ok = await send_telegram_notify_async(address, message)
            if ok:
                logger.debug(
                    f"Telegram 通知已发送: chat_id={address}, "
                    f"message_length={len(message)}"
                )
            return ok
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
            return await send_webhook_notification(
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

async def send_webhook_notification(
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

async def send_to_channel(
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
            if chat_id:
                ok = await send_telegram_notify_async(chat_id, message)
            else:
                # 如果没有提供 chat_id，使用默认管理员
                ok = await send_telegram_notify_async(message)
            if ok:
                logger.debug(
                    f"Telegram 通知已发送: chat_id={chat_id or 'default'}, "
                    f"message_length={len(message)}"
                )
            return ok
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
