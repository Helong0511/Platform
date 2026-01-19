"""
Postback统一处理器模块

功能说明：
负责接收、验证、处理和存储来自上游平台的postback回调数据，包括：
- 数据验证：验证postback数据的完整性和有效性
- 数据标准化：将不同平台的数据格式转换为统一格式
- 重复检测：防止重复处理相同的转化事件
- 关联处理：关联Click ID、Offer、Publisher等信息
- Cap检查：检查转化是否超过Cap限制
- 扣量计算：根据配置计算扣量后的金额
- 数据存储：保存转化记录到数据库
- 渠道转发：转发转化数据到渠道（Publisher）的 Postback URL（如果配置）
- 通知发送：发送转化通知（Telegram、邮件等）

处理流程：
1. 获取平台处理器：根据平台名称获取对应的处理器
2. 数据验证：验证postback数据的必填字段和格式
3. 数据标准化：将平台特定格式转换为统一格式
4. 关联Click ID：尝试通过click_id关联Click记录，获取Offer、Publisher等信息
5. 重复检测：检查是否已处理过相同的转化事件
6. Cap检查：检查是否超过转化上限（Daily Cap / Total Cap）
7. 扣量计算：根据Offer和Publisher的扣量配置计算实际金额
8. 保存转化记录：将转化数据保存到postback_conversions表
9. 更新Click统计：更新click_stats表（如果有Click关联）
10. 渠道转发：如果渠道配置了Postback URL，转发转化数据到渠道
11. 发送通知：如果配置了通知，发送转化通知

支持的平台：
- bft: BFT平台
- 其他平台：通过处理器注册机制扩展

CPL系统集成：
- 自动关联Click ID，获取Offer、Publisher、Advertiser信息
- 支持Cap限制检查（Daily Cap和Total Cap）
- 支持扣量计算（Offer级别和Publisher级别）
- 支持渠道Postback转发（自动替换占位符）

安全特性：
- 数据验证：确保必填字段存在且格式正确
- 重复检测：防止重复处理相同的转化事件
- IP验证：可选的支持IP白名单验证
- 错误处理：完善的异常处理和日志记录

性能优化：
- 使用数据库索引优化查询性能
- 批量操作减少数据库交互
- 异步处理下游转发和通知发送
- Redis缓存优化Cap检查性能

注意事项：
1. 所有postback数据都会保存原始数据（raw_data字段）
2. 重复检测基于platform + conversion_id + event_name的唯一性
3. Cap检查失败不会阻止转化记录保存，但会标记状态
4. 渠道转发失败会记录日志，不影响主流程
5. 通知发送失败不会影响转化处理流程
"""
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.core.postback.handlers import get_handler
from app.core.auto_bot import send_telegram_message_with_buttons
from app.core.postback.forwarder import PostbackForwarder
from app.core.postback.notifier import PostbackNotifier
from app.models.models import (
    PostbackConversion, Product, Click, Offer, Advertiser, ClickStats, Client, Publisher,
    ConversionDeductionLog, AdminNotificationConfig, PostbackIpWhitelist, PendingPostbackConversion
)
from app.core.utils import get_app_now_naive, APP_TIMEZONE
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.core.cap import check_cap, increment_cap_count
from app.core.discount import calculate_discount
from app.core.deduction import find_deduction_config, apply_deduction, log_deduction
from app.services.telegram_notification_service import TelegramNotificationService

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
        # 1. 验证 IP 白名单（强制检查，确保不在白名单的 IP 不能保存转化记录）
        # 注意：即使 request_ip 为空或 None，也要进行检查，确保安全性
        if not request_ip or not request_ip.strip() or request_ip.strip() == "unknown":
            # IP 为空或无法获取，拒绝处理（安全考虑）
            logger.warning(
                f"Postback 请求 IP 为空或无法获取，拒绝处理: "
                f"platform={platform}, conversion_id={raw_data.get('clk_id') or raw_data.get('conversion_id') or 'unknown'}, "
                f"request_ip={request_ip!r}"
            )
            # 发送管理员提醒
            try:
                admin_config_result = await db.execute(
                    select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
                )
                admin_config = admin_config_result.scalars().first()
                if (
                    admin_config
                    and admin_config.telegram_enabled
                    and admin_config.notify_system_errors
                    and admin_config.telegram_chat_id
                ):
                    conversion_id_hint = (
                        raw_data.get("clk_id")
                        or raw_data.get("conversion_id")
                        or raw_data.get("click_id")
                        or "unknown"
                    )
                    msg_lines = [
                        "⚠️ Postback IP 验证失败",
                        "",
                        f"平台: {platform}",
                        f"IP: {request_ip or '无法获取'}",
                        f"转化ID/点击ID: {conversion_id_hint}",
                        "说明: IP 为空或无法获取，已拒绝处理（不入库、不转发）。"
                    ]
                    await TelegramNotificationService.send_admin_notification(
                        message="\n".join(msg_lines),
                        telegram_chat_id=admin_config.telegram_chat_id,
                        notification_type='system_error',
                        db=db
                    )
            except Exception as e:
                logger.warning(
                    f"发送IP验证失败提示失败: ip={request_ip}, error={str(e)}"
                )
            # 返回成功响应，但不处理数据
            return {
                "success": True,
                "message": "PostBack 接收成功（IP验证失败，未记录）",
                "conversion_id": raw_data.get("clk_id") or raw_data.get("conversion_id") or None,
                "platform": platform,
                "is_test_data": True
            }
        
        # 清理IP地址：去除空格、端口号等
        cleaned_ip = request_ip.strip()
        # 如果包含端口号（如 43.130.108.206:8080），只取IP部分
        # 注意：IPv6地址格式为 [::1]:8080，需要特殊处理
        if ":" in cleaned_ip:
            # 检查是否是IPv6格式 [::1]:8080
            if cleaned_ip.startswith("[") and "]" in cleaned_ip:
                # IPv6地址带端口号，格式：[2001:db8::1]:8080
                ipv6_end = cleaned_ip.index("]")
                cleaned_ip = cleaned_ip[1:ipv6_end]  # 提取IPv6地址部分
            else:
                # IPv4地址带端口号，格式：43.130.108.206:8080
                parts = cleaned_ip.split(":")
                if len(parts) == 2 and parts[1].isdigit():
                    cleaned_ip = parts[0]
        
        # 查询所有启用的白名单IP，然后在Python中比较（去除空格后比较）
        # 这样可以避免数据库函数兼容性问题，并且更灵活
        all_whitelist_result = await db.execute(
            select(PostbackIpWhitelist.ip_address, PostbackIpWhitelist.id)
            .where(PostbackIpWhitelist.is_active == True)
        )
        all_whitelist_items = all_whitelist_result.all()
        
        # 在Python中比较（去除空格后比较）
        whitelisted_ip = None
        for whitelist_item in all_whitelist_items:
            whitelist_ip = whitelist_item.ip_address.strip() if whitelist_item.ip_address else ""
            # 比较清理后的IP地址
            if whitelist_ip == cleaned_ip:
                whitelisted_ip = whitelist_item
                break
            # 如果白名单IP也包含端口号，只比较IP部分
            if ":" in whitelist_ip and not whitelist_ip.startswith("["):
                whitelist_ip_parts = whitelist_ip.split(":")
                if len(whitelist_ip_parts) == 2 and whitelist_ip_parts[1].isdigit():
                    if whitelist_ip_parts[0] == cleaned_ip:
                        whitelisted_ip = whitelist_item
                        break
        
        # 如果仍然没找到，记录调试日志
        if not whitelisted_ip:
            all_whitelist_ips = [row.ip_address for row in all_whitelist_items]
            logger.warning(
                f"IP白名单验证失败: request_ip={request_ip!r}, cleaned_ip={cleaned_ip!r}, "
                f"白名单中的IP列表={all_whitelist_ips}, "
                f"platform={platform}, conversion_id={raw_data.get('clk_id') or raw_data.get('conversion_id') or 'unknown'}"
            )
            # IP 不在白名单中，保存为待确认状态，发送带确认按钮的 Telegram 通知
            logger.info(
                f"Postback 请求 IP {request_ip} 不在白名单中，保存为待确认状态: "
                f"platform={platform}, conversion_id={raw_data.get('clk_id') or raw_data.get('conversion_id') or 'unknown'}"
            )
            
            # 保存原始数据为 JSON（json 已在文件顶部导入）
            raw_data_json = json.dumps(raw_data, ensure_ascii=False)
            
            # 创建待确认转化记录
            try:
                # 先进行数据标准化，获取基本信息（但不保存到正式表）
                handler = get_handler(platform)
                if handler:
                    is_valid, error_msg = await handler.validate(raw_data)
                    if is_valid:
                        normalized_data = await handler.normalize(raw_data)
                        conversion_id = normalized_data.get("conversion_id")
                        
                        # 创建待确认记录
                        pending_conversion = PendingPostbackConversion(
                            platform=platform,
                            conversion_id=conversion_id or raw_data.get("clk_id") or raw_data.get("conversion_id") or "unknown",
                            event_name=normalized_data.get("event_name"),
                            event_value=normalized_data.get("event_value"),
                            original_payout=normalized_data.get("payout") or raw_data.get("payout") or raw_data.get("PayOut"),
                            payout=normalized_data.get("payout") or raw_data.get("payout") or raw_data.get("PayOut"),
                            devad_id=normalized_data.get("devad_id"),
                            os=normalized_data.get("os"),
                            carrier=normalized_data.get("carrier"),
                            ip=request_ip,
                            gid=normalized_data.get("gid"),
                            product_id=normalized_data.get("product_id"),
                            client_id=normalized_data.get("client_id"),
                            click_id=raw_data.get("our_click_id") or raw_data.get("click_id") or normalized_data.get("click_id"),
                            raw_data=raw_data_json,
                            request_ip=request_ip,
                            status='pending',
                            created_at=get_app_now_naive()
                        )
                        db.add(pending_conversion)
                        await db.commit()
                        await db.refresh(pending_conversion)
                        
                        # 发送带确认按钮的 Telegram 通知
                        try:
                            admin_config_result = await db.execute(
                                select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
                            )
                            admin_config = admin_config_result.scalars().first()
                            if (
                                admin_config
                                and admin_config.telegram_enabled
                                and admin_config.notify_system_errors
                                and admin_config.telegram_chat_id
                            ):
                                from app.core.auto_bot import send_telegram_message_with_buttons
                                
                                conversion_id_hint = (
                                    raw_data.get("clk_id")
                                    or raw_data.get("conversion_id")
                                    or raw_data.get("click_id")
                                    or "unknown"
                                )
                                msg_lines = [
                                    "⚠️ Postback 非白名单IP - 待确认",
                                    "",
                                    f"平台: {platform}",
                                    f"IP: {request_ip}",
                                    f"转化ID/点击ID: {conversion_id_hint}",
                                    "",
                                    "💰 金额信息",
                                ]
                                if pending_conversion.original_payout:
                                    msg_lines.append(f"• 原始金额 (PO): ${pending_conversion.original_payout:.2f}")
                                if pending_conversion.payout:
                                    msg_lines.append(f"• 扣后金额 (PO(扣)): ${pending_conversion.payout:.2f}")
                                
                                msg_lines.extend([
                                    "",
                                    "说明: IP 不在白名单中，请确认是否保存此转化记录。",
                                    f"待确认记录ID: {pending_conversion.id}"
                                ])
                                
                                # 创建确认和拒绝按钮
                                buttons = [
                                    [
                                        {"text": "✅ 确认保存", "callback_data": f"postback_approve_{pending_conversion.id}"},
                                        {"text": "❌ 拒绝", "callback_data": f"postback_reject_{pending_conversion.id}"}
                                    ]
                                ]
                                
                                success, message_id = await send_telegram_message_with_buttons(
                                    message="\n".join(msg_lines),
                                    chat_id=admin_config.telegram_chat_id,
                                    buttons=buttons
                                )
                                
                                if success and message_id:
                                    # 更新待确认记录的 Telegram 消息ID
                                    pending_conversion.telegram_message_id = message_id
                                    pending_conversion.telegram_chat_id = admin_config.telegram_chat_id
                                    await db.commit()
                                    logger.info(f"已发送待确认通知，消息ID: {message_id}, 待确认记录ID: {pending_conversion.id}")
                        except Exception as e:
                            logger.warning(
                                f"发送待确认通知失败: ip={request_ip}, error={str(e)}"
                            )
                    else:
                        logger.warning(f"数据验证失败，无法创建待确认记录: {error_msg}")
            except Exception as e:
                logger.error(f"创建待确认转化记录失败: {str(e)}", exc_info=True)
                await db.rollback()
            
            # 返回成功响应，但不处理数据（关键：这里直接返回，不会执行后续的保存逻辑）
            return {
                "success": True,
                "message": "PostBack 接收成功（待管理员确认）",
                "conversion_id": raw_data.get("clk_id") or raw_data.get("conversion_id") or None,
                "platform": platform,
                "is_pending": True
            }
        else:
            logger.debug(f"Postback 请求 IP {request_ip} 在白名单中，继续处理")
        
        # 2. 获取平台处理器（平台名可能被自定义参数覆盖，但处理器仍按入参平台选择）
        platform_override = raw_data.get("platform")
        if isinstance(platform_override, str):
            platform_override = platform_override.strip()
            if not platform_override:
                platform_override = None
        else:
            platform_override = None

        handler = get_handler(platform)
        if not handler:
            logger.warning(f"未找到平台 {platform} 的处理器")
            raise_api_exception(
                ErrorCode.NOT_FOUND,
                detail=f"不支持的平台: {platform}"
            )
        
        try:
            # 3. 验证数据
            is_valid, error_msg = await handler.validate(raw_data)
            if not is_valid:
                logger.warning(f"平台 {platform} postback 数据验证失败: {error_msg}")
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail=error_msg or "数据验证失败"
                )
            
            # 4. 标准化数据
            normalized_data = await handler.normalize(raw_data)
            conversion_id = normalized_data.get("conversion_id")
            
            if not conversion_id:
                logger.warning(f"平台 {platform} postback 数据缺少 conversion_id")
                raise_api_exception(
                    ErrorCode.VALIDATION_ERROR,
                    detail="缺少必填字段: conversion_id"
                )
            
            # 5. 验证产品和客户（如果提供）
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
            
            # 5.5. CPL 系统：尝试关联 Click ID 获取广告主信息（在检查重复之前）
            click_id = None
            click_time = None
            offer_id = None
            publisher_id = None
            advertiser_id = None
            advertiser_name = None  # 广告主名称，将用作平台名称
            
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
                    
                    # 将点击记录的核心字段保存到统计表（如果不存在）
                    # 这样即使 clicks 表被清理，转化统计仍然可用
                    # 注意：只有在转化创建成功时才会提交，如果转化失败则不会保存 ClickStats
                    try:
                        existing_stats = await db.execute(
                            select(ClickStats).where(ClickStats.click_id == click_id)
                        )
                        if not existing_stats.scalars().first():
                            # 只有不存在时才创建，避免重复
                            click_stats = ClickStats(
                                click_id=click_id,
                                offer_id=offer_id,
                                publisher_id=publisher_id,
                                advertiser_id=advertiser_id,
                                click_time=click_time,
                                created_at=get_app_now_naive()
                            )
                            db.add(click_stats)
                            logger.debug(f"已创建点击统计记录: click_id={click_id}")
                    except Exception as e:
                        # ClickStats 写入失败不影响主流程，但记录警告
                        logger.warning(f"创建点击统计记录失败: click_id={click_id}, error={str(e)}")
                    
                    # 根据 advertiser_id 查询广告主名称，用作平台名称
                    if advertiser_id:
                        advertiser_result = await db.execute(
                            select(Advertiser).where(Advertiser.id == advertiser_id)
                        )
                        advertiser_obj = advertiser_result.scalars().first()
                        if advertiser_obj:
                            advertiser_name = advertiser_obj.advertiser_name
                            # 如果未传自定义平台名，则将平台名称设置为广告主名称
                            if not platform_override:
                                platform = advertiser_name
                                logger.info(
                                    f"根据 click_id={click_id} 找到广告主: "
                                    f"advertiser_id={advertiser_id}, advertiser_name={advertiser_name}, "
                                    f"平台名称已更新为: {platform}"
                                )
            
            # 6. 检查是否已存在（防重复处理）- 使用更新后的平台名称
            event_name = normalized_data.get("event_name")
            if platform_override:
                final_platform = platform_override
            else:
                final_platform = advertiser_name if advertiser_name else platform
            
            # 6.1. 检查主表（PostbackConversion）
            existing = await db.execute(
                select(PostbackConversion).where(
                    PostbackConversion.platform == final_platform,
                    PostbackConversion.conversion_id == conversion_id,
                    PostbackConversion.event_name == event_name
                )
            )
            existing_record = existing.scalars().first()
            
            # 6.2. 如果主表中没有，检查扣减日志表（因为被扣量的转化不保存到主表）
            if not existing_record and click_id:
                # ConversionDeductionLog 已在文件顶部导入
                log_check = await db.execute(
                    select(ConversionDeductionLog).where(
                        ConversionDeductionLog.click_id == click_id,
                        ConversionDeductionLog.created_at >= get_app_now_naive() - timedelta(days=1)  # 最近1天内的记录
                    ).order_by(ConversionDeductionLog.created_at.desc())
                )
                existing_log = log_check.scalars().first()
                if existing_log:
                    # 如果扣减日志中存在，说明已经处理过（可能被扣量了）
                    logger.info(
                        f"转化已在扣减日志中存在，跳过重复处理: conversion_id={conversion_id}, "
                        f"click_id={click_id}, log_id={existing_log.id}"
                    )
                    
                    # 发送 Telegram 通知提示重复
                    try:
                        admin_config_result = await db.execute(
                            select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
                        )
                        admin_config = admin_config_result.scalars().first()
                        if admin_config and admin_config.telegram_enabled and admin_config.notify_all_conversions:
                            if admin_config.telegram_chat_id:
                                duplicate_message = (
                                    "⚠️ Postback 重复转化提示\n\n"
                                    f"转化ID: {conversion_id}\n"
                                    f"平台: {final_platform}\n"
                                    f"Click ID: {click_id or 'N/A'}\n\n"
                                    "说明: 该转化已在扣减日志中存在，可能是重复的 PostBack 请求。\n"
                                    f"日志ID: {existing_log.id}\n"
                                    f"创建时间: {existing_log.created_at.strftime('%Y-%m-%d %H:%M:%S') if existing_log.created_at else 'N/A'}\n"
                                )
                                asyncio.create_task(
                                    TelegramNotificationService.send_admin_notification(
                                        message=duplicate_message,
                                        telegram_chat_id=admin_config.telegram_chat_id,
                                        conversion=None,  # 重复转化不关联转化记录
                                        notification_type='system_error',
                                        db=db
                                    )
                                )
                    except Exception as e:
                        logger.warning(f"发送重复转化 Telegram 通知失败: {str(e)}")
                    
                    return {
                        "success": True,
                        "message": "PostBack 接收成功（已在扣减日志中存在，跳过重复处理）",
                        "conversion_id": conversion_id,
                        "platform": final_platform
                    }
            
            if existing_record:
                # 如果记录已存在，根据 click_id 更新数据
                updated = False
                if click_record:
                    # 更新字段（如果 clicks 表中有数据且 postback_conversions 中没有）
                    if not existing_record.os and click_record.os:
                        existing_record.os = click_record.os
                        updated = True
                    
                    if not existing_record.ip and click_record.ip:
                        existing_record.ip = click_record.ip
                        updated = True
                    
                    if not existing_record.gid and click_record.publisher_id:
                        existing_record.gid = str(click_record.publisher_id)
                        updated = True
                    
                    # 更新 click_id 和 click_time（如果之前没有）
                    if not existing_record.click_id and click_id:
                        existing_record.click_id = click_id
                        updated = True
                    
                    if not existing_record.click_time and click_time:
                        existing_record.click_time = click_time
                        updated = True
                    
                    if updated:
                        await db.commit()
                        await db.refresh(existing_record)
                        # 已更新数据，只记录一次日志
                        logger.info(
                            f"平台 {final_platform} postback 转化已存在，已根据 click_id 更新数据: "
                            f"conversion_id={conversion_id}, event_name={event_name}"
                        )
                    else:
                        # 未更新数据，记录跳过日志
                        logger.info(
                            f"平台 {final_platform} postback 转化已存在，跳过重复处理: "
                            f"conversion_id={conversion_id}, event_name={event_name}"
                        )
                    
                    # 发送 Telegram 通知提示重复
                    try:
                        admin_config_result = await db.execute(
                            select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
                        )
                        admin_config = admin_config_result.scalars().first()
                        if admin_config and admin_config.telegram_enabled and admin_config.notify_all_conversions:
                            if admin_config.telegram_chat_id:
                                # 获取相关信息用于通知
                                client = None
                                product = None
                                publisher = None
                                offer = None
                                
                                if existing_record.client_id:
                                    client_result = await db.execute(
                                        select(Client).where(Client.id == existing_record.client_id)
                                    )
                                    client = client_result.scalars().first()
                                
                                if existing_record.product_id:
                                    product_result = await db.execute(
                                        select(Product).where(Product.id == existing_record.product_id)
                                    )
                                    product = product_result.scalars().first()
                                
                                # 尝试获取渠道和Offer信息
                                lookup_click_id = existing_record.click_id or click_id
                                if lookup_click_id:
                                    click_stats_result = await db.execute(
                                        select(ClickStats).where(ClickStats.click_id == lookup_click_id)
                                    )
                                    click_stats = click_stats_result.scalars().first()
                                    if click_stats:
                                        if click_stats.publisher_id:
                                            publisher_result = await db.execute(
                                                select(Publisher).where(Publisher.id == click_stats.publisher_id)
                                            )
                                            publisher = publisher_result.scalars().first()
                                        if click_stats.offer_id:
                                            offer_result = await db.execute(
                                                select(Offer).where(Offer.id == click_stats.offer_id)
                                            )
                                            offer = offer_result.scalars().first()
                                
                                # 构建重复转化通知消息
                                duplicate_message = "⚠️ Postback 重复转化提示\n\n"
                                duplicate_message += f"转化ID: {conversion_id}\n"
                                duplicate_message += f"平台: {final_platform}\n"
                                if event_name:
                                    duplicate_message += f"事件: {event_name}\n"
                                
                                if existing_record.original_payout is not None:
                                    duplicate_message += f"\n💰 金额信息\n"
                                    duplicate_message += f"• 原始金额 (PO): ${existing_record.original_payout:.2f}\n"
                                    if existing_record.payout is not None:
                                        duplicate_message += f"• 扣后金额 (PO(扣)): ${existing_record.payout:.2f}\n"
                                
                                client_name = client.client_name if client else None
                                product_name = product.product_name if product else None
                                
                                if client_name or product_name:
                                    duplicate_message += "\n👤 客户信息\n"
                                    if client_name:
                                        duplicate_message += f"• 客户: {client_name}\n"
                                    if product_name:
                                        duplicate_message += f"• 产品: {product_name}\n"
                                
                                if publisher:
                                    duplicate_message += "\n📤 渠道信息\n"
                                    duplicate_message += f"• 渠道ID: {publisher.id}\n"
                                    duplicate_message += f"• 渠道名称: {publisher.publisher_name}\n"
                                
                                if offer:
                                    if not publisher:
                                        duplicate_message += "\n📤 渠道信息\n"
                                    duplicate_message += f"• Offer ID: {offer.id}\n"
                                    if offer.offer_name:
                                        duplicate_message += f"• Offer 名称: {offer.offer_name}\n"
                                
                                duplicate_message += "\n⚠️ 说明\n"
                                duplicate_message += "该转化记录已存在，可能是重复的 PostBack 请求。\n"
                                if updated:
                                    duplicate_message += "已根据新的 click_id 更新了部分数据。\n"
                                else:
                                    duplicate_message += "未发现需要更新的数据，已跳过处理。\n"
                                
                                if existing_record.created_at:
                                    time_str = existing_record.created_at.strftime("%Y-%m-%d %H:%M:%S")
                                    duplicate_message += f"\n⏰ 原记录创建时间: {time_str}\n"
                                
                                asyncio.create_task(
                                    TelegramNotificationService.send_admin_notification(
                                        message=duplicate_message,
                                        telegram_chat_id=admin_config.telegram_chat_id,
                                        conversion=existing_record,  # 关联已存在的转化记录
                                        notification_type='system_error',
                                        db=db
                                    )
                                )
                    except Exception as e:
                        logger.warning(f"发送重复转化 Telegram 通知失败: {str(e)}")
                    
                return {
                    "success": True,
                    "message": "PostBack 接收成功（已存在，跳过重复处理）",
                    "conversion_id": conversion_id,
                    "platform": final_platform
                }
            
            # 7. 保存原始数据（JSON格式）
            raw_data_json = json.dumps(raw_data, ensure_ascii=False)
            
            # 8. 如果提供了IP，添加到标准化数据中
            if request_ip and not normalized_data.get("ip"):
                normalized_data["ip"] = request_ip
            
            # 8.5. CPL 系统：进行 Cap/扣量检查（广告主信息已在上面获取）
            # 从标准化数据中获取 payout，如果不存在则尝试从原始数据中获取（支持多种字段名）
            original_payout = normalized_data.get("payout")
            if original_payout is None:
                # 尝试从原始数据中获取（支持多种字段名：payout, PayOut, pay_out 等）
                original_payout = (
                    raw_data.get("payout") or
                    raw_data.get("PayOut") or
                    raw_data.get("pay_out") or
                    raw_data.get("pay-out") or
                    raw_data.get("Pay_Out") or
                    raw_data.get("Payout") or
                    raw_data.get("PAYOUT")
                )
                # 如果是字符串，尝试转换为浮点数
                if original_payout is not None and isinstance(original_payout, str):
                    try:
                        original_payout = float(original_payout)
                    except (ValueError, TypeError):
                        original_payout = None
                # 如果找到了，更新到 normalized_data 中
                if original_payout is not None:
                    normalized_data["payout"] = original_payout
                    logger.debug(
                        f"从原始数据中提取 payout: conversion_id={conversion_id}, "
                        f"original_payout={original_payout}"
                    )
            
            final_payout = original_payout  # 扣后 payout (PO(扣))，初始值等于原始值
            discount_info = None
            
            # 如果之前找到了 click_record，进行 Cap 和扣量检查
            if click_id and offer_id is not None:
                # 0. 检查 Offer 激活状态和状态
                offer_obj = None
                if offer_id:
                    offer = await db.execute(select(Offer).where(Offer.id == offer_id))
                    offer_obj = offer.scalars().first()
                    if offer_obj:
                        # 检查 Offer 是否激活
                        if not offer_obj.is_active:
                            logger.warning(
                                f"转化被拒绝：Offer未激活: conversion_id={conversion_id}, "
                                f"offer_id={offer_id}, offer_name={offer_obj.offer_name}"
                            )
                            # 标记状态为 OfferInactive，由后续逻辑处理
                            normalized_data["status_override"] = "OfferInactive"
                            normalized_data["rejection_reason"] = f"Offer未激活: offer_id={offer_id}, offer_name={offer_obj.offer_name}"
                        
                        # 检查 Offer 状态（status字段）
                        elif offer_obj.status != 'Active':
                            logger.warning(
                                f"转化被拒绝：Offer状态非Active: conversion_id={conversion_id}, "
                                f"offer_id={offer_id}, offer_name={offer_obj.offer_name}, status={offer_obj.status}"
                            )
                            # 标记状态为 OfferInactive，由后续逻辑处理
                            normalized_data["status_override"] = "OfferInactive"
                            normalized_data["rejection_reason"] = f"Offer状态非Active: offer_id={offer_id}, offer_name={offer_obj.offer_name}, status={offer_obj.status}"
                
                # 0.1. 检查点击有效期 (Click Validity) - 只在Offer激活且状态为Active时检查
                if offer_obj and offer_obj.is_active and offer_obj.status == 'Active':
                    validity_hours = offer_obj.click_validity_hours or 720  # 默认30天
                    # 计算小时差
                    # 数据库中的 click_time 是应用时区的 naive datetime（北京时间）
                    now_app = get_app_now_naive()
                    if click_time:
                        # 如果 click_time 是 naive，假设它是应用时区（北京时间）
                        if click_time.tzinfo is None:
                            # 直接使用naive datetime进行比较（都是应用时区）
                            hours_diff = (now_app - click_time).total_seconds() / 3600
                        else:
                            # 如果有时区信息，转换为应用时区的naive datetime
                            click_time_app = click_time.astimezone(APP_TIMEZONE).replace(tzinfo=None)
                            hours_diff = (now_app - click_time_app).total_seconds() / 3600
                    else:
                        hours_diff = 0  # 如果没有 click_time，跳过有效期检查
                    
                    if hours_diff > validity_hours:
                        logger.warning(
                            f"转化被点击有效期拒绝: conversion_id={conversion_id}, "
                            f"click_age={hours_diff:.1f}h, limit={validity_hours}h"
                        )
                        # 标记状态为 ClickExpired，由后续逻辑处理
                        normalized_data["status_override"] = "ClickExpired"
                        normalized_data["rejection_reason"] = f"Click expired ({hours_diff:.1f}h > {validity_hours}h)"

                # 检查 Cap 限制 - 只在Offer激活且状态为Active时检查
                if offer_obj and offer_obj.is_active and offer_obj.status == 'Active' and offer_id:
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
                
                # 计算扣量（旧版扣量逻辑，保留兼容性）- 只在Offer激活且状态为Active时计算
                if offer_obj and offer_obj.is_active and offer_obj.status == 'Active' and offer_id and publisher_id and final_payout:
                    final_payout, discount_amount, discount_info = await calculate_discount(
                        db=db,
                        offer_id=offer_id,
                        publisher_id=publisher_id,
                        original_payout=final_payout
                    )
                    if discount_info:
                        logger.info(
                            f"应用扣量: conversion_id={conversion_id}, "
                            f"original_payout={original_payout}, "
                            f"final_payout={final_payout}, info={discount_info}"
                        )
            
            # 8.6. CPL 系统：应用新的扣减逻辑（按比例扣量和扣金额）
            # 只在Offer激活且状态为Active时应用扣减
            deduction_result = None
            deduction_config = None
            if (advertiser_id or offer_id or publisher_id) and (not offer_obj or (offer_obj.is_active and offer_obj.status == 'Active')):
                try:
                    # find_deduction_config 和 apply_deduction 已在文件顶部导入
                    
                    # 查找扣减配置
                    deduction_config = await find_deduction_config(
                        db=db,
                        advertiser_id=advertiser_id,
                        offer_id=offer_id,
                        publisher_id=publisher_id
                    )
                    
                    if deduction_config:
                        # 应用扣减
                        conversion_data = {
                            'original_payout': original_payout or 0.0
                        }
                        deduction_result = await apply_deduction(
                            db=db,
                            conversion_data=conversion_data,
                            config=deduction_config,
                            click_id=click_id,
                            advertiser_id=advertiser_id,
                            offer_id=offer_id,
                            publisher_id=publisher_id
                        )
                        
                        # 如果扣减了金额，更新final_payout
                        if deduction_result.get('should_deduct_amount'):
                            final_payout = deduction_result['final_amount']
                            logger.info(
                                f"应用扣减金额: conversion_id={conversion_id}, "
                                f"original_payout={deduction_result['original_amount']}, "
                                f"final_payout={final_payout}, "
                                f"deducted_amount={deduction_result['deducted_amount']}"
                            )
                except Exception as e:
                    # 扣减逻辑失败不影响主流程，但记录错误
                    logger.error(
                        f"应用扣减逻辑失败: conversion_id={conversion_id}, "
                        f"error={str(e)}", 
                        exc_info=True
                    )
                    # 继续处理，不使用扣减结果
                    deduction_result = None
                    deduction_config = None
            
            # 9. 创建转化记录（优先使用自定义平台名称，其次广告主名称）
            if platform_override:
                final_platform = platform_override
            else:
                final_platform = advertiser_name if advertiser_name else platform
            
            # 9.1. 根据 click_id 从 clicks 表获取数据，补充或更新字段
            # 如果 postback 数据中没有某些字段，使用 clicks 表中的数据
            final_os = normalized_data.get("os")
            final_ip = normalized_data.get("ip") or request_ip
            final_gid = normalized_data.get("gid")
            
            if click_record:
                # 如果 postback 数据中没有 os，使用 clicks 表的 os
                if not final_os and click_record.os:
                    final_os = click_record.os
                    logger.debug(f"从 clicks 表补充 os: {final_os}")
                
                # 如果 postback 数据中没有 ip，使用 clicks 表的 ip
                if not final_ip and click_record.ip:
                    final_ip = click_record.ip
                    logger.debug(f"从 clicks 表补充 ip: {final_ip}")
                
                # 如果 postback 数据中没有 gid，使用 clicks 表的 publisher_id 作为 gid
                if not final_gid and click_record.publisher_id:
                    final_gid = str(click_record.publisher_id)
                    logger.debug(f"从 clicks 表补充 gid (publisher_id): {final_gid}")
            
            # 9.2. 判断是否应该保存转化记录（如果扣量了，可能不保存）
            should_save_conversion = True
            if deduction_result and deduction_result.get('should_deduct_volume'):
                # 如果扣量了，不保存转化记录（隐藏扣减）
                should_save_conversion = False
                logger.info(
                    f"转化被扣量，不保存到主表: conversion_id={conversion_id}, "
                    f"click_id={click_id}"
                )
            
            # 9.2.1. 额外的安全检查：再次验证 IP 白名单（防御性编程）
            # 确保即使前面的逻辑有变化，不在白名单的 IP 也绝对不会保存转化记录
            if should_save_conversion and request_ip:
                cleaned_ip_check = request_ip.strip()
                # 处理端口号
                if ":" in cleaned_ip_check:
                    if cleaned_ip_check.startswith("[") and "]" in cleaned_ip_check:
                        ipv6_end = cleaned_ip_check.index("]")
                        cleaned_ip_check = cleaned_ip_check[1:ipv6_end]
                    else:
                        parts = cleaned_ip_check.split(":")
                        if len(parts) == 2 and parts[1].isdigit():
                            cleaned_ip_check = parts[0]
                
                # 快速检查：查询白名单
                whitelist_check_result = await db.execute(
                    select(PostbackIpWhitelist.ip_address)
                    .where(PostbackIpWhitelist.is_active == True)
                )
                whitelist_check_items = whitelist_check_result.all()
                
                is_whitelisted = False
                for whitelist_item in whitelist_check_items:
                    whitelist_ip = whitelist_item.ip_address.strip() if whitelist_item.ip_address else ""
                    if whitelist_ip == cleaned_ip_check:
                        is_whitelisted = True
                        break
                    if ":" in whitelist_ip and not whitelist_ip.startswith("["):
                        whitelist_ip_parts = whitelist_ip.split(":")
                        if len(whitelist_ip_parts) == 2 and whitelist_ip_parts[1].isdigit():
                            if whitelist_ip_parts[0] == cleaned_ip_check:
                                is_whitelisted = True
                                break
                
                if not is_whitelisted:
                    # 严重安全警告：IP 不在白名单中，但代码执行到了这里
                    logger.error(
                        f"【安全警告】IP 不在白名单中，但代码执行到了保存转化记录的位置！"
                        f"request_ip={request_ip!r}, cleaned_ip={cleaned_ip_check!r}, "
                        f"platform={platform}, conversion_id={conversion_id}"
                    )
                    # 强制不保存转化记录
                    should_save_conversion = False
                    # 发送严重安全警告通知
                    try:
                        admin_config_result = await db.execute(
                            select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
                        )
                        admin_config = admin_config_result.scalars().first()
                        if (
                            admin_config
                            and admin_config.telegram_enabled
                            and admin_config.notify_system_errors
                            and admin_config.telegram_chat_id
                        ):
                            msg_lines = [
                                "🚨 【严重安全警告】Postback 白名单验证异常",
                                "",
                                f"平台: {platform}",
                                f"IP: {request_ip}",
                                f"转化ID: {conversion_id}",
                                "",
                                "说明: IP 不在白名单中，但代码执行到了保存转化记录的位置。",
                                "已强制阻止保存转化记录，请检查代码逻辑。"
                            ]
                            await TelegramNotificationService.send_admin_notification(
                                message="\n".join(msg_lines),
                                telegram_chat_id=admin_config.telegram_chat_id,
                                notification_type='system_error',
                                db=db
                            )
                    except Exception as e:
                        logger.error(f"发送安全警告通知失败: {str(e)}")
            
            conversion = None
            conversion_id_for_log = None
            
            if should_save_conversion:
                # 创建转化记录
                conversion = PostbackConversion(
                    platform=final_platform,
                    conversion_id=conversion_id,
                    event_name=normalized_data.get("event_name"),
                    event_value=normalized_data.get("event_value"),
                    original_payout=original_payout,  # 原始 payout (PO)
                    payout=final_payout,  # 扣后 payout (PO(扣))
                    devad_id=normalized_data.get("devad_id"),
                    os=final_os,  # 使用补充后的 os
                    carrier=normalized_data.get("carrier"),
                    ip=final_ip,  # 使用补充后的 ip
                    gid=final_gid,  # 使用补充后的 gid
                    product_id=product_id,
                    client_id=client_id,
                    click_id=click_id,  # CPL 系统字段
                    click_time=click_time,  # CPL 系统字段
                    conversion_status='Pending',  # CPL 系统字段，默认待处理
                    raw_data=raw_data_json,
                    # 扣减相关字段
                    is_deducted=bool(deduction_result and (deduction_result.get('should_deduct_volume') or deduction_result.get('should_deduct_amount'))),
                    deduction_type=deduction_result.get('deduction_type') if deduction_result else None,
                    original_volume=deduction_result.get('original_volume', 1) if deduction_result else 1,
                    deducted_volume=deduction_result.get('deducted_volume', 0) if deduction_result else 0,
                    created_at=get_app_now_naive()
                )
                
                db.add(conversion)
                await db.commit()
                await db.refresh(conversion)
                conversion_id_for_log = conversion.id
            
            # 9.3. 记录扣减日志（无论是否保存转化记录都要记录）
            # 注意：根据系统设计，所有转化都会记录到扣减日志表，即使未扣减也会记录
            # 这样可以确保统计的准确性（统计时查询扣减日志表即可获得所有转化数据）
            if deduction_result and deduction_config:
                # 有配置且应用了扣减逻辑
                try:
                    # log_deduction 已在文件顶部导入
                    # 确定配置层级
                    if deduction_config.advertiser_id:
                        level_str = 'advertiser'
                    elif deduction_config.offer_id:
                        level_str = 'offer'
                    else:
                        level_str = 'publisher'
                    deduction_reason = f"应用扣减配置: level={level_str}, config_id={deduction_config.id}"
                    await log_deduction(
                        db=db,
                        deduction_result=deduction_result,
                        conversion_id=conversion_id_for_log,
                        click_id=click_id,
                        advertiser_id=advertiser_id,
                        offer_id=offer_id,
                        publisher_id=publisher_id,
                        config=deduction_config,
                        deduction_reason=deduction_reason
                    )
                    await db.commit()
                    logger.debug(
                        f"扣减日志记录成功: conversion_id={conversion_id}, "
                        f"click_id={click_id}, "
                        f"deduction_type={deduction_result.get('deduction_type')}"
                    )
                except Exception as e:
                    # 日志记录失败不影响主流程，但记录错误
                    logger.error(
                        f"记录扣减日志失败: conversion_id={conversion_id}, "
                        f"click_id={click_id}, "
                        f"error={str(e)}", 
                        exc_info=True
                    )
            elif (advertiser_id or offer_id or publisher_id):
                # 即使没有找到配置，也记录一条日志（用于统计，标记为未扣减）
                # 这样可以确保统计时能获取到所有转化数据
                try:
                    # log_deduction 已在文件顶部导入
                    # 创建一个空的扣减结果，表示未应用扣减
                    no_deduction_result = {
                        'should_deduct_volume': False,
                        'should_deduct_amount': False,
                        'original_volume': 1,
                        'original_amount': original_payout or 0.0,
                        'final_volume': 1,
                        'final_amount': original_payout or 0.0,
                        'deducted_volume': 0,
                        'deducted_amount': 0.0,
                        'deduction_type': None
                    }
                    await log_deduction(
                        db=db,
                        deduction_result=no_deduction_result,
                        conversion_id=conversion_id_for_log,
                        click_id=click_id,
                        advertiser_id=advertiser_id,
                        offer_id=offer_id,
                        publisher_id=publisher_id,
                        config=None,
                        deduction_reason="未找到扣减配置"
                    )
                    await db.commit()
                except Exception as e:
                    # 静默失败，不影响主流程
                    logger.debug(f"记录未扣减日志失败: {str(e)}")
                    # 尝试回滚，但不影响主流程
                    try:
                        await db.rollback()
                    except:
                        pass
            
            # 9.4. 如果通过了 Cap 检查，增加 Cap 计数
            # 只有当转化状态正常(Pending/Approved)时才增加计数
            # 注意：如果转化被扣量了（conversion为None），不执行后续逻辑
            if conversion and offer_id and click_id and conversion.conversion_status in ['Pending', 'Approved']:
                # 检查是否有 Override 状态
                if normalized_data.get("status_override"):
                    conversion.conversion_status = normalized_data.get("status_override")
                    if normalized_data.get("rejection_reason"):
                         # 记录拒绝原因到 raw_data 或其他字段? 暂时只改状态
                         pass
                else:
                    # 尝试增加计数
                    try:
                        is_within_cap = await increment_cap_count(
                            db=db,
                            offer_id=offer_id,
                            publisher_id=publisher_id,
                            advertiser_id=advertiser_id
                        )
                        
                        if not is_within_cap:
                            # 严重：计数递增后发现超限 (Race Condition 捕获)
                            logger.warning(
                                f"转化在计数后被判定超限 (Race Condition): conversion_id={conversion_id}, "
                                f"offer_id={offer_id}. 更新状态为 CapReached"
                            )
                            conversion.conversion_status = 'CapReached'
                            # 注意：这里我们不需要回滚计数，因为 Redis 计数已经加了。
                            # 实际上这会导致 Cap 计数略微超过限制，但这是为了防止超发给下游。
                            # 如果想回滚，可以在 cap_manager 中增加 decrement 方法。
                            
                    except Exception as e:
                        # Cap 计数失败不影响主流程，但记录严重错误
                        logger.error(f"增加Cap计数失败: {str(e)}")
            
            # 再次提交以保存状态更新（如果conversion存在）
            if conversion:
                await db.commit()
            
            # 记录日志（区分是否保存了转化记录）
            if conversion:
                logger.info(
                    f"平台 {final_platform} postback 转化记录已保存: "
                    f"conversion_id={conversion_id}, event_name={event_name}, "
                    f"original_payout={original_payout}, payout={final_payout}, "
                    f"product_id={product_id}, client_id={client_id}, "
                    f"click_id={click_id}, offer_id={offer_id}"
                )
            else:
                logger.info(
                    f"平台 {final_platform} postback 转化被扣量，未保存到主表: "
                    f"conversion_id={conversion_id}, event_name={event_name}, "
                    f"original_payout={original_payout}, "
                    f"click_id={click_id}, offer_id={offer_id}"
                )
            
            # 如果 original_payout 为 None，记录警告
            if original_payout is None:
                logger.warning(
                    f"警告：转化记录缺少原始 payout (PO): conversion_id={conversion_id}, "
                    f"platform={final_platform}, raw_data_keys={list(raw_data.keys())}"
                )
            
            # 10. 异步发送通知（按客户和产品）
            # 注意：如果转化被扣量了（conversion为None），不发送通知
            # 注意：notify_conversion 内部已处理异常并记录日志，这里不需要重复记录
            if conversion:
                try:
                    await PostbackNotifier.notify_conversion(
                        conversion=conversion,
                        db=db,
                        product=None,  # 将在通知函数中查询
                        client=None   # 将在通知函数中查询
                    )
                except Exception as e:
                    # 只有在 notify_conversion 内部未捕获的异常才记录（通常不会发生）
                    # 内部异常已在 notify_conversion 中记录，这里只记录未预期的异常
                    logger.debug(
                        f"通知函数调用异常（内部应已记录）: conversion_id={conversion_id}, "
                        f"error={str(e)}"
                    )
                
                # 10.1. 发送管理员通知（如果配置了）
                try:
                    # TelegramNotificationService 和 AdminNotificationConfig 已在文件顶部导入
                    # 查询管理员通知配置
                    admin_config_result = await db.execute(
                        select(AdminNotificationConfig).where(AdminNotificationConfig.id == 1)
                    )
                    admin_config = admin_config_result.scalars().first()
                    
                    # 检查是否需要发送管理员通知
                    if admin_config and admin_config.telegram_enabled and admin_config.notify_all_conversions:
                        if admin_config.telegram_chat_id:
                            # 获取客户和产品信息
                            client = None
                            product = None
                            publisher = None
                            offer = None
                            
                            if conversion.client_id:
                                client_result = await db.execute(
                                    select(Client).where(Client.id == conversion.client_id)
                                )
                                client = client_result.scalars().first()
                            
                            if conversion.product_id:
                                product_result = await db.execute(
                                    select(Product).where(Product.id == conversion.product_id)
                                )
                                product = product_result.scalars().first()
                            
                            # 尝试获取渠道和Offer信息
                            lookup_click_id = conversion.conversion_id if conversion.conversion_id else conversion.click_id
                            if lookup_click_id:
                                # 使用已在文件顶部导入的模型（Offer, ClickStats, Publisher）
                                click_stats_result = await db.execute(
                                    select(ClickStats).where(ClickStats.click_id == lookup_click_id)
                                )
                                click_stats = click_stats_result.scalars().first()
                                if click_stats:
                                    if click_stats.publisher_id:
                                        publisher_result = await db.execute(
                                            select(Publisher).where(Publisher.id == click_stats.publisher_id)
                                        )
                                        publisher = publisher_result.scalars().first()
                                    if click_stats.offer_id:
                                        offer_result = await db.execute(
                                            select(Offer).where(Offer.id == click_stats.offer_id)
                                        )
                                        offer = offer_result.scalars().first()
                            
                            # 构建管理员通知消息
                            client_name = client.client_name if client else None
                            product_name = product.product_name if product else None
                            
                            admin_message = TelegramNotificationService.build_admin_conversion_message(
                                conversion=conversion,
                                client_name=client_name,
                                product_name=product_name,
                                publisher=publisher,
                                offer=offer
                            )
                            
                            # 异步发送管理员通知
                            asyncio.create_task(
                                TelegramNotificationService.send_admin_notification(
                                    message=admin_message,
                                    telegram_chat_id=admin_config.telegram_chat_id,
                                    conversion=conversion,
                                    notification_type='conversion',
                                    db=db
                                )
                            )
                except Exception as e:
                    # 管理员通知失败不影响主流程
                    logger.warning(
                        f"发送管理员转化通知失败: conversion_id={conversion_id}, "
                        f"error={str(e)}"
                    )
            
            # 11. 异步转发给渠道（如果渠道配置了 Postback URL）
            # 注意：PostBack 数据只转发给渠道（Publisher），不转发给其他系统
            # 注意：如果转化被扣量了（conversion为None），不转发
            if conversion and conversion.conversion_status in ['Pending', 'Approved']:
                try:
                    # 转发到渠道的 Postback URL
                    # PostbackForwarder 已在文件顶部导入
                    await PostbackForwarder.forward_to_publisher(
                        conversion=conversion,
                        db=db
                    )
                except Exception as e:
                    # 渠道转发失败不影响主流程
                    logger.warning(
                        f"转发到渠道 Postback URL 失败: conversion_id={conversion_id}, "
                        f"error={str(e)}"
                    )
            
            # 12. 返回成功响应
            return {
                "success": True,
                "message": "PostBack 接收成功",
                "conversion_id": conversion_id,
                "platform": final_platform
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

