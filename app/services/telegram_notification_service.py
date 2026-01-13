"""
Telegram 通知服务
负责构建和发送 Telegram 通知消息（客户和管理员）
"""
import json
import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    PostbackConversion, Client, Product, Publisher, Offer, User, PostbackNotification
)
from app.core.auto_bot import send_telegram_message
from app.core.utils import get_app_now_naive

logger = logging.getLogger(__name__)


class TelegramNotificationService:
    """Telegram 通知服务"""
    
    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
    
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
    def build_admin_conversion_message(
        conversion: PostbackConversion,
        client_name: Optional[str] = None,
        product_name: Optional[str] = None,
        publisher: Optional[Publisher] = None,
        offer: Optional[Offer] = None
    ) -> str:
        """
        构建管理员转化通知消息
        
        Args:
            conversion: 转化记录
            client_name: 客户名称（可选）
            product_name: 产品名称（可选）
            publisher: 渠道对象（可选）
            offer: Offer 对象（可选）
        
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
            url_display = publisher.postback_url[:100] + "..." if len(publisher.postback_url) > 100 else publisher.postback_url
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
            url_display = publisher.postback_url[:100] + "..." if len(publisher.postback_url) > 100 else publisher.postback_url
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
        发送客户通知
        
        Args:
            message: 通知消息
            telegram_chat_id: Telegram Chat ID
            conversion: 转化记录（可选，用于记录通知历史）
            client_id: 客户ID（可选，用于汇总通知）
            product_id: 产品ID（可选，用于汇总通知）
            notification_type: 通知类型（conversion, summary_hourly, summary_daily）
            db: 数据库会话（可选）
        
        Returns:
            bool: 是否发送成功
        """
        try:
            success = await send_telegram_message(message, chat_id=telegram_chat_id)
            
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
        发送管理员通知
        
        Args:
            message: 通知消息
            telegram_chat_id: Telegram Chat ID（可选，如果未提供则使用配置中的）
            conversion: 转化记录（可选，用于记录通知历史）
            notification_type: 通知类型（conversion, forward_failure, system_error等）
            db: 数据库会话（可选）
        
        Returns:
            bool: 是否发送成功
        """
        try:
            success = await send_telegram_message(message, chat_id=telegram_chat_id)
            
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
