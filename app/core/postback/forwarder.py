"""
Postback 转发服务
负责将接收到的 postback 数据转发给渠道（Publisher）

注意：PostBack 数据只转发给渠道（Publisher），不转发给其他系统
"""
import json
import logging
import asyncio
import re
from typing import Dict, Any, Optional, Union, Tuple
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse, quote

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.models.models import (
    Product, PostbackConversion, PostbackForwardLog, PostbackNotification,
    ClickStats, Click, Offer, Publisher, Advertiser
)
from app.core.utils import get_app_now_naive

logger = logging.getLogger(__name__)


class PostbackForwarder:
    """Postback 转发器（主要用于转发给渠道）"""

    @staticmethod
    async def forward_to_publisher(
        conversion: PostbackConversion,
        db: AsyncSession
    ) -> None:
        """
        将转化数据转发给渠道（Publisher）的 Postback URL
        
        Args:
            conversion: 转化记录
            db: 数据库会话
        """
        # 1. 通过 click_id 查找关联的 Publisher
        # 注意：postback_conversions.conversion_id = clicks.click_id
        # 优先使用 conversion_id，如果不存在则使用 click_id 字段（兼容性）
        publisher = None
        click_record = None
        offer = None
        advertiser = None
        
        # 获取用于查找点击记录的 click_id
        # 优先使用 conversion_id（因为 conversion_id = clicks.click_id）
        lookup_click_id = conversion.conversion_id if conversion.conversion_id else conversion.click_id
        
        if lookup_click_id:
            # 优先从 ClickStats 获取核心字段，然后查询关联的 Publisher、Offer、Advertiser
            # 如果 Click 表还有数据，也可以从中获取（兼容性）
            click_stats_result = await db.execute(
                select(ClickStats).where(ClickStats.click_id == lookup_click_id)
            )
            click_stats = click_stats_result.scalars().first()
            
            if click_stats:
                # 从 ClickStats 获取 publisher_id，然后查询 Publisher
                if click_stats.publisher_id:
                    publisher_result = await db.execute(
                        select(Publisher).where(Publisher.id == click_stats.publisher_id)
                    )
                    publisher = publisher_result.scalars().first()
                
                # 从 ClickStats 获取 offer_id，然后查询 Offer 和 Advertiser
                if click_stats.offer_id:
                    offer_result = await db.execute(
                        select(Offer)
                        .options(joinedload(Offer.advertiser))
                        .where(Offer.id == click_stats.offer_id)
                    )
                    # 使用joinedload时，为了安全起见使用unique()去重
                    offer = offer_result.unique().scalars().first()
                    if offer:
                        advertiser = offer.advertiser
            
            # 如果 ClickStats 中没有找到 publisher，尝试从 Click 表获取（兼容性，如果数据还未清理）
            # 或者 ClickStats 存在但没有 publisher_id（数据不完整的情况）
            if (not publisher or not click_stats) and lookup_click_id:
                try:
                    click_result = await db.execute(
                        select(Click)
                        .options(
                            joinedload(Click.publisher),
                            joinedload(Click.offer).joinedload(Offer.advertiser)
                        )
                        .where(Click.click_id == lookup_click_id)
                    )
                    # 使用joinedload时，为了安全起见使用unique()去重
                    click_record = click_result.unique().scalars().first()
                    
                    if click_record:
                        publisher = click_record.publisher
                        offer = click_record.offer
                        if offer:
                            advertiser = offer.advertiser
                except Exception as e:
                    # Click 表可能不存在或数据已清理，忽略错误
                    logger.debug(f"无法从 Click 表加载数据: {e}")
        
        # 2. 如果没有找到 Publisher，创建通知记录后返回
        if not publisher:
            lookup_click_id = conversion.conversion_id if conversion.conversion_id else conversion.click_id
            logger.debug(
                f"未找到关联的渠道，跳过转发: conversion_id={conversion.id}, "
                f"conversion_id={conversion.conversion_id}, click_id={lookup_click_id}"
            )
            # 即使没有找到 Publisher，也创建通知记录（用于后续手动通知）
            try:
                notification_record = PostbackNotification(
                    conversion_id=conversion.id,
                    publisher_id=None,  # 没有找到 Publisher
                    notification_type='forward',
                    notification_channel='webhook',
                    notification_status='pending',
                    notification_message=f"未找到关联的渠道，无法转发: conversion_id={conversion.conversion_id}",
                    auto_notify=False,  # 没有 postback_url，只能手动通知
                    postback_url=None,
                    created_at=get_app_now_naive()
                )
                db.add(notification_record)
                await db.commit()
            except Exception as e:
                logger.error(f"创建转发通知记录失败: {str(e)}", exc_info=True)
                await db.rollback()
            return
        
        # 2.1. 无论是否有 postback_url，都创建通知记录
        has_postback_url = bool(publisher.postback_url and publisher.postback_url.strip())
        
        # 构建通知消息
        notification_message = PostbackForwarder._build_forward_notification_message(
            conversion=conversion,
            publisher=publisher,
            offer=offer,
            has_postback_url=has_postback_url
        )
        
        # 创建通知记录（无论是否有 postback_url）
        notification_record = PostbackNotification(
            conversion_id=conversion.id,
            publisher_id=publisher.id,
            notification_type='forward',
            notification_channel='webhook',
            notification_status='pending',  # 初始状态为 pending
            notification_message=notification_message,
            auto_notify=has_postback_url,  # 如果有 postback_url，默认自动通知
            postback_url=publisher.postback_url if has_postback_url else None,
            created_at=get_app_now_naive()
        )
        db.add(notification_record)
        
        # 如果没有配置 Postback URL，保存通知记录后返回（不进行转发）
        if not has_postback_url:
            logger.debug(
                f"渠道未配置 Postback URL，创建通知记录后跳过转发: conversion_id={conversion.id}, "
                f"publisher_id={publisher.id}"
            )
            try:
                await db.commit()
            except Exception as e:
                logger.error(f"保存转发通知记录失败: {str(e)}", exc_info=True)
                await db.rollback()
            return
        
        downstream_url = publisher.postback_url.strip()
        method = (publisher.postback_method or 'GET').upper()
        
        if method not in ['GET', 'POST']:
            logger.warning(f"渠道 {publisher.id} 的 Postback 请求方式无效: {method}，使用默认 GET")
            method = 'GET'
        
        # 3. 替换 URL 中的占位符
        try:
            replaced_url = await PostbackForwarder._replace_url_placeholders(
                url=downstream_url,
                conversion=conversion,
                click=click_record,
                offer=offer,
                publisher=publisher,
                advertiser=advertiser,
                db=db
            )
        except Exception as e:
            logger.error(
                f"替换 URL 占位符失败: conversion_id={conversion.id}, "
                f"publisher_id={publisher.id}, error={str(e)}",
                exc_info=True
            )
            # 如果替换失败，使用原始 URL（可能包含未替换的占位符）
            replaced_url = downstream_url
        
        # 4. 自动通知模式：执行转发（因为 has_postback_url=True，所以 auto_notify=True）
        # 获取原始点击参数（如果有 click_id）
        # 注意：使用 conversion_id 来查找，因为 conversion_id = clicks.click_id
        click_params = {}
        lookup_click_id = conversion.conversion_id if conversion.conversion_id else conversion.click_id
        if lookup_click_id:
            try:
                # 如果 click_record 已存在且有 url_params，直接使用
                if click_record and click_record.url_params:
                    try:
                        # 解析 JSON 格式的 url_params
                        click_params_raw = json.loads(click_record.url_params)
                        # 过滤掉占位符
                        click_params = PostbackForwarder._filter_placeholders(click_params_raw)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(
                            f"解析点击参数失败: conversion_id={conversion.id}, "
                            f"conversion_id={conversion.conversion_id}, click_id={lookup_click_id}, error={str(e)}"
                        )
                else:
                    # 如果 click_record 不存在，尝试查询 Click 表获取 url_params
                    try:
                        click_result = await db.execute(
                            select(Click).where(Click.click_id == lookup_click_id)
                        )
                        click_for_params = click_result.scalars().first()
                        if click_for_params and click_for_params.url_params:
                            try:
                                # 解析 JSON 格式的 url_params
                                click_params_raw = json.loads(click_for_params.url_params)
                                # 过滤掉占位符
                                click_params = PostbackForwarder._filter_placeholders(click_params_raw)
                            except (json.JSONDecodeError, TypeError) as e:
                                logger.warning(
                                    f"解析点击参数失败: conversion_id={conversion.id}, "
                                    f"conversion_id={conversion.conversion_id}, click_id={lookup_click_id}, error={str(e)}"
                                )
                    except Exception as e:
                        logger.debug(
                            f"查询点击参数失败: conversion_id={conversion.id}, "
                            f"conversion_id={conversion.conversion_id}, click_id={lookup_click_id}, error={str(e)}"
                        )
            except Exception as e:
                logger.debug(
                    f"获取点击参数失败: conversion_id={conversion.id}, "
                    f"conversion_id={conversion.conversion_id}, click_id={lookup_click_id}, error={str(e)}"
                )
        
        # 构建转发数据（包含原始点击参数）
        forward_data = PostbackForwarder._build_forward_data(conversion, click_params)
        
        # 5. 创建转发日志记录
        forward_log = PostbackForwardLog(
            conversion_id=conversion.id,
            product_id=None,  # 渠道转发不使用 product_id
            publisher_id=publisher.id,  # 记录渠道ID
            downstream_url=replaced_url,
            request_method=method,
            success=False,
            created_at=get_app_now_naive()
        )
        
        try:
            # 6. 根据请求方式发送请求
            if method == 'GET':
                # GET 请求：将数据作为 URL 参数
                # 注意：如果 URL 中已经有占位符被替换，可能已经包含参数
                # 这里我们仍然添加额外的参数，_forward_get 会合并参数
                request_params = forward_data
                forward_log.request_params = json.dumps(request_params, ensure_ascii=False)
                response = await PostbackForwarder._forward_get(replaced_url, request_params)
            else:
                # POST 请求：将数据作为 JSON body
                forward_log.request_data = json.dumps(forward_data, ensure_ascii=False)
                response = await PostbackForwarder._forward_post(replaced_url, forward_data)
            
            # 7. 记录响应
            forward_log.response_status = response.status_code
            forward_log.response_body = response.text[:2000]  # 限制响应内容长度
            forward_log.completed_at = get_app_now_naive()  # 使用北京时间
            
            # 检查响应是否表示成功（支持自定义检查配置）
            success_check_config = publisher.postback_success_check if publisher else None
            is_success, check_error = PostbackForwarder._check_response_success(
                response, success_check_config
            )
            forward_log.success = is_success
            
            # 如果 HTTP 状态码成功但内容检查失败，记录详细信息
            http_success = 200 <= response.status_code < 300
            if http_success and not is_success:
                error_msg = f"HTTP 状态码 {response.status_code} 表示成功，但响应内容检查失败: {check_error}"
                forward_log.error_message = error_msg
                logger.warning(
                    f"转发响应内容检查失败: conversion_id={conversion.id}, "
                    f"publisher_id={publisher.id}, status={response.status_code}, "
                    f"check_error={check_error}"
                )
            elif not http_success:
                forward_log.error_message = f"HTTP {response.status_code}: {response.text[:500]}"
            elif not is_success and check_error:
                forward_log.error_message = check_error
            
            # 更新通知记录状态
            notification_record.notification_status = 'sent' if forward_log.success else 'failed'
            if not forward_log.success:
                if not notification_record.error_message:
                    notification_record.error_message = forward_log.error_message or f"HTTP {response.status_code}: {response.text[:500]}"
            
            if forward_log.success:
                logger.info(
                    f"成功转发 postback 到渠道: conversion_id={conversion.id}, "
                    f"publisher_id={publisher.id}, url={replaced_url[:100]}, "
                    f"status={response.status_code}, "
                    f"method={method}, "
                    f"request_params={forward_log.request_params[:200] if forward_log.request_params else 'N/A'}, "
                    f"request_data={forward_log.request_data[:200] if forward_log.request_data else 'N/A'}, "
                    f"response_body={response.text[:500]}"
                )
                
                # 发送 Telegram 通知（异步，不阻塞）
                try:
                    asyncio.create_task(
                        PostbackForwarder._send_telegram_notification(
                            conversion=conversion,
                            publisher=publisher,
                            offer=offer,
                            replaced_url=replaced_url,
                            response_status=response.status_code,
                            success=True
                        )
                    )
                except Exception as e:
                    # Telegram 通知失败不影响主流程
                    logger.warning(f"创建 Telegram 通知任务失败: {str(e)}")
            else:
                logger.warning(
                    f"渠道 Postback 转发失败: conversion_id={conversion.id}, "
                    f"publisher_id={publisher.id}, url={replaced_url[:100]}, "
                    f"status={response.status_code}, "
                    f"method={method}, "
                    f"request_params={forward_log.request_params[:200] if forward_log.request_params else 'N/A'}, "
                    f"request_data={forward_log.request_data[:200] if forward_log.request_data else 'N/A'}, "
                    f"response_body={response.text[:500]}, "
                    f"error={forward_log.error_message or 'Unknown error'}"
                )
                if not forward_log.error_message:
                    forward_log.error_message = f"HTTP {response.status_code}: {response.text[:500]}"
                
                # 转发失败也发送 Telegram 通知
                try:
                    asyncio.create_task(
                        PostbackForwarder._send_telegram_notification(
                            conversion=conversion,
                            publisher=publisher,
                            offer=offer,
                            replaced_url=replaced_url,
                            response_status=response.status_code,
                            success=False,
                            error_message=forward_log.error_message
                        )
                    )
                except Exception as e:
                    logger.warning(f"创建 Telegram 通知任务失败: {str(e)}")
        
        except httpx.TimeoutException as e:
            forward_log.error_message = f"请求超时: {str(e)}"
            forward_log.completed_at = get_app_now_naive()  # 使用北京时间
            # 更新通知记录状态
            notification_record.notification_status = 'failed'
            notification_record.error_message = f"请求超时: {str(e)}"
            logger.error(
                f"转发 postback 到渠道超时: conversion_id={conversion.id}, "
                f"publisher_id={publisher.id}, url={replaced_url[:100]}"
            )
        except httpx.RequestError as e:
            forward_log.error_message = f"请求错误: {str(e)}"
            forward_log.completed_at = get_app_now_naive()  # 使用北京时间
            # 更新通知记录状态
            notification_record.notification_status = 'failed'
            notification_record.error_message = f"请求错误: {str(e)}"
            logger.error(
                f"转发 postback 到渠道失败: conversion_id={conversion.id}, "
                f"publisher_id={publisher.id}, url={replaced_url[:100]}, error={str(e)}"
            )
        except Exception as e:
            forward_log.error_message = f"未知错误: {str(e)}"
            forward_log.completed_at = get_app_now_naive()  # 使用北京时间
            # 更新通知记录状态
            notification_record.notification_status = 'failed'
            notification_record.error_message = f"未知错误: {str(e)}"
            logger.error(
                f"转发 postback 到渠道时发生异常: conversion_id={conversion.id}, "
                f"publisher_id={publisher.id}, url={replaced_url[:100]}, error={str(e)}",
                exc_info=True
            )
        finally:
            # 8. 保存转发日志和通知记录
            db.add(forward_log)
            try:
                await db.commit()
            except Exception as e:
                logger.error(f"保存转发日志和通知记录失败: {str(e)}", exc_info=True)
                await db.rollback()

    @staticmethod
    async def forward_to_downstream(
        conversion: PostbackConversion,
        product: Optional[Product],
        db: AsyncSession
    ) -> None:
        """
        将转化数据转发给下游系统
        
        Args:
            conversion: 转化记录
            product: 产品对象（如果提供了 product_id）
            db: 数据库会话
        """
        # 如果没有产品配置，或者产品没有配置下游 URL，则不转发
        if not product or not product.downstream_postback_url:
            return

        downstream_url = product.downstream_postback_url.strip()
        method = (product.downstream_postback_method or 'GET').upper()

        if method not in ['GET', 'POST']:
            logger.warning(f"产品 {product.id} 的下游转发方式无效: {method}，使用默认 GET")
            method = 'GET'

        # 获取原始点击参数（如果有 click_id）
        click_params = {}
        if conversion.click_id:
            try:
                click_result = await db.execute(
                    select(Click).where(Click.click_id == conversion.click_id)
                )
                click_record = click_result.scalars().first()
                if click_record and click_record.url_params:
                    try:
                        # 解析 JSON 格式的 url_params
                        click_params_raw = json.loads(click_record.url_params)
                        # 过滤掉占位符
                        click_params = PostbackForwarder._filter_placeholders(click_params_raw)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(
                            f"解析点击参数失败: conversion_id={conversion.id}, "
                            f"click_id={conversion.click_id}, error={str(e)}"
                        )
            except Exception as e:
                logger.debug(
                    f"获取点击参数失败: conversion_id={conversion.id}, "
                    f"click_id={conversion.click_id}, error={str(e)}"
                )

        # 构建转发数据（包含原始点击参数）
        forward_data = PostbackForwarder._build_forward_data(conversion, click_params)

        # 创建转发日志记录
        forward_log = PostbackForwardLog(
            conversion_id=conversion.id,
            product_id=product.id,
            downstream_url=downstream_url,
            request_method=method,
            success=False,
            created_at=get_app_now_naive()
        )

        try:
            # 根据请求方式构建请求参数
            if method == 'GET':
                # GET 请求：将数据作为 URL 参数
                request_params = forward_data
                forward_log.request_params = json.dumps(request_params, ensure_ascii=False)
                response = await PostbackForwarder._forward_get(downstream_url, request_params)
            else:
                # POST 请求：将数据作为 JSON body
                forward_log.request_data = json.dumps(forward_data, ensure_ascii=False)
                response = await PostbackForwarder._forward_post(downstream_url, forward_data)

            # 记录响应
            forward_log.response_status = response.status_code
            forward_log.response_body = response.text[:2000]  # 限制响应内容长度
            forward_log.completed_at = get_app_now_naive()  # 使用北京时间
            
            # 检查响应是否表示成功（支持自定义检查配置）
            success_check_config = product.downstream_postback_success_check if product else None
            is_success, check_error = PostbackForwarder._check_response_success(
                response, success_check_config
            )
            forward_log.success = is_success
            
            # 如果 HTTP 状态码成功但内容检查失败，记录详细信息
            http_success = 200 <= response.status_code < 300
            if http_success and not is_success:
                error_msg = f"HTTP 状态码 {response.status_code} 表示成功，但响应内容检查失败: {check_error}"
                forward_log.error_message = error_msg
                logger.warning(
                    f"下游转发响应内容检查失败: conversion_id={conversion.id}, "
                    f"product_id={product.id}, status={response.status_code}, "
                    f"check_error={check_error}"
                )
            elif not http_success:
                forward_log.error_message = f"HTTP {response.status_code}: {response.text[:500]}"
            elif not is_success and check_error:
                forward_log.error_message = check_error

            if forward_log.success:
                logger.info(
                    f"成功转发 postback 到下游: conversion_id={conversion.id}, "
                    f"product_id={product.id}, url={downstream_url}, "
                    f"status={response.status_code}, "
                    f"method={method}, "
                    f"request_params={forward_log.request_params[:200] if forward_log.request_params else 'N/A'}, "
                    f"request_data={forward_log.request_data[:200] if forward_log.request_data else 'N/A'}, "
                    f"response_body={response.text[:500]}"
                )
            else:
                logger.warning(
                    f"下游转发失败: conversion_id={conversion.id}, "
                    f"product_id={product.id}, url={downstream_url}, "
                    f"status={response.status_code}, "
                    f"method={method}, "
                    f"request_params={forward_log.request_params[:200] if forward_log.request_params else 'N/A'}, "
                    f"request_data={forward_log.request_data[:200] if forward_log.request_data else 'N/A'}, "
                    f"response_body={response.text[:500]}, "
                    f"error={forward_log.error_message or 'Unknown error'}"
                )
                if not forward_log.error_message:
                    forward_log.error_message = f"HTTP {response.status_code}: {response.text[:500]}"

        except httpx.TimeoutException as e:
            forward_log.error_message = f"请求超时: {str(e)}"
            forward_log.completed_at = get_app_now_naive()  # 使用北京时间
            logger.error(
                f"转发 postback 到下游超时: conversion_id={conversion.id}, "
                f"product_id={product.id}, url={downstream_url}"
            )
        except httpx.RequestError as e:
            forward_log.error_message = f"请求错误: {str(e)}"
            forward_log.completed_at = get_app_now_naive()  # 使用北京时间
            logger.error(
                f"转发 postback 到下游失败: conversion_id={conversion.id}, "
                f"product_id={product.id}, url={downstream_url}, error={str(e)}"
            )
        except Exception as e:
            forward_log.error_message = f"未知错误: {str(e)}"
            forward_log.completed_at = get_app_now_naive()  # 使用北京时间
            logger.error(
                f"转发 postback 到下游时发生异常: conversion_id={conversion.id}, "
                f"product_id={product.id}, url={downstream_url}, error={str(e)}",
                exc_info=True
            )
        finally:
            # 保存转发日志
            db.add(forward_log)
            try:
                await db.commit()
            except Exception as e:
                logger.error(f"保存转发日志失败: {str(e)}", exc_info=True)
                await db.rollback()

    @staticmethod
    def _build_forward_data(
        conversion: PostbackConversion,
        click_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        构建转发给下游的数据
        
        将转化记录转换为字典格式，用于转发给下游系统
        注意：payout 字段使用扣后的 payout（PO(扣)），这是给下游的实际金额
        
        Args:
            conversion: 转化记录
            click_params: 原始点击参数（已过滤占位符），可选
        """
        data = {
            "conversion_id": conversion.conversion_id,
            "platform": conversion.platform,
            "event_name": conversion.event_name,
        }

        # 添加可选字段（如果存在）
        if conversion.event_value is not None:
            data["event_value"] = conversion.event_value
        
        # payout 字段使用扣后的 payout（给下游的实际金额）
        if conversion.payout is not None:
            data["payout"] = conversion.payout
        elif conversion.original_payout is not None:
            # 如果没有扣后的 payout，使用原始的 payout
            data["payout"] = conversion.original_payout
        
        # original_payout 作为参考字段（可选）
        if conversion.original_payout is not None:
            data["original_payout"] = conversion.original_payout
        if conversion.devad_id:
            data["devad_id"] = conversion.devad_id
        if conversion.os:
            data["os"] = conversion.os
        if conversion.carrier:
            data["carrier"] = conversion.carrier
        if conversion.ip:
            data["ip"] = conversion.ip
        if conversion.gid:
            data["gid"] = conversion.gid
        if conversion.product_id:
            data["product_id"] = conversion.product_id
        if conversion.client_id:
            data["client_id"] = conversion.client_id

        # 添加时间戳
        if conversion.created_at:
            data["timestamp"] = conversion.created_at.isoformat()

        # 合并原始点击参数（如果有）
        # 注意：如果转化数据中的字段与点击参数冲突，转化数据的字段优先
        if click_params:
            for key, value in click_params.items():
                # 只添加转化数据中不存在的字段，避免覆盖转化数据
                if key not in data and value is not None:
                    # 处理列表值（parse_qs 可能返回列表）
                    if isinstance(value, list):
                        # 如果列表只有一个元素，取第一个；否则保持列表
                        data[key] = value[0] if len(value) == 1 else value
                    else:
                        data[key] = value
        
        # 特别处理：如果click_params中有click_id（渠道提供的），确保添加到转发数据中
        # 注意：这里的click_id是渠道提供的原始click_id，不是系统生成的click_id
        if click_params and 'click_id' in click_params:
            click_id_value = click_params['click_id']
            if isinstance(click_id_value, list):
                click_id_value = click_id_value[0] if click_id_value else None
            if click_id_value:
                # 如果转化数据中没有click_id字段，或者转化数据中的click_id是系统生成的
                # 则使用渠道提供的click_id
                if 'click_id' not in data or data.get('click_id') == conversion.click_id:
                    data['click_id'] = click_id_value
        
        # 特别处理：如果click_params中有sub_channel_id，确保添加到转发数据中
        if click_params and 'sub_channel_id' in click_params:
            sub_channel_id_value = click_params['sub_channel_id']
            if isinstance(sub_channel_id_value, list):
                sub_channel_id_value = sub_channel_id_value[0] if sub_channel_id_value else None
            if sub_channel_id_value:
                data['sub_channel_id'] = sub_channel_id_value

        return data

    @staticmethod
    def _check_response_success(
        response: httpx.Response,
        success_check_config: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        检查响应是否表示成功
        
        支持三种检查方式：
        1. HTTP 状态码检查：检查 HTTP 响应状态码（默认方式）
        2. JSON 检查：检查响应 JSON 中的特定字段和值
        3. 关键词检查：检查响应文本中是否包含成功/失败关键词
        
        配置格式（JSON）：
        {
            "type": "status_code" | "json" | "keyword",
            "success_status_codes": [200, 201, 202],  // HTTP 状态码检查：成功状态码列表（默认 [200-299]）
            "json_path": "status",  // JSON 检查：字段路径（支持点号分隔，如 "data.status"）
            "json_value": "ok",     // JSON 检查：期望的值（如果字段值等于此值，表示成功）
            "success_keywords": ["success", "ok", "200"],  // 关键词检查：成功关键词列表
            "failure_keywords": ["error", "fail", "failed"],  // 关键词检查：失败关键词列表
            "exact_match": false  // 关键词检查：是否精确匹配（默认false，即包含匹配）。如果为true，响应文本去除首尾空白后必须完全等于关键词才匹配
        }
        
        示例：
        1. 只使用 HTTP 状态码检查（默认，200-299 为成功）：
           不填写配置，或填写：{"type": "status_code"}
           说明：默认 200-299 状态码为成功
        
        2. 自定义 HTTP 状态码检查（只接受 200 和 201）：
           {"type": "status_code", "success_status_codes": [200, 201]}
           说明：只有状态码为 200 或 201 时才认为成功
        
        3. 如果下游只返回 "OK"、"ok" 或 "Ok"（精确匹配，不区分大小写），配置：
           {"type": "keyword", "success_keywords": ["OK"], "exact_match": true}
           说明：精确匹配时，响应文本去除首尾空白后必须完全等于关键词（不区分大小写）
           例如："OK"、"ok"、"  OK  "、"Ok\n" 都会匹配，但 "OK success" 不会匹配
        
        4. 如果下游返回包含 "success" 的文本（包含匹配，不区分大小写），配置：
           {"type": "keyword", "success_keywords": ["success"]}
           说明：包含匹配时，响应文本中只要包含关键词（不区分大小写）就匹配
           例如："success"、"SUCCESS"、"Response: success" 都会匹配
        
        5. 如果下游返回 "OK" 或包含 "OK" 的文本（包含匹配，不区分大小写），配置：
           {"type": "keyword", "success_keywords": ["OK"]}
           说明：默认包含匹配，不区分大小写
           例如："OK"、"ok"、"Response: OK"、"ok success" 都会匹配
        
        Args:
            response: HTTP 响应对象
            success_check_config: 成功检查配置（JSON 字符串）
            
        Returns:
            (是否成功, 错误信息)
        """
        # 如果没有配置，默认使用 HTTP 状态码判断（200-299 为成功）
        if not success_check_config or not success_check_config.strip():
            return (200 <= response.status_code < 300, None)
        
        try:
            config = json.loads(success_check_config)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"解析成功检查配置失败: {str(e)}, 使用默认 HTTP 状态码判断")
            return (200 <= response.status_code < 300, None)
        
        check_type = config.get("type", "status_code")  # 默认使用状态码检查
        response_text = response.text
        
        # HTTP 状态码检查
        if check_type == "status_code":
            success_status_codes = config.get("success_status_codes", [])
            
            if not success_status_codes:
                # 如果没有配置，默认使用 200-299 范围
                return (200 <= response.status_code < 300, None)
            
            # 检查状态码是否在成功列表中
            is_success = response.status_code in success_status_codes
            if not is_success:
                return (False, f"HTTP 状态码 {response.status_code} 不在成功状态码列表中: {success_status_codes}")
            return (True, None)
        
        # JSON 检查
        if check_type == "json":
            json_path = config.get("json_path")
            json_value = config.get("json_value")
            
            if not json_path:
                logger.warning("JSON 检查配置缺少 json_path，使用默认 HTTP 状态码判断")
                return (200 <= response.status_code < 300, None)
            
            try:
                response_json = response.json()
            except (json.JSONDecodeError, ValueError):
                # 响应不是 JSON，使用 HTTP 状态码判断
                logger.debug(f"响应不是 JSON 格式，使用 HTTP 状态码判断: status={response.status_code}")
                return (200 <= response.status_code < 300, None)
            
            # 支持点号分隔的路径（如 "data.status"）
            path_parts = json_path.split(".")
            current_value = response_json
            for part in path_parts:
                if isinstance(current_value, dict):
                    current_value = current_value.get(part)
                else:
                    logger.debug(f"JSON 路径 {json_path} 无法访问，使用 HTTP 状态码判断")
                    return (200 <= response.status_code < 300, None)
            
            # 如果配置了期望值，检查是否匹配
            if json_value is not None:
                is_success = str(current_value) == str(json_value)
                if not is_success:
                    return (False, f"JSON 字段 {json_path} 的值 '{current_value}' 不等于期望值 '{json_value}'")
                return (True, None)
            else:
                # 如果没有配置期望值，只要字段存在且不为空/False/None，就认为成功
                is_success = current_value is not None and current_value != False and current_value != ""
                if not is_success:
                    return (False, f"JSON 字段 {json_path} 的值 '{current_value}' 表示失败")
                return (True, None)
        
        # 关键词检查
        elif check_type == "keyword":
            success_keywords = config.get("success_keywords", [])
            failure_keywords = config.get("failure_keywords", [])
            exact_match = config.get("exact_match", False)  # 是否精确匹配（默认false，即包含匹配）
            
            if not success_keywords and not failure_keywords:
                logger.warning("关键词检查配置缺少关键词列表，使用默认 HTTP 状态码判断")
                return (200 <= response.status_code < 300, None)
            
            # 先检查失败关键词（优先级更高）
            for keyword in failure_keywords:
                if exact_match:
                    # 精确匹配：去除首尾空白后比较，不区分大小写
                    if response_text.strip().lower() == keyword.strip().lower():
                        return (False, f"响应精确匹配失败关键词: {keyword}")
                else:
                    # 包含匹配：不区分大小写
                    if keyword.lower() in response_text.lower():
                        return (False, f"响应中包含失败关键词: {keyword}")
            
            # 检查成功关键词
            if success_keywords:
                found_success = False
                matched_keyword = None
                for keyword in success_keywords:
                    if exact_match:
                        # 精确匹配：去除首尾空白后比较，不区分大小写
                        if response_text.strip().lower() == keyword.strip().lower():
                            found_success = True
                            matched_keyword = keyword
                            break
                    else:
                        # 包含匹配：不区分大小写
                        if keyword.lower() in response_text.lower():
                            found_success = True
                            matched_keyword = keyword
                            break
                
                if not found_success:
                    match_type = "精确匹配" if exact_match else "包含匹配"
                    return (False, f"响应中未找到任何成功关键词（{match_type}）: {success_keywords}")
            
            return (True, None)
        
        else:
            logger.warning(f"未知的检查类型: {check_type}，使用默认 HTTP 状态码判断")
            return (200 <= response.status_code < 300, None)
    
    @staticmethod
    def _filter_placeholders(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        过滤掉包含占位符的参数
        
        占位符格式：{变量名}，例如 {click_id}, {offer_id}, {channel_id} 等
        
        Args:
            params: 原始参数字典
            
        Returns:
            过滤后的参数字典（不包含占位符）
        """
        if not params:
            return {}
        
        # 占位符正则表达式：匹配 {变量名} 格式
        placeholder_pattern = r'\{[a-zA-Z_][a-zA-Z0-9_]*\}'
        
        filtered_params = {}
        for key, value in params.items():
            # 处理列表值（parse_qs 可能返回列表）
            if isinstance(value, list):
                # 检查列表中是否有值包含占位符
                filtered_values = []
                for v in value:
                    v_str = str(v) if v is not None else ''
                    # 如果值不包含占位符，则保留
                    if not re.search(placeholder_pattern, v_str):
                        filtered_values.append(v)
                # 如果有过滤后的值，则添加
                if filtered_values:
                    filtered_params[key] = filtered_values if len(filtered_values) > 1 else filtered_values[0]
            else:
                # 检查单个值是否包含占位符
                value_str = str(value) if value is not None else ''
                if not re.search(placeholder_pattern, value_str):
                    filtered_params[key] = value
        
        return filtered_params

    @staticmethod
    async def _forward_get(url: str, params: Dict[str, Any]) -> httpx.Response:
        """
        使用 GET 方式转发数据
        
        Args:
            url: 下游 URL
            params: 请求参数字典
            
        Returns:
            HTTP 响应对象
        """
        # 解析 URL，合并参数
        parsed = urlparse(url)
        existing_params = parse_qs(parsed.query)
        
        # 将新参数添加到现有参数中
        for key, value in params.items():
            if value is not None:
                existing_params[key] = [str(value)]
        
        # 重建 URL
        new_query = urlencode(existing_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        final_url = urlunparse(new_parsed)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(final_url)
            return response

    @staticmethod
    async def _forward_post(url: str, data: Dict[str, Any]) -> httpx.Response:
        """
        使用 POST 方式转发数据
        
        Args:
            url: 下游 URL
            data: 请求体数据（JSON）
            
        Returns:
            HTTP 响应对象
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                json=data,
                headers={"Content-Type": "application/json"}
            )
            return response

    @staticmethod
    async def _replace_url_placeholders(
        url: str,
        conversion: PostbackConversion,
        click: Optional[Click],
        offer: Optional[Offer],
        publisher: Optional[Publisher],
        advertiser: Optional[Advertiser],
        db: AsyncSession
    ) -> str:
        """
        替换 URL 中的占位符
        
        支持的占位符格式：{变量名}
        例如：{click_id}, {original_payout}, {payout}, {offer_id} 等
        
        Args:
            url: 包含占位符的 URL
            conversion: 转化记录
            click: 点击记录（可选）
            offer: Offer 记录（可选）
            publisher: Publisher 记录（可选）
            advertiser: Advertiser 记录（可选）
            db: 数据库会话
            
        Returns:
            替换后的 URL
        """
        # 使用正则表达式查找所有占位符
        pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
        placeholders = re.findall(pattern, url)
        
        if not placeholders:
            # 没有占位符，直接返回原 URL
            return url
        
        # 构建参数值字典
        values = {}
        
        # 1. PostbackConversion 直接字段
        if conversion:
            values['conversion_id'] = conversion.conversion_id
            values['platform'] = conversion.platform
            values['event_name'] = conversion.event_name if conversion.event_name else ''
            values['event_value'] = str(conversion.event_value) if conversion.event_value is not None else ''
            # payout 使用扣后的 payout（给下游的实际金额）
            if conversion.payout is not None:
                values['payout'] = str(conversion.payout)
            elif conversion.original_payout is not None:
                # 如果没有扣后的 payout，使用原始的 payout
                values['payout'] = str(conversion.original_payout)
            else:
                values['payout'] = ''
            # original_payout 作为参考字段
            values['original_payout'] = str(conversion.original_payout) if conversion.original_payout is not None else ''
            values['devad_id'] = conversion.devad_id if conversion.devad_id else ''
            values['os'] = conversion.os if conversion.os else ''
            values['carrier'] = conversion.carrier if conversion.carrier else ''
            values['ip'] = conversion.ip if conversion.ip else ''
            values['gid'] = conversion.gid if conversion.gid else ''
            values['product_id'] = str(conversion.product_id) if conversion.product_id else ''
            values['client_id'] = str(conversion.client_id) if conversion.client_id else ''
            values['click_id'] = conversion.click_id if conversion.click_id else ''
            values['click_time'] = conversion.click_time.isoformat() if conversion.click_time else ''
            values['conversion_status'] = conversion.conversion_status if conversion.conversion_status else ''
            values['timestamp'] = conversion.created_at.isoformat() if conversion.created_at else ''
            values['created_at'] = conversion.created_at.isoformat() if conversion.created_at else ''
        
        # 2. Click 关联字段
        if click:
            values['click_offer_id'] = str(click.offer_id) if click.offer_id else ''
            values['click_publisher_id'] = str(click.publisher_id) if click.publisher_id else ''
            values['click_advertiser_id'] = str(click.advertiser_id) if click.advertiser_id else ''
            values['click_ip'] = click.ip if click.ip else ''
            values['click_device'] = click.device if click.device else ''
            values['click_country'] = click.country if click.country else ''
            values['click_user_agent'] = click.user_agent if click.user_agent else ''
            values['click_referer'] = click.referer if click.referer else ''
        
        # 3. Offer 关联字段
        if offer:
            values['offer_id'] = str(offer.id) if offer.id else ''
            values['offer_name'] = offer.offer_name if offer.offer_name else ''
            values['advertiser_offer_id'] = offer.advertiser_offer_id if offer.advertiser_offer_id else ''
            values['offer_advertiser_id'] = str(offer.advertiser_id) if offer.advertiser_id else ''
            values['offer_payout'] = str(offer.payout) if offer.payout is not None else ''
            values['affiliate_payout'] = str(offer.affiliate_payout) if offer.affiliate_payout is not None else ''
            values['offer_country'] = offer.country if offer.country else ''
            values['offer_category'] = offer.category if offer.category else ''
            values['offer_type'] = offer.type if offer.type else ''
            values['offer_status'] = offer.status if offer.status else ''
        
        # 4. Publisher 关联字段
        if publisher:
            values['publisher_id'] = str(publisher.id) if publisher.id else ''
            values['channel_id'] = str(publisher.id) if publisher.id else ''  # 别名
            values['publisher_name'] = publisher.publisher_name if publisher.publisher_name else ''
            values['publisher_email'] = publisher.email if publisher.email else ''
        
        # 5. Advertiser 关联字段
        if advertiser:
            values['advertiser_id'] = str(advertiser.id) if advertiser.id else ''
            values['advertiser_name'] = advertiser.advertiser_name if advertiser.advertiser_name else ''
            values['advertiser_email'] = advertiser.email if advertiser.email else ''
        
        # 6. 支持别名（转换为小写加下划线格式）
        alias_map = {
            'clickid': 'click_id',
            'clickId': 'click_id',
            'clk_id': 'click_id',
            'cid': 'click_id',
            'conversionId': 'conversion_id',
            'conv_id': 'conversion_id',
            'publisherId': 'publisher_id',
            'channelId': 'channel_id',
            'offerId': 'offer_id',
            'eventName': 'event_name',
            'eventId': 'event_name',
            'event_id': 'event_name',
        }
        
        # 替换占位符
        result_url = url
        for placeholder in placeholders:
            # 转换为小写加下划线格式
            normalized_key = placeholder.lower()
            if normalized_key in alias_map:
                normalized_key = alias_map[normalized_key]
            else:
                # 将驼峰命名转换为下划线命名
                normalized_key = re.sub(r'(?<!^)(?=[A-Z])', '_', placeholder).lower()
            
            # 获取值
            value = values.get(normalized_key, '')
            
            # 如果值为空，保持占位符不变（或者可以替换为空字符串）
            if not value:
                logger.debug(
                    f"占位符 {{{placeholder}}} 对应的值为空，保持占位符不变: url={url[:100]}"
                )
                continue
            
            # URL 编码值（保留 URL 中常用的安全字符，如 : / ? = & 等）
            # 注意：这里只编码值本身，不编码整个 URL
            # 如果值已经是一个完整的 URL 或包含特殊字符，需要编码
            if isinstance(value, str):
                # 对于字符串值，进行 URL 编码（保留一些安全字符）
                encoded_value = quote(value, safe='')
            else:
                # 对于非字符串值，先转换为字符串再编码
                encoded_value = quote(str(value), safe='')
            
            # 替换占位符（使用原始占位符名称，支持大小写敏感）
            result_url = result_url.replace(f'{{{placeholder}}}', encoded_value)
        
        return result_url

    @staticmethod
    def _build_forward_notification_message(
        conversion: PostbackConversion,
        publisher: Publisher,
        offer: Optional[Offer],
        has_postback_url: bool
    ) -> str:
        """
        构建转发通知消息
        
        Args:
            conversion: 转化记录
            publisher: 渠道对象
            offer: Offer 对象（可选）
            has_postback_url: 是否有 postback_url
            
        Returns:
            通知消息文本
        """
        msg = "📤 Postback 转发通知\n\n"
        msg += f"转化ID: {conversion.conversion_id}\n"
        msg += f"平台: {conversion.platform}\n"
        
        if conversion.event_name:
            msg += f"事件: {conversion.event_name}\n"
        
        if conversion.original_payout is not None:
            msg += f"原始金额 (PO): ${conversion.original_payout:.2f}\n"
        if conversion.payout is not None:
            msg += f"扣后金额 (PO(扣)): ${conversion.payout:.2f}\n"
        
        # 渠道信息
        msg += f"\n渠道信息:\n"
        msg += f"• 渠道ID: {publisher.id}\n"
        msg += f"• 渠道名称: {publisher.publisher_name}\n"
        
        # Offer 信息
        if offer:
            msg += f"\nOffer 信息:\n"
            msg += f"• Offer ID: {offer.id}\n"
            msg += f"• Offer 名称: {offer.offer_name}\n"
        
        # Postback URL 信息
        msg += f"\n转发配置:\n"
        if has_postback_url:
            url_display = publisher.postback_url[:150] + "..." if len(publisher.postback_url) > 150 else publisher.postback_url
            msg += f"• Postback URL: {url_display}\n"
            msg += f"• 请求方式: {publisher.postback_method or 'GET'}\n"
            msg += f"• 通知模式: 自动通知\n"
        else:
            msg += f"• Postback URL: 未配置\n"
            msg += f"• 通知模式: 手动通知\n"
        
        # 时间戳
        if conversion.created_at:
            time_str = conversion.created_at.strftime("%Y-%m-%d %H:%M:%S")
            msg += f"\n时间: {time_str}\n"
        
        return msg
    
    @staticmethod
    async def _send_telegram_notification(
        conversion: PostbackConversion,
        publisher: Publisher,
        offer: Optional[Offer],
        replaced_url: str,
        response_status: int,
        success: bool,
        error_message: Optional[str] = None
    ) -> None:
        """
        发送 Telegram 通知（转发结果）
        
        Args:
            conversion: 转化记录
            publisher: 渠道对象
            offer: Offer 对象（可选）
            replaced_url: 替换后的 URL
            response_status: HTTP 响应状态码
            success: 是否成功
            error_message: 错误信息（如果失败）
        """
        try:
            from app.core.auto_bot import send_telegram_message
            
            # 构建通知消息
            if success:
                msg = "✅ Postback 转发成功\n\n"
            else:
                msg = "❌ Postback 转发失败\n\n"
            
            # 基础信息
            msg += f"转化ID: {conversion.conversion_id}\n"
            msg += f"平台: {conversion.platform}\n"
            
            if conversion.event_name:
                msg += f"事件: {conversion.event_name}\n"
            
            if conversion.original_payout is not None:
                msg += f"原始金额 (PO): ${conversion.original_payout:.2f}\n"
            if conversion.payout is not None:
                msg += f"扣后金额 (PO(扣)): ${conversion.payout:.2f}\n"
            
            # 渠道信息
            msg += f"\n渠道信息:\n"
            msg += f"• 渠道ID: {publisher.id}\n"
            msg += f"• 渠道名称: {publisher.publisher_name}\n"
            
            # Offer 信息
            if offer:
                msg += f"\nOffer 信息:\n"
                msg += f"• Offer ID: {offer.id}\n"
                msg += f"• Offer 名称: {offer.offer_name}\n"
            
            # 转发信息
            msg += f"\n转发信息:\n"
            msg += f"• 请求方式: {publisher.postback_method or 'GET'}\n"
            msg += f"• 响应状态: {response_status}\n"
            
            # URL（截断，避免消息过长）
            url_display = replaced_url[:150] + "..." if len(replaced_url) > 150 else replaced_url
            msg += f"• URL: {url_display}\n"
            
            # 错误信息（如果失败）
            if not success and error_message:
                error_display = error_message[:200] + "..." if len(error_message) > 200 else error_message
                msg += f"\n错误信息:\n{error_display}\n"
            
            # 时间戳
            if conversion.created_at:
                time_str = conversion.created_at.strftime("%Y-%m-%d %H:%M:%S")
                msg += f"\n时间: {time_str}\n"
            
            # 发送 Telegram 消息（异步函数，直接 await）
            await send_telegram_message(msg)
            
        except ImportError:
            logger.debug("Telegram Bot 模块未导入，跳过通知")
        except Exception as e:
            logger.warning(f"构建或发送 Telegram 通知时出错: {str(e)}")

