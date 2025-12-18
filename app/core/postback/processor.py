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
from app.core.postback.forwarder import PostbackForwarder
from app.core.postback.notifier import PostbackNotifier
from app.models.models import PostbackConversion, Product, Click, Offer
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.cap import check_cap, increment_cap_count
from app.core.discount import calculate_discount

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
            
            # 7.5. CPL 系统：尝试关联 Click ID 和进行 Cap/扣量检查
            click_id = None
            click_time = None
            offer_id = None
            publisher_id = None
            advertiser_id = None
            final_payout = normalized_data.get("payout")
            discount_info = None
            
            # 尝试从 raw_data 中提取 click_id（可能是 our_click_id 或其他字段）
            click_id = (raw_data.get("our_click_id") or 
                       raw_data.get("click_id") or 
                       normalized_data.get("click_id"))
            
            if click_id:
                # 查找 Click 记录
                click_result = await db.execute(
                    select(Click).where(Click.click_id == click_id)
                )
                click_record = click_result.scalars().first()
                
                if click_record:
                    click_time = click_record.click_time
                    offer_id = click_record.offer_id
                    publisher_id = click_record.publisher_id
                    advertiser_id = click_record.advertiser_id
                    
                    # 检查 Cap 限制
                    if offer_id:
                        is_allowed, cap_reason = await check_cap(
                            db=db,
                            offer_id=offer_id,
                            publisher_id=publisher_id,
                            advertiser_id=advertiser_id
                        )
                        
                        if not is_allowed:
                            logger.warning(
                                f"转化被Cap限制拒绝: conversion_id={conversion_id}, "
                                f"offer_id={offer_id}, reason={cap_reason}"
                            )
                            # 可以选择拒绝转化或标记为特殊状态
                            # 这里我们仍然保存转化，但标记状态
                            # 也可以选择直接拒绝：raise_api_exception(...)
                    
                    # 计算扣量
                    if offer_id and publisher_id and final_payout:
                        final_payout, discount_amount, discount_info = await calculate_discount(
                            db=db,
                            offer_id=offer_id,
                            publisher_id=publisher_id,
                            original_payout=final_payout
                        )
                        if discount_info:
                            logger.info(
                                f"应用扣量: conversion_id={conversion_id}, "
                                f"original={normalized_data.get('payout')}, "
                                f"final={final_payout}, info={discount_info}"
                            )
            
            # 8. 创建转化记录
            conversion = PostbackConversion(
                platform=platform,
                conversion_id=conversion_id,
                event_name=normalized_data.get("event_name"),
                event_value=normalized_data.get("event_value"),
                payout=final_payout,  # 使用扣量后的金额
                devad_id=normalized_data.get("devad_id"),
                os=normalized_data.get("os"),
                carrier=normalized_data.get("carrier"),
                ip=normalized_data.get("ip"),
                gid=normalized_data.get("gid"),
                product_id=product_id,
                client_id=client_id,
                click_id=click_id,  # CPL 系统字段
                click_time=click_time,  # CPL 系统字段
                conversion_status='Pending',  # CPL 系统字段，默认待处理
                raw_data=raw_data_json,
                created_at=datetime.now(timezone.utc)
            )
            
            db.add(conversion)
            await db.commit()
            await db.refresh(conversion)
            
            # 8.5. 如果通过了 Cap 检查，增加 Cap 计数
            if offer_id and click_id:
                try:
                    await increment_cap_count(
                        db=db,
                        offer_id=offer_id,
                        publisher_id=publisher_id,
                        advertiser_id=advertiser_id
                    )
                except Exception as e:
                    # Cap 计数失败不影响主流程
                    logger.warning(f"增加Cap计数失败: {str(e)}")
            
            logger.info(
                f"平台 {platform} postback 转化记录已保存: "
                f"conversion_id={conversion_id}, event_name={event_name}, "
                f"payout={final_payout} (original={normalized_data.get('payout')}), "
                f"product_id={product_id}, client_id={client_id}, "
                f"click_id={click_id}, offer_id={offer_id}"
            )
            
            # 9. 异步发送通知（按客户和产品）
            try:
                await PostbackNotifier.notify_conversion(
                    conversion=conversion,
                    db=db,
                    product=None,  # 将在通知函数中查询
                    client=None   # 将在通知函数中查询
                )
            except Exception as e:
                # 通知失败不影响主流程
                logger.warning(
                    f"发送转化通知失败: conversion_id={conversion_id}, "
                    f"error={str(e)}"
                )
            
            # 10. 异步转发给下游（如果产品配置了下游 URL）
            product = None
            if product_id:
                result = await db.execute(
                    select(Product).where(Product.id == product_id)
                )
                product = result.scalars().first()
            
            if product and product.downstream_postback_url:
                # 异步转发，不阻塞主流程
                # 注意：需要在后台任务中使用新的数据库会话
                try:
                    import asyncio
                    from app.core.database import AsyncSessionLocal
                    
                    async def forward_task():
                        """后台转发任务"""
                        async with AsyncSessionLocal() as new_db:
                            # 重新查询转化记录和产品（使用新的会话）
                            conv_result = await new_db.execute(
                                select(PostbackConversion).where(PostbackConversion.id == conversion.id)
                            )
                            new_conversion = conv_result.scalars().first()
                            
                            prod_result = await new_db.execute(
                                select(Product).where(Product.id == product_id)
                            )
                            new_product = prod_result.scalars().first()
                            
                            if new_conversion and new_product:
                                await PostbackForwarder.forward_to_downstream(
                                    new_conversion, new_product, new_db
                                )
                    
                    asyncio.create_task(forward_task())
                except Exception as e:
                    # 转发失败不影响主流程，只记录日志
                    logger.warning(
                        f"创建下游转发任务失败: conversion_id={conversion_id}, "
                        f"product_id={product_id}, error={str(e)}"
                    )
            
            # 11. 返回成功响应
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

