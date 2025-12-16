"""
Postback 统一处理器
负责接收、验证、处理和存储 postback 数据
"""
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.postback.handlers import get_handler
from app.models.models import PostbackConversion
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode

logger = logging.getLogger(__name__)


class PostbackProcessor:
    """Postback 统一处理器"""
    
    @staticmethod
    async def process(
        platform: str,
        raw_data: Dict[str, Any],
        db: AsyncSession,
        request_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        处理 postback 回调
        
        Args:
            platform: 平台名称
            raw_data: 原始请求数据
            db: 数据库会话
            request_ip: 请求IP地址
            
        Returns:
            处理结果字典，包含：
            - success: 是否成功
            - message: 响应消息
            - conversion_id: 转化ID
        """
        # 1. 获取平台处理器
        handler = get_handler(platform)
        if not handler:
            logger.warning(f"未找到平台 {platform} 的处理器")
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                detail=f"不支持的平台: {platform}"
            )
        
        try:
            # 2. 验证数据
            is_valid, error_msg = await handler.validate(raw_data)
            if not is_valid:
                logger.warning(f"平台 {platform} postback 数据验证失败: {error_msg}")
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=error_msg or "数据验证失败"
                )
            
            # 3. 标准化数据
            normalized_data = await handler.normalize(raw_data)
            conversion_id = normalized_data.get("conversion_id")
            
            if not conversion_id:
                logger.warning(f"平台 {platform} postback 数据缺少 conversion_id")
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="缺少必填字段: conversion_id"
                )
            
            # 4. 验证产品和客户（如果提供）
            product_id = normalized_data.get("product_id")
            client_id = normalized_data.get("client_id")
            is_valid, error_msg = await handler.validate_product_client(
                product_id, client_id, db
            )
            if not is_valid:
                logger.warning(f"平台 {platform} postback 产品和客户验证失败: {error_msg}")
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=error_msg or "产品和客户验证失败"
                )
            
            # 5. 检查是否已存在（防重复处理）
            event_name = normalized_data.get("event_name")
            existing = await db.execute(
                select(PostbackConversion).where(
                    PostbackConversion.platform == platform,
                    PostbackConversion.conversion_id == conversion_id,
                    PostbackConversion.event_name == event_name
                )
            )
            existing_record = existing.scalars().first()
            
            if existing_record:
                logger.info(
                    f"平台 {platform} postback 转化已存在，跳过重复处理: "
                    f"conversion_id={conversion_id}, event_name={event_name}"
                )
                return {
                    "success": True,
                    "message": "PostBack 接收成功（已存在，跳过重复处理）",
                    "conversion_id": conversion_id,
                    "platform": platform
                }
            
            # 6. 保存原始数据（JSON格式）
            raw_data_json = json.dumps(raw_data, ensure_ascii=False)
            
            # 7. 如果提供了IP，添加到标准化数据中
            if request_ip and not normalized_data.get("ip"):
                normalized_data["ip"] = request_ip
            
            # 8. 创建转化记录
            conversion = PostbackConversion(
                platform=platform,
                conversion_id=conversion_id,
                event_name=normalized_data.get("event_name"),
                event_value=normalized_data.get("event_value"),
                payout=normalized_data.get("payout"),
                devad_id=normalized_data.get("devad_id"),
                os=normalized_data.get("os"),
                carrier=normalized_data.get("carrier"),
                ip=normalized_data.get("ip"),
                gid=normalized_data.get("gid"),
                product_id=product_id,
                client_id=client_id,
                raw_data=raw_data_json,
                created_at=datetime.now(timezone.utc)
            )
            
            db.add(conversion)
            await db.commit()
            await db.refresh(conversion)
            
            logger.info(
                f"平台 {platform} postback 转化记录已保存: "
                f"conversion_id={conversion_id}, event_name={event_name}, "
                f"payout={normalized_data.get('payout')}, "
                f"product_id={product_id}, client_id={client_id}"
            )
            
            # 9. 返回成功响应
            return {
                "success": True,
                "message": "PostBack 接收成功",
                "conversion_id": conversion_id,
                "platform": platform
            }
            
        except Exception as e:
            await db.rollback()
            logger.error(
                f"处理平台 {platform} postback 时发生错误: {str(e)}",
                exc_info=True
            )
            # 如果是 API 异常，直接抛出
            if hasattr(e, 'status_code'):
                raise
            # 否则包装为通用错误
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"处理 PostBack 回调失败：{str(e)}"
            )

