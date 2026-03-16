"""
Postback 转发器（重构版）

负责将转化数据转发给渠道（Publisher）的 Postback URL

处理流程：
1. 获取渠道信息（带缓存）
2. 构建 Postback URL（占位符替换）
3. 发送 HTTP 请求
4. 检查转发结果
5. 记录转发日志
6. 发送通知（失败时）
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    PostbackConversion, PostbackForwardLog, Publisher,
    AdminNotificationConfig
)
from app.core.postback.forwarding.cache_manager import CacheManager
from app.core.postback.forwarding.url_builder import UrlBuilder
from app.core.postback.forwarding.placeholder_resolver import PlaceholderResolver
from app.core.postback.forwarding.http_client import HttpClient
from app.core.postback.forwarding.success_checker import SuccessChecker
from app.core.utils import get_app_now_naive
from app.services.telegram_notification_service import TelegramNotificationService

logger = logging.getLogger(__name__)


class PostbackForwarder:
    """Postback 转发器"""
    
    @staticmethod
    async def forward_to_publisher(
        conversion: PostbackConversion,
        click_association: Dict[str, Any],
        db: AsyncSession
    ) -> None:
        """
        将转化数据转发给渠道（Publisher）的 Postback URL
        
        Args:
            conversion: 转化记录
            click_association: Click 关联信息
            db: 数据库会话
        """
        logger.info(f"开始转发 Postback 到渠道：conversion_id={conversion.id}")
        
        # ========== 第 1 步：获取渠道信息 ==========
        publisher_id = click_association.get('publisher_id')
        if not publisher_id:
            logger.debug("没有 Publisher ID，跳过转发")
            return
        
        publisher = await CacheManager.get_cached_publisher(publisher_id, db)
        
        if not publisher or not publisher.postback_url:
            logger.warning(f"渠道无 Postback URL：publisher_id={publisher_id}")
            return
        
        if not publisher.is_active:
            logger.warning(f"渠道未激活：publisher_id={publisher_id}")
            return
        
        # ========== 第 2 步：准备数据 ==========
        conversion_data = {
            'conversion_id': conversion.conversion_id,
            'payout': conversion.payout,
            'event_name': conversion.event_name,
            'event_value': conversion.event_value,
            'ip': conversion.ip,
        }
        
        click_association_data = {
            'click_id': click_association.get('click_id'),
            'offer_id': click_association.get('offer_id'),
            'publisher_id': click_association.get('publisher_id'),
            'advertiser_id': click_association.get('advertiser_id'),
        }
        
        # ========== 第 3 步：构建 URL ==========
        base_url = publisher.postback_url
        
        # 先替换占位符
        url_data = {**conversion_data, **click_association_data}
        resolved_url = PlaceholderResolver.resolve(base_url, url_data)
        
        # 再添加查询参数
        final_url, params = UrlBuilder.build_postback_url(
            resolved_url,
            conversion_data,
            click_association_data
        )
        
        # ========== 第 4 步：发送 HTTP 请求 ==========
        method = publisher.postback_method or 'GET'
        success, status_code, response_content = await HttpClient.send_request(
            url=final_url,
            method=method
        )
        
        # ========== 第 5 步：检查转发结果 ==========
        success_check_config = publisher.postback_success_check
        check_success, check_message = SuccessChecker.check(
            status_code=status_code,
            response_content=response_content,
            success_check_config=success_check_config
        )
        
        final_success = success and check_success
        
        # ========== 第 6 步：记录转发日志 ==========
        forward_log = PostbackForwardLog(
            conversion_id=conversion.id,
            publisher_id=click_association.get('publisher_id'),
            request_url=final_url,
            request_method=method,
            response_status_code=status_code,
            response_content=response_content[:1000] if response_content else None,  # 限制长度
            is_success=final_success,
            check_message=check_message,
            created_at=get_app_now_naive()
        )
        
        db.add(forward_log)
        await db.commit()
        
        logger.info(
            f"Postback 转发完成：conversion_id={conversion.id}, "
            f"publisher_id={conversion.publisher_id}, success={final_success}"
        )
        
        # ========== 第 7 步：发送通知（失败时） ==========
        if not final_success:
            await PostbackForwarder._send_failure_notification(
                conversion=conversion,
                publisher=publisher,
                status_code=status_code,
                response_content=response_content,
                check_message=check_message,
                db=db
            )
    
    @staticmethod
    async def _send_failure_notification(
        conversion: PostbackConversion,
        publisher: Publisher,
        status_code: int,
        response_content: str,
        check_message: str,
        db: AsyncSession
    ):
        """发送转发失败通知"""
        try:
            admin_config_result = await db.execute(
                select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
            )
            admin_config = admin_config_result.scalars().first()
            
            if (
                admin_config
                and admin_config.telegram_enabled
                and admin_config.notify_forward_failure
                and admin_config.telegram_chat_id
            ):
                msg_lines = [
                    "❌ Postback 转发失败",
                    "",
                    f"平台：{conversion.platform}",
                    f"转化 ID: {conversion.conversion_id}",
                    f"渠道：{publisher.publisher_name}",
                    f"状态码：{status_code}",
                    f"检查结果：{check_message}",
                    "",
                    f"响应：{response_content[:200] if response_content else '无'}"
                ]
                
                await TelegramNotificationService.send_admin_notification(
                    message="\n".join(msg_lines),
                    telegram_chat_id=admin_config.telegram_chat_id,
                    notification_type='forward_failure',
                    db=db
                )
                
        except Exception as e:
            logger.warning(f"发送转发失败通知失败：{e}")


# 向后兼容：导入 select
from sqlalchemy import select
