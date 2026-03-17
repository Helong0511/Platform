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
import json
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
        db: AsyncSession,
        click_association: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        将转化数据转发给渠道（Publisher）的 Postback URL
        
        Args:
            conversion: 转化记录
            db: 数据库会话
            click_association: Click 关联信息（可选）
        """
        logger.warning(f"开始转发 Postback 到渠道：conversion_id={conversion.id}")
        
        # 详细日志：开始转发流程
        logger.warning(f"=== PostBack 转发流程开始 ===")
        logger.warning(f"转化 ID: {conversion.conversion_id}")
        logger.warning(f"平台: {conversion.platform}")
        logger.warning(f"接收到的 click_id: {conversion.click_id}")
        logger.warning(f"接收到的 payout: {conversion.payout}")
        
        # ========== 第 1 步：获取渠道信息 ==========
        publisher_id = None  # 渠道 ID
        click_association_data = {}  # Click 关联数据
        
        # 如果提供了 click_association，直接使用
        if click_association:
            publisher_id = click_association.get('publisher_id')
            # 构建 click_association_data 字典，包含所有必要的信息
            click_association_data = {
                'click_id': click_association.get('click_id'),  # 点击 ID
                'advertiser_id': click_association.get('advertiser_id'),  # 广告主 ID
                'offer_id': click_association.get('offer_id'),  # 广告任务 ID
                'publisher_id': click_association.get('publisher_id'),  # 渠道 ID
                'short_link_id': click_association.get('short_link_id'),  # 短链接 ID
                'url_params': click_association.get('url_params', {}),  # URL 参数
            }
            
            # 详细日志：Click 关联信息
            logger.warning(f"=== Click 关联信息 ===")
            logger.warning(f"click_id: {click_association_data.get('click_id')}")
            logger.warning(f"advertiser_id: {click_association_data.get('advertiser_id')}")
            logger.warning(f"offer_id: {click_association_data.get('offer_id')}")
            logger.warning(f"publisher_id: {click_association_data.get('publisher_id')}")
            logger.warning(f"short_link_id: {click_association_data.get('short_link_id')}")
            logger.warning(f"url_params: {click_association_data.get('url_params')}")
        else:
            # 如果没有提供 click_association，尝试从 conversion 中获取
            if conversion.click_id:
                from app.core.postback.transformers.click_associator import ClickAssociator
                # 通过 ClickAssociator 关联点击信息
                logger.warning(f"尝试通过 click_id 关联信息: {conversion.click_id}")
                click_association = await ClickAssociator.associate(
                    conversion.click_id,
                    db
                )
                if click_association:
                    publisher_id = click_association.get('publisher_id')
                    # 构建 click_association_data 字典
                    click_association_data = {
                        'click_id': click_association.get('click_id'),  # 点击 ID
                        'advertiser_id': click_association.get('advertiser_id'),  # 广告主
                        'offer_id': click_association.get('offer_id'),  # 广告任务 ID
                        'publisher_id': click_association.get('publisher_id'),  # 渠道 ID
                        'short_link_id': click_association.get('short_link_id'),  # 短链接 ID
                        'url_params': click_association.get('url_params', {}),  # URL 参数
                    }
                    
                    # 详细日志：Click 关联信息
                    logger.warning(f"=== Click 关联信息 ===")
                    logger.warning(f"click_id: {click_association_data.get('click_id')}")
                    logger.warning(f"advertiser_id: {click_association_data.get('advertiser_id')}")
                    logger.warning(f"offer_id: {click_association_data.get('offer_id')}")
                    logger.warning(f"publisher_id: {click_association_data.get('publisher_id')}")
                    logger.warning(f"short_link_id: {click_association_data.get('short_link_id')}")
                    logger.warning(f"url_params: {click_association_data.get('url_params')}")
        
        # 如果没有找到 publisher_id，跳过转发
        if not publisher_id:
            logger.debug("没有 Publisher ID，跳过转发")
            return
        
        # 从缓存中获取渠道信息
        logger.warning(f"获取渠道信息：publisher_id={publisher_id}")
        publisher = await CacheManager.get_cached_publisher(publisher_id, db)
        
        # 检查渠道是否存在且有 postback_url
        if not publisher or not publisher.postback_url:
            logger.warning(f"渠道无 Postback URL：publisher_id={publisher_id}")
            return
        
        # 检查渠道是否激活
        if not publisher.is_active:
            logger.warning(f"渠道未激活：publisher_id={publisher_id}")
            return
        
        # 详细日志：渠道信息
        logger.warning(f"=== 渠道信息 ===")
        logger.warning(f"渠道名称: {publisher.publisher_name}")
        logger.warning(f"postback_url: {publisher.postback_url}")
        logger.warning(f"postback_method: {publisher.postback_method or 'GET'}")
        logger.warning(f"postback_success_check: {publisher.postback_success_check}")
        
        # ========== 第 2 步：准备数据 ==========
        # 构建转化数据字典
        conversion_data = {
            'conversion_id': conversion.conversion_id,  # 转化 ID
            'payout': conversion.payout,  # 支付金额
            'event_name': conversion.event_name,  # 事件名称
            'event_value': conversion.event_value,  # 事件值
            'ip': conversion.ip,  # IP 地址
        }
        
        # 详细日志：转化数据
        logger.warning(f"=== 转化数据 ===")
        logger.warning(f"conversion_id: {conversion_data.get('conversion_id')}")
        logger.warning(f"payout: {conversion_data.get('payout')}")
        logger.warning(f"event_name: {conversion_data.get('event_name')}")
        
        # ========== 第 3 步：构建 URL ==========
        base_url = publisher.postback_url  # 渠道的 postback URL
        
        # 详细日志：URL 构建过程
        logger.warning(f"=== URL 构建过程 ===")
        logger.warning(f"原始 postback_url: {base_url}")
        
        # 合并数据用于占位符替换
        url_data = {**conversion_data, **click_association_data}
        # 解析 URL 中的占位符
        resolved_url = PlaceholderResolver.resolve(base_url, url_data)
        logger.warning(f"解析占位符后 URL: {resolved_url}")
        
        # 构建最终的 postback URL，添加必要的参数
        final_url, params = UrlBuilder.build_postback_url(
            resolved_url,
            conversion_data,
            click_association_data
        )
        logger.warning(f"最终 URL: {final_url}")
        logger.warning(f"构建的参数: {params}")
        
        # ========== 第 4 步：发送 HTTP 请求 ==========
        # 获取渠道配置的请求方法，默认为 GET
        method = publisher.postback_method or 'GET'
        
        # 详细日志：请求准备
        logger.warning(f"=== 请求准备 ===")
        logger.warning(f"请求方法: {method}")
        
        # 准备请求参数
        request_params = None  # GET 请求参数
        json_data = None  # POST 请求的 JSON 数据
        
        if method.upper() == 'POST':
            # 对于 POST 请求，构建 JSON 数据
            json_data = {}
            
            # 从 conversion_data 中提取数据
            if conversion_data.get('payout'):
                json_data['payout'] = conversion_data['payout']
            if conversion_data.get('conversion_id'):
                json_data['conversion_id'] = conversion_data['conversion_id']
            if conversion_data.get('event_name'):
                json_data['event_name'] = conversion_data['event_name']
            
            # 从 click_association 中提取数据，优先使用 url_params
            url_params = click_association_data.get('url_params', {})
            if url_params.get('click_id'):
                # 同时添加带下划线和不带下划线的版本，确保兼容性
                json_data['clickid'] = url_params['click_id']
                json_data['click_id'] = url_params['click_id']
            elif click_association_data.get('click_id'):
                json_data['clickid'] = click_association_data['click_id']
                json_data['click_id'] = click_association_data['click_id']
            
            # 添加 offer_id
            if url_params.get('offer_id'):
                json_data['offer_id'] = url_params['offer_id']
            elif click_association_data.get('offer_id'):
                json_data['offer_id'] = click_association_data['offer_id']
            
            logger.warning(f"POST JSON 数据: {json_data}")
        else:
            # 对于 GET 请求，参数已经在 URL 中
            request_params = params
            logger.warning(f"GET 请求参数: {request_params}")
        
        # 详细日志：发送请求
        logger.warning(f"=== 发送 HTTP 请求 ===")
        logger.warning(f"发送请求到: {final_url}")
        
        # 发送 HTTP 请求
        success, status_code, response_content = await HttpClient.send_request(
            url=final_url,
            method=method,
            params=request_params,
            json_data=json_data
        )
        
        # 详细日志：请求结果
        logger.warning(f"=== 请求结果 ===")
        logger.warning(f"请求成功: {success}")
        logger.warning(f"状态码: {status_code}")
        logger.warning(f"响应内容: {response_content[:500] if response_content else '无'}")
        
        # ========== 第 5 步：检查转发结果 ==========
        # 获取渠道配置的成功检查规则
        success_check_config = publisher.postback_success_check
        # 检查转发是否成功
        check_success, check_message = SuccessChecker.check(
            status_code=status_code,
            response_content=response_content,
            success_check_config=success_check_config
        )
        
        # 最终成功状态：请求成功且检查通过
        final_success = success and check_success
        
        # ========== 第 6 步：记录转发日志 ==========
        # 创建转发日志记录
        forward_log = PostbackForwardLog(
            conversion_id=conversion.id,  # 转化 ID
            product_id=conversion.product_id,  # 产品 ID
            publisher_id=publisher_id,  # 渠道 ID
            downstream_url=final_url,  # 下游 URL
            request_method=method,  # 请求方法
            request_params=json.dumps(params, ensure_ascii=False) if params else None,  # 请求参数
            response_status=status_code,  # 响应状态码
            response_body=response_content[:1000] if response_content else None,  # 响应内容（限制长度）
            success=final_success,  # 是否成功
            error_message=check_message if not final_success else None,  # 错误信息
            created_at=get_app_now_naive(),  # 创建时间
            completed_at=get_app_now_naive()  # 完成时间
        )
        
        # 添加到数据库
        db.add(forward_log)
        await db.flush()
        
        logger.warning(
            f"Postback 转发完成：conversion_id={conversion.id}, "
            f"publisher_id={publisher_id}, success={final_success}"
        )
        
        # ========== 第 7 步：发送通知（失败时） ==========
        if not final_success:
            # 发送转发失败通知
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
            # 查询管理员通知配置
            admin_config_result = await db.execute(
                select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
            )
            admin_config = admin_config_result.scalars().first()
            
            # 检查是否启用了 Telegram 通知且配置了聊天 ID
            if (
                admin_config
                and admin_config.telegram_enabled
                and admin_config.notify_forward_failure
                and admin_config.telegram_chat_id
            ):
                # 构建通知消息
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
                
                # 发送 Telegram 通知
                await TelegramNotificationService.send_admin_notification(
                    message="\n".join(msg_lines),
                    telegram_chat_id=admin_config.telegram_chat_id,
                    notification_type='forward_failure',
                    db=db
                )
                
        except Exception as e:
            # 记录发送通知失败的错误
            logger.warning(f"发送转发失败通知失败：{e}")


# 向后兼容：导入 select
from sqlalchemy import select
