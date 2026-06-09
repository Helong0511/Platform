"""
Telegram 通知服务。

职责：
- 构建客户/管理员/系统各类 Postback 通知消息（转化、高价值、转发成败、告警等）
- 调用 send_telegram_message_async 发送并写入 PostbackNotification 历史
- 支持汇总、批量转化、带按钮交互通知；超长消息自动分片

管理员 Chat ID 默认取自 TELEGRAM_ADMIN；发送失败返回 False 不抛异常。
"""
import json
import logging
import asyncio
from datetime import datetime, time
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy import and_, func, select

from app.models.models import (
    PostbackConversion, Client, Product, Publisher, Offer, User, PostbackNotification, Click
)
from app.core.telegram import (
    send_telegram_message_async,
    send_telegram_message_with_buttons,
)
from app.core.utils import get_app_now_naive
from app.core.config import settings
from app.core.telegram_utils import (
    format_telegram_message,
    build_conversion_message,
    build_summary_message,
    build_alert_message,
    split_long_message,
    validate_chat_id,
    MESSAGE_TYPES
)

logger = logging.getLogger(__name__)


class TelegramNotificationService:
    """
    Telegram 消息构建与发送服务。

    多数方法为 @staticmethod，db 可选注入用于写入通知历史；
    消息模板与格式化逻辑委托 app.core.telegram_utils。
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        """可选注入数据库会话，供发送方法记录 PostbackNotification。"""
        self.db = db

    @staticmethod
    def _resolve_admin_chat_id(telegram_chat_id: Optional[str] = None) -> Optional[str]:
        """解析管理员 Chat ID：入参优先，否则回退 TELEGRAM_ADMIN 环境变量。"""
        if telegram_chat_id and str(telegram_chat_id).strip():
            return str(telegram_chat_id).strip()
        admin = getattr(settings, "TELEGRAM_ADMIN", None)
        if admin and str(admin).strip():
            return str(admin).strip()
        return None

    @staticmethod
    def build_client_conversion_message(
            conversion: PostbackConversion,
            client_name: str,
            product_name: str,
            user_full_name: Optional[str] = None
    ) -> str:
        """
        构建客户转化通知消息
        
        Args:
            conversion: 转化记录
            client_name: 客户名称
            product_name: 产品名称
            user_full_name: 用户全名（可选）
        
        Returns:
            str: 通知消息
        """
        msg = "△ Postback 转化通知\n\n"
        msg += f"产品: {product_name}\n"
        msg += f"平台: {conversion.platform}\n"
        msg += f"转化ID: {conversion.conversion_id}\n"

        if conversion.event_name:
            msg += f"事件: {conversion.event_name}\n"

        msg += "\n💰 金额信息\n"
        if conversion.original_payout is not None:
            msg += f"• 原始收益 (PO): ${conversion.original_payout:.2f}\n"
        if conversion.payout is not None:
            msg += f"• 扣后收益 (PO(扣)): ${conversion.payout:.2f}\n"

        if conversion.created_at:
            time_str = conversion.created_at.strftime("%Y-%m-%d %H:%M:%S")
            msg += f"\n⏰ 时间: {time_str}\n"

        msg += "\n---\n"
        msg += f"客户: {client_name}"
        if user_full_name:
            msg += f" ({user_full_name})"

        return msg

    @staticmethod
    def build_client_high_value_message(
            conversion: PostbackConversion,
            client_name: str,
            product_name: str,
            threshold: float,
            user_full_name: Optional[str] = None
    ) -> str:
        """
        构建客户高价值转化通知消息
        
        Args:
            conversion: 转化记录
            client_name: 客户名称
            product_name: 产品名称
            threshold: 高价值阈值
            user_full_name: 用户全名（可选）
        
        Returns:
            str: 通知消息
        """
        msg = "⭐ 高价值转化通知\n\n"
        msg += f"产品: {product_name}\n"
        msg += f"平台: {conversion.platform}\n"
        msg += f"转化ID: {conversion.conversion_id}\n"

        if conversion.event_name:
            msg += f"事件: {conversion.event_name}\n"

        msg += "\n💰 金额信息\n"
        if conversion.original_payout is not None:
            msg += f"• 原始收益 (PO): ${conversion.original_payout:.2f}\n"
        if conversion.payout is not None:
            msg += f"• 扣后收益 (PO(扣)): ${conversion.payout:.2f}\n"
        msg += f"• 阈值: ${threshold:.2f} ✅\n"

        if conversion.created_at:
            time_str = conversion.created_at.strftime("%Y-%m-%d %H:%M:%S")
            msg += f"\n⏰ 时间: {time_str}\n"

        msg += "\n---\n"
        msg += f"客户: {client_name}"
        if user_full_name:
            msg += f" ({user_full_name})"

        return msg

    @staticmethod
    async def build_admin_conversion_message(
            conversion: PostbackConversion,
            client_name: Optional[str] = None,
            product_name: Optional[str] = None,
            publisher: Optional[Publisher] = None,
            offer: Optional[Offer] = None,
            db: Optional[AsyncSession] = None
    ) -> str:
        """
        构建管理员转化通知消息
        
        Args:
            conversion: 转化记录
            client_name: 客户名称（可选）
            product_name: 产品名称（可选）
            publisher: 渠道对象（可选）
            offer: Offer 对象（可选）
            db: 数据库会话（可选，用于查询当天总转化数）
        
        Returns:
            str: 通知消息
        """
        msg = "📊 Postback 转化通知（管理员）\n\n"
        msg += f"转化ID: {conversion.conversion_id}\n"
        msg += f"平台: {conversion.platform}\n"

        if conversion.event_name:
            msg += f"事件: {conversion.event_name}\n"

        msg += "\n💰 金额信息\n"
        if conversion.original_payout is not None:
            msg += f"• 原始金额 (PO): ${conversion.original_payout:.2f}\n"
        if conversion.payout is not None:
            msg += f"• 扣后金额 (PO(扣)): ${conversion.payout:.2f}\n"

        if client_name or product_name:
            msg += "\n👤 客户信息\n"
            if client_name:
                msg += f"• 客户: {client_name}\n"
            if product_name:
                msg += f"• 产品: {product_name}\n"

        if publisher:
            msg += "\n📤 渠道信息\n"
            msg += f"• 渠道ID: {publisher.id}\n"
            msg += f"• 渠道名称: {publisher.publisher_name}\n"

        if offer:
            if not publisher:  # 如果还没有显示渠道信息，先显示
                msg += "\n📤 渠道信息\n"
            msg += f"• Offer ID: {offer.id}\n"
            if offer.offer_name:
                msg += f"• Offer 名称: {offer.offer_name}\n"

        # ====== 当日转化统计（管理员消息附加信息） ======
        if db:
            try:
                today = conversion.created_at.date() if conversion.created_at else get_app_now_naive().date()

                # 构建当天的开始和结束时间
                start_of_day = datetime.combine(today, time.min)
                end_of_day = datetime.combine(today, time.max)

                # 查询当天的转化记录数
                result = await db.execute(
                    select(func.count(PostbackConversion.id)).where(
                        and_(
                            PostbackConversion.created_at >= start_of_day,
                            PostbackConversion.created_at <= end_of_day
                        )
                    )
                )
                daily_total = result.scalar() or 0

                msg += f"\n📊 统计信息\n"
                msg += f"• 当天总转化个数: {daily_total}\n"

                # 查询当天当前渠道的转化记录数
                if publisher:
                    # 构建查询条件：当天 + 关联到该渠道的转化
                    # 注意：这里通过 click_id 关联到 Click，再通过 Click.publisher_id 关联到渠道
                    click_alias = aliased(Click)

                    # 查询当天该渠道的转化数
                    channel_result = await db.execute(
                        select(func.count(PostbackConversion.id)).join(
                            click_alias, PostbackConversion.click_id == click_alias.click_id
                        ).where(
                            and_(
                                PostbackConversion.created_at >= start_of_day,
                                PostbackConversion.created_at <= end_of_day,
                                click_alias.publisher_id == publisher.id
                            )
                        )
                    )
                    daily_channel_total = channel_result.scalar() or 0

                    msg += f"• 当天当前渠道转化个数: {daily_channel_total}\n"

            except Exception as e:
                logger.warning(f"获取当天转化数失败: {str(e)}")

        if conversion.created_at:
            time_str = conversion.created_at.strftime("%Y-%m-%d %H:%M:%S")
            msg += f"\n⏰ 时间: {time_str}\n"

        return msg

    @staticmethod
    def build_admin_forward_failure_message(
            conversion: PostbackConversion,
            publisher: Publisher,
            error_message: str,
            click_params: Optional[Dict[str, Any]] = None,
            offer: Optional[Offer] = None
    ) -> str:
        """
        构建管理员转发失败告警消息
        
        Args:
            conversion: 转化记录
            publisher: 渠道对象
            error_message: 错误信息
            click_params: 点击参数（可选）
            offer: Offer 对象（可选）
        
        Returns:
            str: 通知消息
        """
        msg = "❌ Postback 转发失败告警\n\n"
        msg += f"转化ID: {conversion.conversion_id}\n"
        msg += f"平台: {conversion.platform}\n"

        msg += "\n📤 渠道信息\n"
        msg += f"• 渠道ID: {publisher.id}\n"
        msg += f"• 渠道名称: {publisher.publisher_name}\n"
        if publisher.postback_url:
            url_display = publisher.postback_url[:100] + "..." if len(
                publisher.postback_url) > 100 else publisher.postback_url
            msg += f"• Postback URL: {url_display}\n"

        msg += "\n❌ 错误信息\n"
        error_display = error_message[:300] + "..." if len(error_message) > 300 else error_message
        msg += f"{error_display}\n"

        if click_params:
            try:
                click_params_str = json.dumps(click_params, ensure_ascii=False)
                msg += f"\n📋 点击参数\n{click_params_str}\n"
            except Exception:
                msg += f"\n📋 点击参数\n{str(click_params)}\n"

        if conversion.created_at:
            time_str = conversion.created_at.strftime("%Y-%m-%d %H:%M:%S")
            msg += f"\n⏰ 时间: {time_str}\n"

        return msg

    @staticmethod
    def build_admin_forward_success_message(
            conversion: PostbackConversion,
            publisher: Publisher,
            response_status: int,
            response_body: Optional[str] = None,
            offer: Optional[Offer] = None
    ) -> str:
        """
        构建管理员转发成功通知消息
        
        Args:
            conversion: 转化记录
            publisher: 渠道对象
            response_status: HTTP 响应状态码
            response_body: 响应内容（可选）
            offer: Offer 对象（可选）
        
        Returns:
            str: 通知消息
        """
        msg = "✅ Postback 转发成功\n\n"
        msg += f"转化ID: {conversion.conversion_id}\n"
        msg += f"平台: {conversion.platform}\n"

        msg += "\n📤 渠道信息\n"
        msg += f"• 渠道ID: {publisher.id}\n"
        msg += f"• 渠道名称: {publisher.publisher_name}\n"
        if publisher.postback_url:
            url_display = publisher.postback_url[:100] + "..." if len(
                publisher.postback_url) > 100 else publisher.postback_url
            msg += f"• Postback URL: {url_display}\n"

        msg += "\n✅ 响应信息\n"
        msg += f"• 状态码: {response_status}\n"
        if response_body:
            body_display = response_body[:200] + "..." if len(response_body) > 200 else response_body
            msg += f"• 响应: {body_display}\n"

        if conversion.created_at:
            time_str = conversion.created_at.strftime("%Y-%m-%d %H:%M:%S")
            msg += f"\n⏰ 时间: {time_str}\n"

        return msg

    @staticmethod
    def build_test_message(message_type: str = 'conversion') -> str:
        """
        构建测试消息
        
        Args:
            message_type: 消息类型（conversion, forward_failure, system_error）
        
        Returns:
            str: 测试消息
        """
        if message_type == 'conversion':
            msg = "📊 Postback 转化通知（管理员）\n\n"
            msg += "转化ID: TEST_CONVERSION_ID\n"
            msg += "平台: TEST_PLATFORM\n"
            msg += "事件: purchase\n\n"
            msg += "💰 金额信息\n"
            msg += "• 原始金额 (PO): $10.00\n"
            msg += "• 扣后金额 (PO(扣)): $8.50\n\n"
            msg += "👤 客户信息\n"
            msg += "• 客户: 测试客户\n"
            msg += "• 产品: 测试产品\n\n"
            msg += "📤 渠道信息\n"
            msg += "• 渠道ID: 1\n"
            msg += "• 渠道名称: 测试渠道\n\n"
            msg += "⏰ 时间: 2026-01-12 15:00:00\n"
        elif message_type == 'forward_failure':
            msg = "❌ Postback 转发失败告警\n\n"
            msg += "转化ID: TEST_CONVERSION_ID\n"
            msg += "平台: TEST_PLATFORM\n\n"
            msg += "📤 渠道信息\n"
            msg += "• 渠道ID: 1\n"
            msg += "• 渠道名称: 测试渠道\n"
            msg += "• Postback URL: https://example.com/postback\n\n"
            msg += "❌ 错误信息\n"
            msg += "HTTP 400: Bad Request\n\n"
            msg += "📋 点击参数\n"
            msg += '{"click_id": "1230180"}\n\n'
            msg += "⏰ 时间: 2026-01-12 15:00:00\n"
        elif message_type == 'system_error':
            msg = "⚠️ 系统异常告警\n\n"
            msg += "类型: 错误\n"
            msg += "描述: 测试系统异常\n\n"
            msg += "📍 位置\n"
            msg += "• 模块: test_module\n"
            msg += "• 函数: test_function\n"
            msg += "• 行号: 100\n\n"
            msg += "⏰ 时间: 2026-01-12 15:00:00\n"
        else:
            msg = "🔔 Telegram 通知测试\n\n这是一条测试消息。"

        return msg

    @staticmethod
    async def send_client_notification(
            message: str,
            telegram_chat_id: str,
            conversion: Optional[PostbackConversion] = None,
            client_id: Optional[int] = None,
            product_id: Optional[int] = None,
            notification_type: str = 'conversion',
            db: Optional[AsyncSession] = None
    ) -> bool:
        """
        向客户 Telegram Chat 发送通知并可选写入历史。

        有 conversion 时关联转化 ID；汇总类通知用 client_id / product_id 标识来源。

        Args:
            message: 消息正文
            telegram_chat_id: 目标 Chat ID
            conversion: 转化记录（单条通知时）
            client_id: 客户 ID（汇总通知时）
            product_id: 产品 ID（汇总通知时）
            notification_type: conversion / summary_hourly / summary_daily 等
            db: 数据库会话

        Returns:
            是否发送成功
        """
        try:

            success = await send_telegram_message_async(telegram_chat_id, message)

            # 记录通知历史（如果有数据库会话）
            if db:
                try:
                    # 如果有转化记录，使用转化记录的信息
                    if conversion:
                        record_client_id = conversion.client_id
                        record_product_id = conversion.product_id
                        record_conversion_id = conversion.id
                    else:
                        # 汇总通知，使用传入的 client_id 和 product_id
                        record_client_id = client_id
                        record_product_id = product_id
                        record_conversion_id = None

                    notification_record = PostbackNotification(
                        conversion_id=record_conversion_id,
                        client_id=record_client_id,
                        product_id=record_product_id,
                        publisher_id=None,
                        notification_type=notification_type,
                        notification_channel='telegram',
                        notification_status='sent' if success else 'failed',
                        notification_message=message,
                        error_message=None if success else "发送失败",
                        auto_notify=True,
                        postback_url=None,
                        created_at=get_app_now_naive()
                    )
                    db.add(notification_record)
                    await db.commit()
                except Exception as e:
                    logger.warning(f"记录客户通知历史失败: {str(e)}")
                    if db:
                        await db.rollback()

            return success
        except Exception as e:
            logger.error(f"发送客户通知失败: {str(e)}", exc_info=True)
            return False

    @staticmethod
    async def send_admin_notification(
            message: str,
            telegram_chat_id: Optional[str] = None,
            conversion: Optional[PostbackConversion] = None,
            notification_type: str = 'conversion',
            db: Optional[AsyncSession] = None
    ) -> bool:
        """
        向管理员 Telegram 发送通知。

        Chat ID 未传时走 _resolve_admin_chat_id；有 conversion 时写入通知历史
        （client_id / product_id 置空，区分于客户通知）。

        Args:
            message: 消息正文
            telegram_chat_id: 可选 Chat ID
            conversion: 关联转化记录
            notification_type: conversion / forward_failure / system_error 等
            db: 数据库会话

        Returns:
            是否发送成功
        """
        try:
            chat_id = TelegramNotificationService._resolve_admin_chat_id(telegram_chat_id)
            if not chat_id:
                logger.warning("Telegram Chat ID 未配置，无法发送管理员通知")
                return False

            success = await send_telegram_message_async(chat_id, message)

            # 记录通知历史（如果有转化记录和数据库会话）
            if conversion and db:
                try:
                    notification_record = PostbackNotification(
                        conversion_id=conversion.id,
                        client_id=None,  # 管理员通知不关联客户
                        product_id=None,  # 管理员通知不关联产品
                        publisher_id=None,
                        notification_type=notification_type,
                        notification_channel='telegram',
                        notification_status='sent' if success else 'failed',
                        notification_message=message,
                        error_message=None if success else "发送失败",
                        auto_notify=True,
                        postback_url=None,
                        created_at=get_app_now_naive()
                    )
                    db.add(notification_record)
                    await db.commit()
                except Exception as e:
                    logger.warning(f"记录管理员通知历史失败: {str(e)}")
                    if db:
                        await db.rollback()

            return success
        except Exception as e:
            logger.error(f"发送管理员通知失败: {str(e)}", exc_info=True)
            return False

    @staticmethod
    async def send_system_alert(
            alert_type: str,
            description: str,
            location: Optional[Dict[str, str]] = None,
            error: Optional[Exception] = None,
            telegram_chat_id: Optional[str] = None,
            db: Optional[AsyncSession] = None
    ) -> bool:
        """
        发送系统异常/错误告警至管理员 Telegram。

        消息由 build_alert_message 组装；写入 notification_type=system_alert 历史。

        Args:
            alert_type: 告警类型标识
            description: 告警描述
            location: 模块/函数/行号等位置信息
            error: 可选异常对象
            telegram_chat_id: 可选 Chat ID
            db: 数据库会话

        Returns:
            是否发送成功
        """
        try:
            message = build_alert_message(
                alert_type=alert_type,
                description=description,
                location=location,
                error=error
            )

            chat_id = TelegramNotificationService._resolve_admin_chat_id(telegram_chat_id)
            if not chat_id:
                logger.warning(
                    "Telegram Chat ID 未配置，无法发送系统告警: alert_type=%s",
                    alert_type,
                )
                return False

            success = await send_telegram_message_async(chat_id, message)

            if db:
                try:
                    notification_record = PostbackNotification(
                        conversion_id=None,
                        client_id=None,
                        product_id=None,
                        publisher_id=None,
                        notification_type='system_alert',
                        notification_channel='telegram',
                        notification_status='sent' if success else 'failed',
                        notification_message=message,
                        error_message=None if success else "发送失败",
                        auto_notify=True,
                        postback_url=None,
                        created_at=get_app_now_naive()
                    )
                    db.add(notification_record)
                    await db.commit()
                except Exception as e:
                    logger.warning(f"记录系统告警通知历史失败: {str(e)}")
                    if db:
                        await db.rollback()

            if success:
                logger.warning(
                    "系统告警已发送: alert_type=%s, description=%s",
                    alert_type,
                    description,
                )
            else:
                logger.warning(
                    "系统告警发送失败: alert_type=%s, description=%s",
                    alert_type,
                    description,
                )
            return success
        except Exception as e:
            logger.error(f"发送系统告警通知失败: {str(e)}", exc_info=True)
            return False

    @staticmethod
    async def send_summary_notification(
            summary_data: Dict[str, Any],
            period: str = 'today',
            telegram_chat_id: Optional[str] = None,
            db: Optional[AsyncSession] = None,
            client_id: Optional[int] = None,
            product_id: Optional[int] = None
    ) -> bool:
        """
        发送汇总统计通知
        
        Args:
            summary_data: 汇总数据字典
            period: 统计周期（today, hourly, daily, weekly, monthly）
            telegram_chat_id: Telegram Chat ID（可选）
            db: 数据库会话（可选，用于记录通知历史）
            client_id: 客户ID（可选，用于记录通知历史）
            product_id: 产品ID（可选，用于记录通知历史）
        
        Returns:
            bool: 是否发送成功
        """
        try:
            message = build_summary_message(
                summary_data=summary_data,
                period=period
            )

            chat_id = TelegramNotificationService._resolve_admin_chat_id(telegram_chat_id)
            if not chat_id:
                logger.warning("Telegram Chat ID 未配置，无法发送汇总统计通知")
                return False

            success = await send_telegram_message_async(chat_id, message)

            if db:
                try:
                    notification_record = PostbackNotification(
                        conversion_id=None,
                        client_id=client_id,
                        product_id=product_id,
                        publisher_id=None,
                        notification_type=f'summary_{period}',
                        notification_channel='telegram',
                        notification_status='sent' if success else 'failed',
                        notification_message=message,
                        error_message=None if success else "发送失败",
                        auto_notify=True,
                        postback_url=None,
                        created_at=get_app_now_naive()
                    )
                    db.add(notification_record)
                    await db.commit()
                except Exception as e:
                    logger.warning(f"记录汇总统计通知历史失败: {str(e)}")
                    if db:
                        await db.rollback()

            logger.info(f"汇总统计通知已发送: period={period}")
            return success
        except Exception as e:
            logger.error(f"发送汇总统计通知失败: {str(e)}", exc_info=True)
            return False

    @staticmethod
    async def send_batch_conversion_notifications(
            conversions: List[PostbackConversion],
            telegram_chat_id: str,
            db: Optional[AsyncSession] = None,
            client_id: Optional[int] = None,
            product_id: Optional[int] = None
    ) -> bool:
        """
        批量发送转化通知（用于汇总通知场景）
        
        Args:
            conversions: 转化记录列表
            telegram_chat_id: Telegram Chat ID
            db: 数据库会话（可选）
            client_id: 客户ID（可选）
            product_id: 产品ID（可选）
        
        Returns:
            bool: 是否发送成功
        """
        if not conversions:
            return True

        try:
            # 构建批量通知消息
            total_count = len(conversions)
            total_payout = sum(c.payout or 0 for c in conversions)
            total_original_payout = sum(c.original_payout or 0 for c in conversions)

            title = f"📊 批量转化通知 ({total_count} 条)"
            fields = {
                "总转化数": total_count,
                "总扣后收益": f"${total_payout:.2f}",
                "总原始收益": f"${total_original_payout:.2f}"
            }

            # 添加最近的几条转化详情
            recent_conversions = conversions[-5:]  # 只显示最近5条
            for i, conv in enumerate(recent_conversions, 1):
                fields[f"转化 {i}"] = f"ID: {conv.conversion_id}, 平台: {conv.platform}, 收益: ${conv.payout:.2f}"

            if total_count > 5:
                fields["提示"] = f"只显示最近5条，共 {total_count} 条转化"

            message = format_telegram_message(
                title=title,
                fields=fields,
                message_type='conversion'
            )

            # 分割长消息
            messages = split_long_message(message)

            all_success = True
            for msg in messages:
                success = await send_telegram_message_async(telegram_chat_id, msg)
                if not success:
                    all_success = False

            # 记录通知历史（只记录一次，使用第一条转化作为代表）
            if db and conversions:
                try:
                    notification_record = PostbackNotification(
                        conversion_id=conversions[0].id,
                        client_id=client_id,
                        product_id=product_id,
                        publisher_id=None,
                        notification_type='batch_conversion',
                        notification_channel='telegram',
                        notification_status='sent' if all_success else 'failed',
                        notification_message=message,
                        error_message=None if all_success else "部分或全部消息发送失败",
                        auto_notify=True,
                        postback_url=None,
                        created_at=get_app_now_naive()
                    )
                    db.add(notification_record)
                    await db.commit()
                except Exception as e:
                    logger.warning(f"记录批量转化通知历史失败: {str(e)}")
                    if db:
                        await db.rollback()

            logger.info(f"批量转化通知已发送: count={total_count}, success={all_success}")
            return all_success
        except Exception as e:
            logger.error(f"发送批量转化通知失败: {str(e)}", exc_info=True)
            return False

    @staticmethod
    async def send_notification_with_buttons(
            message: str,
            buttons: List[List[Dict[str, str]]],
            telegram_chat_id: Optional[str] = None,
            db: Optional[AsyncSession] = None,
            conversion: Optional[PostbackConversion] = None,
            notification_type: str = 'interactive'
    ) -> tuple[bool, Optional[int]]:
        """
        发送带按钮的交互式通知
        
        Args:
            message: 通知消息
            buttons: 按钮列表，格式：[[{"text": "按钮1", "callback_data": "data1"}, ...], ...]
            telegram_chat_id: Telegram Chat ID（可选）
            db: 数据库会话（可选，用于记录通知历史）
            conversion: 转化记录（可选，用于记录通知历史）
            notification_type: 通知类型
        
        Returns:
            tuple[bool, Optional[int]]: (是否发送成功, 消息ID)
        """
        try:
            chat_id = TelegramNotificationService._resolve_admin_chat_id(telegram_chat_id)
            if not chat_id:
                logger.warning("Telegram Chat ID 未配置，无法发送带按钮通知")
                return False, None

            success, message_id = await asyncio.to_thread(
                send_telegram_message_with_buttons,
                chat_id,
                message,
                buttons,
            )

            if db:
                try:
                    notification_record = PostbackNotification(
                        conversion_id=conversion.id if conversion else None,
                        client_id=conversion.client_id if conversion else None,
                        product_id=conversion.product_id if conversion else None,
                        publisher_id=None,
                        notification_type=notification_type,
                        notification_channel='telegram',
                        notification_status='sent' if success else 'failed',
                        notification_message=message,
                        error_message=None if success else "发送失败",
                        auto_notify=True,
                        postback_url=None,
                        created_at=get_app_now_naive()
                    )
                    db.add(notification_record)
                    await db.commit()
                except Exception as e:
                    logger.warning(f"记录交互式通知历史失败: {str(e)}")
                    if db:
                        await db.rollback()

            logger.info(f"交互式通知已发送: success={success}, message_id={message_id}")
            return success, message_id
        except Exception as e:
            logger.error(f"发送交互式通知失败: {str(e)}", exc_info=True)
            return False, None

    @staticmethod
    def build_pending_conversion_message(
            pending_conversion: Any,
            client_name: Optional[str] = None,
            product_name: Optional[str] = None
    ) -> tuple[str, List[List[Dict[str, str]]]]:
        """
        构建待确认转化通知消息（带确认/拒绝按钮）
        
        Args:
            pending_conversion: 待确认转化对象
            client_name: 客户名称（可选）
            product_name: 产品名称（可选）
        
        Returns:
            tuple[str, List[List[Dict[str, str]]]]: (消息文本, 按钮列表)
        """
        title = "⚠️ 待确认转化通知"
        fields = {
            "转化ID": pending_conversion.conversion_id,
            "平台": pending_conversion.platform,
            "请求IP": pending_conversion.request_ip,
        }

        if hasattr(pending_conversion, 'payout') and pending_conversion.payout:
            fields["收益"] = f"${pending_conversion.payout:.2f}"

        if hasattr(pending_conversion, 'original_payout') and pending_conversion.original_payout:
            fields["原始收益"] = f"${pending_conversion.original_payout:.2f}"

        if client_name:
            fields["客户"] = client_name

        if product_name:
            fields["产品"] = product_name

        if hasattr(pending_conversion, 'created_at') and pending_conversion.created_at:
            footer = f"⏰ 请求时间: {pending_conversion.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        else:
            footer = None

        message = format_telegram_message(
            title=title,
            fields=fields,
            footer=footer,
            message_type='warning'
        )

        buttons = [
            [
                {"text": "✅ 批准", "callback_data": f"postback_approve_{pending_conversion.id}"},
                {"text": "❌ 拒绝", "callback_data": f"postback_reject_{pending_conversion.id}"}
            ]
        ]

        return message, buttons
