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
import asyncio
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    PostbackConversion, PostbackForwardLog, PostbackForwardQueue, Publisher,
    AdminNotificationConfig
)
from app.core.postback.forwarding.cache_manager import CacheManager
from app.core.postback.forwarding.url_builder import UrlBuilder
from app.core.postback.forwarding.placeholder_resolver import PlaceholderResolver
from app.core.postback.forwarding.http_client import HttpClient
from app.core.postback.forwarding.success_checker import SuccessChecker
from app.core.utils import get_app_now_naive
from app.services.telegram_notification_service import TelegramNotificationService
from app.core.url.url_params_util import (
    build_click_association_payload,
    scalar_query_value,
)

logger = logging.getLogger(__name__)

# 通知是尽力而为的旁路任务，不应占用 Postback 队列租约。
# 保留 Task 引用，避免后台通知协程在完成前被垃圾回收。
_notification_tasks: set[asyncio.Task] = set()


def _schedule_admin_notification(
    *,
    message: str,
    telegram_chat_id: str,
    notification_type: str,
) -> None:
    """异步调度管理员通知，不阻塞下游回传队列的确认/重试。"""
    task = asyncio.create_task(
        TelegramNotificationService.send_admin_notification(
            message=message,
            telegram_chat_id=telegram_chat_id,
            notification_type=notification_type,
        )
    )
    _notification_tasks.add(task)

    def _on_done(completed: asyncio.Task) -> None:
        _notification_tasks.discard(completed)
        if completed.cancelled():
            return
        try:
            error = completed.exception()
        except Exception as exc:
            logger.warning("读取 Postback 通知后台任务结果失败: %s", exc)
            return
        if error:
            logger.warning("Postback 管理员通知后台任务异常: %s", error, exc_info=error)

    task.add_done_callback(_on_done)


