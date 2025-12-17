"""
Postback 下游转发服务
负责将接收到的 postback 数据转发给下游系统
"""
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import Product, PostbackConversion, PostbackForwardLog

logger = logging.getLogger(__name__)


class PostbackForwarder:
    """Postback 下游转发器"""

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

