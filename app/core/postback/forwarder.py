"""
Postback 下游转发服务
负责将接收到的 postback 数据转发给下游系统
"""
import json
import logging
import asyncio
import re
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse, quote

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.models.models import (
    Product, PostbackConversion, PostbackForwardLog,
    Click, Offer, Publisher, Advertiser
)

logger = logging.getLogger(__name__)


class PostbackForwarder:
    """Postback 下游转发器"""

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
        publisher = None
        click_record = None
        offer = None
        advertiser = None
        
        if conversion.click_id:
            # 查询 Click 记录及其关联的 Publisher、Offer、Advertiser
            click_result = await db.execute(
                select(Click)
                .options(
                    joinedload(Click.publisher),
                    joinedload(Click.offer).joinedload(Offer.advertiser)
                )
                .where(Click.click_id == conversion.click_id)
            )
            click_record = click_result.scalars().first()
            
            if click_record:
                publisher = click_record.publisher
                offer = click_record.offer
                if offer:
                    advertiser = offer.advertiser
        
        # 2. 如果没有找到 Publisher 或 Publisher 没有配置 Postback URL，则不转发
        if not publisher or not publisher.postback_url:
            if not publisher:
                logger.debug(
                    f"未找到关联的渠道，跳过转发: conversion_id={conversion.id}, "
                    f"click_id={conversion.click_id}"
                )
            else:
                logger.debug(
                    f"渠道未配置 Postback URL，跳过转发: conversion_id={conversion.id}, "
                    f"publisher_id={publisher.id}"
                )
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
        
        # 4. 构建转发数据
        forward_data = PostbackForwarder._build_forward_data(conversion)
        
        # 5. 创建转发日志记录
        forward_log = PostbackForwardLog(
            conversion_id=conversion.id,
            product_id=None,  # 渠道转发不使用 product_id
            downstream_url=replaced_url,
            request_method=method,
            success=False,
            created_at=datetime.now(timezone.utc)
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
            forward_log.success = 200 <= response.status_code < 300
            forward_log.completed_at = datetime.now(timezone.utc)
            
            if forward_log.success:
                logger.info(
                    f"成功转发 postback 到渠道: conversion_id={conversion.id}, "
                    f"publisher_id={publisher.id}, url={replaced_url[:100]}, status={response.status_code}"
                )
            else:
                logger.warning(
                    f"渠道 Postback 返回非成功状态: conversion_id={conversion.id}, "
                    f"publisher_id={publisher.id}, url={replaced_url[:100]}, status={response.status_code}"
                )
                forward_log.error_message = f"HTTP {response.status_code}: {response.text[:500]}"
        
        except httpx.TimeoutException as e:
            forward_log.error_message = f"请求超时: {str(e)}"
            forward_log.completed_at = datetime.now(timezone.utc)
            logger.error(
                f"转发 postback 到渠道超时: conversion_id={conversion.id}, "
                f"publisher_id={publisher.id}, url={replaced_url[:100]}"
            )
        except httpx.RequestError as e:
            forward_log.error_message = f"请求错误: {str(e)}"
            forward_log.completed_at = datetime.now(timezone.utc)
            logger.error(
                f"转发 postback 到渠道失败: conversion_id={conversion.id}, "
                f"publisher_id={publisher.id}, url={replaced_url[:100]}, error={str(e)}"
            )
        except Exception as e:
            forward_log.error_message = f"未知错误: {str(e)}"
            forward_log.completed_at = datetime.now(timezone.utc)
            logger.error(
                f"转发 postback 到渠道时发生异常: conversion_id={conversion.id}, "
                f"publisher_id={publisher.id}, url={replaced_url[:100]}, error={str(e)}",
                exc_info=True
            )
        finally:
            # 8. 保存转发日志
            db.add(forward_log)
            try:
                await db.commit()
            except Exception as e:
                logger.error(f"保存转发日志失败: {str(e)}", exc_info=True)
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

        # 构建转发数据
        forward_data = PostbackForwarder._build_forward_data(conversion)

        # 创建转发日志记录
        forward_log = PostbackForwardLog(
            conversion_id=conversion.id,
            product_id=product.id,
            downstream_url=downstream_url,
            request_method=method,
            success=False,
            created_at=datetime.now(timezone.utc)
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
            forward_log.success = 200 <= response.status_code < 300
            forward_log.completed_at = datetime.now(timezone.utc)

            if forward_log.success:
                logger.info(
                    f"成功转发 postback 到下游: conversion_id={conversion.id}, "
                    f"product_id={product.id}, url={downstream_url}, status={response.status_code}"
                )
            else:
                logger.warning(
                    f"下游转发返回非成功状态: conversion_id={conversion.id}, "
                    f"product_id={product.id}, url={downstream_url}, status={response.status_code}"
                )
                forward_log.error_message = f"HTTP {response.status_code}: {response.text[:500]}"

        except httpx.TimeoutException as e:
            forward_log.error_message = f"请求超时: {str(e)}"
            forward_log.completed_at = datetime.now(timezone.utc)
            logger.error(
                f"转发 postback 到下游超时: conversion_id={conversion.id}, "
                f"product_id={product.id}, url={downstream_url}"
            )
        except httpx.RequestError as e:
            forward_log.error_message = f"请求错误: {str(e)}"
            forward_log.completed_at = datetime.now(timezone.utc)
            logger.error(
                f"转发 postback 到下游失败: conversion_id={conversion.id}, "
                f"product_id={product.id}, url={downstream_url}, error={str(e)}"
            )
        except Exception as e:
            forward_log.error_message = f"未知错误: {str(e)}"
            forward_log.completed_at = datetime.now(timezone.utc)
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
    def _build_forward_data(conversion: PostbackConversion) -> Dict[str, Any]:
        """
        构建转发给下游的数据
        
        将转化记录转换为字典格式，用于转发给下游系统
        """
        data = {
            "conversion_id": conversion.conversion_id,
            "platform": conversion.platform,
            "event_name": conversion.event_name,
        }

        # 添加可选字段（如果存在）
        if conversion.event_value is not None:
            data["event_value"] = conversion.event_value
        if conversion.payout is not None:
            data["payout"] = conversion.payout
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

        return data

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
        例如：{click_id}, {payout}, {offer_id} 等
        
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
            values['payout'] = str(conversion.payout) if conversion.payout is not None else ''
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