async def _lock_conversion_for_queue_enqueue(
    db: AsyncSession,
    conversion_id: int,
) -> bool:
    """锁定转化主记录，串行化同一转化的队列去重检查与插入。

    仅依赖「先 SELECT 队列、再 INSERT」会在并发首次入队时产生重复记录。
    所有入队路径先锁同一转化行，再检查目标队列；锁持续到外层事务提交。
    """
    result = await db.execute(
        select(PostbackConversion.id)
        .where(PostbackConversion.id == conversion_id)
        .with_for_update()
    )
    return result.scalars().first() is not None


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
        logger.info(f"开始转发 Postback 到渠道：conversion_id={conversion.id}")
        
        # 详细日志：开始转发流程
        logger.info(f"=== PostBack 转发流程开始 ===")
        logger.info(f"转化 ID: {conversion.conversion_id}")
        logger.info(f"平台: {conversion.platform}")
        logger.info(f"接收到的 click_id: {conversion.click_id}")
        logger.info(f"接收到的 payout: {conversion.payout}")
        
        # ========== 第 1 步：获取渠道信息 ==========
        publisher_id = None  # 渠道 ID
        click_association_data = {}  # Click 关联数据
        
        # 如果提供了 click_association，直接使用
        if click_association:
            publisher_id = click_association.get('publisher_id')
            click_association_data = build_click_association_payload(click_association)
            
            # 详细日志：Click 关联信息
            logger.info(f"=== Click 关联信息 ===")
            logger.info(f"click_id: {click_association_data.get('click_id')}")
            logger.info(f"advertiser_id: {click_association_data.get('advertiser_id')}")
            logger.info(f"offer_id: {click_association_data.get('offer_id')}")
            logger.info(f"publisher_id: {click_association_data.get('publisher_id')}")
            logger.info(f"short_link_id: {click_association_data.get('short_link_id')}")
            logger.info(f"url_params: {click_association_data.get('url_params')}")
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
                    click_association_data = build_click_association_payload(
                        click_association
                    )
                    
                    # 详细日志：Click 关联信息
                    logger.info(f"=== Click 关联信息 ===")
                    logger.info(f"click_id: {click_association_data.get('click_id')}")
                    logger.info(f"advertiser_id: {click_association_data.get('advertiser_id')}")
                    logger.info(f"offer_id: {click_association_data.get('offer_id')}")
                    logger.info(f"publisher_id: {click_association_data.get('publisher_id')}")
                    logger.info(f"short_link_id: {click_association_data.get('short_link_id')}")
                    logger.info(f"url_params: {click_association_data.get('url_params')}")
        
        # 如果没有找到 publisher_id，跳过转发
        if not publisher_id:
            logger.debug("没有 Publisher ID，跳过转发")
            return
        
        # 从缓存中获取渠道信息
        logger.info(f"获取渠道信息：publisher_id={publisher_id}")
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
        logger.info(f"=== 渠道信息 ===")
        logger.info(f"渠道名称: {publisher.publisher_name}")
        logger.info(f"postback_url: {publisher.postback_url}")
        logger.info(f"postback_method: {publisher.postback_method or 'GET'}")
        logger.info(f"postback_success_check: {publisher.postback_success_check}")
        
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
        logger.info(f"=== 转化数据 ===")
        logger.info(f"conversion_id: {conversion_data.get('conversion_id')}")
        logger.info(f"payout: {conversion_data.get('payout')}")
        logger.info(f"event_name: {conversion_data.get('event_name')}")
        
        # ========== 第 3 步：构建 URL ==========
        base_url = publisher.postback_url  # 渠道的 postback URL
        
        # 详细日志：URL 构建过程
        logger.info(f"=== URL 构建过程 ===")
        logger.info(f"原始 postback_url: {base_url}")
        
        # 合并数据用于占位符替换
        url_data = {**conversion_data, **click_association_data}
        # 解析 URL 中的占位符
        resolved_url = PlaceholderResolver.resolve(base_url, url_data)
        logger.info(f"解析占位符后 URL: {resolved_url}")
        
        # 构建最终的 postback URL，添加必要的参数
        final_url, params = UrlBuilder.build_postback_url(
            resolved_url,
            conversion_data,
            click_association_data
        )
        logger.info(f"最终 URL: {final_url}")
        logger.info(f"构建的参数: {params}")
        
        # ========== 第 4 步：发送 HTTP 请求 ==========
        # 获取渠道配置的请求方法，默认为 GET
        method = publisher.postback_method or 'GET'
        
        # 详细日志：请求准备
        logger.info(f"=== 请求准备 ===")
        logger.info(f"请求方法: {method}")
        
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
            cid = scalar_query_value(url_params.get('click_id')) or click_association_data.get(
                'click_id'
            )
            if cid:
                json_data['clickid'] = str(cid)
                json_data['click_id'] = str(cid)

            oid = scalar_query_value(url_params.get('offer_id')) or click_association_data.get(
                'offer_id'
            )
            if oid is not None:
                json_data['offer_id'] = str(oid)
            
            logger.info(f"POST JSON 数据: {json_data}")
        else:
            # 对于 GET 请求，参数已经在 URL 中
            request_params = params
            logger.info(f"GET 请求参数: {request_params}")
        
        # 详细日志：发送请求
        logger.info(f"=== 发送 HTTP 请求 ===")
        logger.info(f"发送请求到: {final_url}")
        
        # 发送 HTTP 请求
        success, status_code, response_content = await HttpClient.send_request(
            url=final_url,
            method=method,
            params=request_params,
            json_data=json_data
        )
        
        # 详细日志：请求结果
        logger.info(f"=== 请求结果 ===")
        logger.info(f"请求成功: {success}")
        logger.info(f"状态码: {status_code}")
        logger.info(f"响应内容: {response_content[:500] if response_content else '无'}")
        
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
        
        logger.info(
            f"Postback 转发完成：conversion_id={conversion.id}, "
            f"publisher_id={publisher_id}, success={final_success}"
        )

        if not final_success:
            await PostbackForwarder._enqueue_publisher_forward_retry(
                db=db,
                conversion=conversion,
                publisher_id=publisher_id,
                downstream_url=final_url,
                method=method,
                params=params,
                json_data=json_data if method.upper() == "POST" else None,
            )
        
        # ========== 第 7 步：发送通知（失败和成功时） ==========
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
        else:
            # 发送转发成功通知（如果启用）
            await PostbackForwarder._send_success_notification(
                conversion=conversion,
                publisher=publisher,
                status_code=status_code,
                response_content=response_content,
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
                
                # 通知异步旁路发送，不能让 Telegram 限流/网络重试延长队列租约。
                _schedule_admin_notification(
                    message="\n".join(msg_lines),
                    telegram_chat_id=admin_config.telegram_chat_id,
                    notification_type='forward_failure',
                )
                
        except Exception as e:
            # 记录发送通知失败的错误
            logger.warning(f"发送转发失败通知失败：{e}")
    
    @staticmethod
    async def _send_success_notification(
        conversion: PostbackConversion,
        publisher: Publisher,
        status_code: int,
        response_content: str,
        db: AsyncSession
    ):
        """发送转发成功通知"""
        try:
            # 查询管理员通知配置
            admin_config_result = await db.execute(
                select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
            )
            admin_config = admin_config_result.scalars().first()
            
            # 检查是否启用了 Telegram 通知且配置了聊天 ID，并且启用了转发成功通知
            if (
                admin_config
                and admin_config.telegram_enabled
                and admin_config.notify_forward_success
                and admin_config.telegram_chat_id
            ):
                # 构建通知消息
                msg_lines = [
                    "✅ Postback 转发成功",
                    "",
                    f"平台：{conversion.platform}",
                    f"转化 ID: {conversion.conversion_id}",
                    f"渠道：{publisher.publisher_name}",
                    f"状态码：{status_code}",
                    "",
                    f"响应：{response_content[:200] if response_content else '无'}"
                ]
                
                # 通知异步旁路发送，不能让 Telegram 限流/网络重试延长队列租约。
                _schedule_admin_notification(
                    message="\n".join(msg_lines),
                    telegram_chat_id=admin_config.telegram_chat_id,
                    notification_type='forward_success',
                )
                
        except Exception as e:
            # 记录发送通知失败的错误
            logger.warning(f"发送转发成功通知失败：{e}")

    @staticmethod
    async def forward_to_product(
        conversion: PostbackConversion,
        db: AsyncSession,
        click_association: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        将转化数据转发到产品配置的下游 Postback URL（追加于渠道转发之外）。

        仅当 conversion.product_id 存在且产品配置了 downstream_postback_url 时执行。
        """
        if not conversion.product_id:
            logger.debug("转化无 product_id，跳过产品级转发")
            return

        logger.info(
            "开始产品级 Postback 转发：conversion_id=%s product_id=%s",
            conversion.id,
            conversion.product_id,
        )

        product = await CacheManager.get_cached_product(conversion.product_id, db)
        if not product or not product.downstream_postback_url:
            logger.debug(
                "产品无下游 Postback URL，跳过：product_id=%s",
                conversion.product_id,
            )
            return
        if not product.is_active:
            logger.warning(
                "产品未激活，跳过产品级转发：product_id=%s",
                conversion.product_id,
            )
            return

        click_association_data = {}
        if click_association:
            click_association_data = build_click_association_payload(click_association)
        elif conversion.click_id:
            from app.core.postback.transformers.click_associator import ClickAssociator
            click_association = await ClickAssociator.associate(conversion.click_id, db)
            if click_association:
                click_association_data = build_click_association_payload(click_association)

        conversion_data = {
            'conversion_id': conversion.conversion_id,
            'payout': conversion.payout,
            'event_name': conversion.event_name,
            'event_value': conversion.event_value,
            'ip': conversion.ip,
        }

        base_url = product.downstream_postback_url
        url_data = {**conversion_data, **click_association_data}
        resolved_url = PlaceholderResolver.resolve(base_url, url_data)
        final_url, params = UrlBuilder.build_postback_url(
            resolved_url,
            conversion_data,
            click_association_data,
        )

        method = product.downstream_postback_method or 'GET'
        request_params = None
        json_data = None

        if method.upper() == 'POST':
            json_data = {}
            if conversion_data.get('payout'):
                json_data['payout'] = conversion_data['payout']
            if conversion_data.get('conversion_id'):
                json_data['conversion_id'] = conversion_data['conversion_id']
            if conversion_data.get('event_name'):
                json_data['event_name'] = conversion_data['event_name']
            url_params = click_association_data.get('url_params', {})
            cid = scalar_query_value(url_params.get('click_id')) or click_association_data.get(
                'click_id'
            )
            if cid:
                json_data['clickid'] = str(cid)
                json_data['click_id'] = str(cid)
            oid = scalar_query_value(url_params.get('offer_id')) or click_association_data.get(
                'offer_id'
            )
            if oid is not None:
                json_data['offer_id'] = str(oid)
        else:
            request_params = params

        success, status_code, response_content = await HttpClient.send_request(
            url=final_url,
            method=method,
            params=request_params,
            json_data=json_data,
        )

        check_success, check_message = SuccessChecker.check(
            status_code=status_code,
            response_content=response_content,
            success_check_config=product.downstream_postback_success_check,
        )
        final_success = success and check_success

        forward_log = PostbackForwardLog(
            conversion_id=conversion.id,
            product_id=conversion.product_id,
            publisher_id=None,
            downstream_url=final_url,
            request_method=method,
            request_params=json.dumps(params, ensure_ascii=False) if params else None,
            response_status=status_code,
            response_body=response_content[:1000] if response_content else None,
            success=final_success,
            error_message=check_message if not final_success else None,
            created_at=get_app_now_naive(),
            completed_at=get_app_now_naive(),
        )
        db.add(forward_log)
        await db.flush()

        logger.info(
            "产品级 Postback 转发完成：conversion_id=%s, product_id=%s, success=%s",
            conversion.id,
            conversion.product_id,
            final_success,
        )

        if not final_success:
            await PostbackForwarder._enqueue_product_forward_retry(
                db=db,
                conversion=conversion,
                product_id=conversion.product_id,
                downstream_url=final_url,
                method=method,
                params=params,
                json_data=json_data if method.upper() == "POST" else None,
            )

    @staticmethod
    async def _enqueue_publisher_forward_retry(
        db: AsyncSession,
        conversion: PostbackConversion,
        publisher_id: int,
        downstream_url: str,
        method: str,
        params: Optional[Dict[str, Any]],
        json_data: Optional[Dict[str, Any]],
    ) -> None:
        """转发失败时写入重试队列，由定时任务指数退避重试。"""
        try:
            # 对同一 conversion 加行锁，使并发首次入队的去重查询串行执行。
            if not await _lock_conversion_for_queue_enqueue(db, conversion.id):
                logger.warning(
                    "转发入队跳过：转化记录不存在: conversion_id=%s",
                    conversion.id,
                )
                return
            existing = await db.execute(
                select(PostbackForwardQueue).where(
                    PostbackForwardQueue.conversion_id == conversion.id,
                    PostbackForwardQueue.publisher_id == publisher_id,
                )
                # 使用当前读：在 MySQL REPEATABLE READ 下，普通 SELECT 可能沿用
                # 等待行锁前建立的旧快照，看不到刚由前一个事务提交的队列记录。
                .with_for_update()
            )
            if existing.scalars().first():
                logger.debug(
                    "转发重试队列已存在: conversion_id=%s publisher_id=%s",
                    conversion.id,
                    publisher_id,
                )
                return

            task = PostbackForwardQueue(
                conversion_id=conversion.id,
                product_id=None,
                publisher_id=publisher_id,
                downstream_url=downstream_url,
                request_method=method,
                request_params=json.dumps(params, ensure_ascii=False) if params else None,
                request_data=json.dumps(json_data, ensure_ascii=False) if json_data else None,
                retry_count=0,
                next_retry_time=get_app_now_naive(),
            )
            db.add(task)
            await db.flush()
            logger.info(
                "转发失败已入重试队列: conversion_id=%s publisher_id=%s",
                conversion.id,
                publisher_id,
            )
            import asyncio
            from app.scheduler_module.tasks.forward_tasks import trigger_forward_processing

            asyncio.create_task(trigger_forward_processing())
        except Exception as exc:
            logger.error(
                "入队转发重试失败: conversion_id=%s err=%s",
                conversion.id,
                exc,
                exc_info=True,
            )

    @staticmethod
    async def _enqueue_product_forward_retry(
        db: AsyncSession,
        conversion: PostbackConversion,
        product_id: int,
        downstream_url: str,
        method: str,
        params: Optional[Dict[str, Any]],
        json_data: Optional[Dict[str, Any]],
    ) -> None:
        """产品级转发失败时写入重试队列。"""
        try:
            # 与渠道级共用转化主记录锁，避免不同消费者同时插入重复产品任务。
            if not await _lock_conversion_for_queue_enqueue(db, conversion.id):
                logger.warning(
                    "产品级转发入队跳过：转化记录不存在: conversion_id=%s",
                    conversion.id,
                )
                return
            existing = await db.execute(
                select(PostbackForwardQueue).where(
                    PostbackForwardQueue.conversion_id == conversion.id,
                    PostbackForwardQueue.product_id == product_id,
                    PostbackForwardQueue.publisher_id.is_(None),
                )
                # 与渠道级查询一样必须读取最新已提交状态，避免旧快照导致重复插入。
                .with_for_update()
            )
            if existing.scalars().first():
                logger.debug(
                    "产品级转发重试队列已存在: conversion_id=%s product_id=%s",
                    conversion.id,
                    product_id,
                )
                return

            task = PostbackForwardQueue(
                conversion_id=conversion.id,
                product_id=product_id,
                publisher_id=None,
                downstream_url=downstream_url,
                request_method=method,
                request_params=json.dumps(params, ensure_ascii=False) if params else None,
                request_data=json.dumps(json_data, ensure_ascii=False) if json_data else None,
                retry_count=0,
                next_retry_time=get_app_now_naive(),
            )
            db.add(task)
            await db.flush()
            logger.info(
                "产品级转发失败已入重试队列: conversion_id=%s product_id=%s",
                conversion.id,
                product_id,
            )
            import asyncio
            from app.scheduler_module.tasks.forward_tasks import trigger_forward_processing

            asyncio.create_task(trigger_forward_processing())
        except Exception as exc:
            logger.error(
                "入队产品级转发重试失败: conversion_id=%s err=%s",
                conversion.id,
                exc,
                exc_info=True,
            )


# 向后兼容：导入 select
from sqlalchemy import select
