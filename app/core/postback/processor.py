"""
Postback 统一处理器模块（重构版）

协调各子模块完成 Postback 处理流程：
1. IP 验证 → 2. 数据验证 → 3. 数据标准化 → 4. Click 关联 → 5. 重复检测
6. Cap 检查 → 7. 扣量计算 → 8. 保存记录 → 9. 渠道转发 → 10. 通知发送
"""
import logging
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postback.validators.ip_validator import IpValidator
from app.core.postback.validators.data_validator import DataValidator
from app.core.postback.validators.duplicate_checker import DuplicateChecker
from app.core.postback.transformers.normalizer import DataNormalizer
from app.core.postback.transformers.click_associator import ClickAssociator
from app.core.postback.checks.cap_checker import CapChecker
from app.core.postback.checks.discount_checker import DiscountChecker
from app.core.postback.savers.conversion_saver import ConversionSaver
from app.core.postback.forwarder import PostbackForwarder
from app.core.postback.notifier import PostbackNotifier
from app.models.models import AdminNotificationConfig
from app.services.telegram_notification_service import TelegramNotificationService
from app.core.third_party_report import send_third_party_report

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
            request_ip: 请求 IP 地址
            
        Returns:
            处理结果字典
        """
        # 详细日志：开始处理 Postback
        logger.info(f"=== PostBack 接收处理开始 ===")
        logger.info(f"平台: {platform}")
        logger.info(f"请求 IP: {request_ip}")
        logger.info(f"原始数据: {raw_data}")
        
        try:
            # ========== 第 1 步：IP 验证 ==========
            logger.info("=== 第 1 步：IP 验证 ===")
            ip_valid, cleaned_ip = await IpValidator.validate(request_ip, db)
            logger.info(f"IP 验证结果: {ip_valid}, 清理后 IP: {cleaned_ip}")
            
            if not ip_valid:
                logger.warning("IP 验证失败，处理失败流程")
                return await PostbackProcessor._handle_ip_failure(platform, raw_data, db)
            
            # ========== 第 2 步：数据验证 ==========
            logger.info("=== 第 2 步：数据验证 ===")
            # 优先使用平台特定处理器
            from app.core.postback.handlers import get_handler
            handler = get_handler(platform)
            
            if handler:
                logger.info(f"使用平台特定处理器: {handler.__class__.__name__}")
                # 使用平台特定处理器验证
                data_valid, error_msg = await handler.validate(raw_data)
                if not data_valid:
                    logger.warning(f"数据验证失败：platform={platform}, error={error_msg}")
                    return {
                        "success": True,
                        "message": "数据验证失败",
                        "errors": [error_msg] if error_msg else []
                    }
                
                # ========== 第 3 步：数据标准化 ==========
                logger.info("=== 第 3 步：数据标准化 ===")
                normalized_data = await handler.normalize(raw_data)
            else:
                logger.info("使用通用验证和标准化")
                # 回退到通用验证和标准化
                data_valid, errors = DataValidator.validate(raw_data, platform)
                if not data_valid:
                    logger.warning(f"数据验证失败：platform={platform}, errors={errors}")
                    return {
                        "success": True,
                        "message": "数据验证失败",
                        "errors": errors
                    }
                
                # ========== 第 3 步：数据标准化 ==========
                logger.info("=== 第 3 步：数据标准化 ===")
                normalized_data = DataNormalizer.normalize(raw_data, platform)
            
            logger.info(f"标准化后数据: {normalized_data}")
            
            # ========== 第 4 步：Click ID 关联 ==========
            logger.info("=== 第 4 步：Click ID 关联 ===")
            click_id = normalized_data.get('click_id')
            logger.info(f"关联 Click ID: {click_id}")
            
            click_association = await ClickAssociator.associate(
                click_id,
                db
            )
            
            logger.info(f"Click 关联结果: {click_association}")
            
            # 检查 url_params 中的 fbclid 参数并上报
            if click_association and click_association.get('url_params'):
                url_params = click_association['url_params']
                ip = click_association.get('ipip')
                ua = click_association.get('user_agent')
                fbclid = url_params.get('fbclid')
                email = url_params.get('email')
                phone = url_params.get('phone')

                if fbclid:
                    logger.info(f"=== 检测到 fbclid 参数: {fbclid} ===")

                    # 调用第三方上报
                    try:
                        await send_third_party_report(
                            adsid=fbclid,
                            event="finishPayment",
                            email=email,
                            ip=ip,
                            phone=phone,
                            ua=ua,
                            source="postback"
                        )
                        logger.info(f"=== 第三方上报成功: fbclid={fbclid} ===")
                    except Exception as e:
                        logger.error(f"=== 第三方上报失败: {str(e)} ===")
            
            # ========== 第 5 步：重复检测 ==========
            logger.info("=== 第 5 步：重复检测 ===")
            conversion_id = normalized_data.get('conversion_id')
            event_name = normalized_data.get('event_name')
            logger.info(f"检测重复：conversion_id={conversion_id}, event_name={event_name}")
            
            is_dup = await DuplicateChecker.is_duplicate(
                conversion_id=conversion_id,
                db=db
            )
            
            if is_dup:
                logger.info(f"检测到重复转化，跳过处理：platform={platform}")
                return {
                    "success": True,
                    "message": "重复转化，已跳过"
                }
            
            # ========== 第 6 步：Cap 检查 ==========
            logger.info("=== 第 6 步：Cap 检查 ===")
            offer_id = click_association.get('offer_id') if click_association else None
            publisher_id = click_association.get('publisher_id') if click_association else None
            advertiser_id = click_association.get('advertiser_id') if click_association else None
            logger.info(f"Cap 检查参数：offer_id={offer_id}, publisher_id={publisher_id}, advertiser_id={advertiser_id}")
            
            cap_ok, cap_status = await CapChecker.check(
                offer_id=offer_id,
                publisher_id=publisher_id,
                advertiser_id=advertiser_id,
                db=db
            )
            
            conversion_status = 'Pending' if cap_ok else f'CapExceeded({cap_status})'
            logger.info(f"Cap 检查结果：{cap_ok}, 状态：{conversion_status}")
            
            # ========== 第 7 步：扣量计算 ==========
            logger.info("=== 第 7 步：扣量计算 ===")
            original_payout = normalized_data['payout'] or 0.0
            logger.info(f"原始 payout: {original_payout}")
            
            final_payout, deduction_info = await DiscountChecker.calculate(
                original_payout=original_payout,
                offer_id=offer_id,
                publisher_id=publisher_id,
                product_id=normalized_data['product_id'],
                client_id=normalized_data['client_id'],
                db=db
            )
            
            logger.info(f"扣量计算结果：final_payout={final_payout}, 扣量信息：{deduction_info}")
            
            # ========== 第 8 步：保存转化记录 ==========
            logger.info("=== 第 8 步：保存转化记录 ===")
            conversion = await ConversionSaver.save(
                normalized_data=normalized_data,
                click_association=click_association,
                final_payout=final_payout,
                conversion_status=conversion_status,
                db=db
            )
            
            logger.info(f"转化记录保存成功：ID={conversion.id}, conversion_id={conversion.conversion_id}")
            
            # 更新 Click 统计
            if click_association:
                logger.info("=== 更新 Click 统计 ===")
                await ConversionSaver.update_click_conversion(
                    click_association=click_association,
                    conversion_id=conversion.id,
                    db=db
                )
                logger.info("Click 统计更新成功")
            
            # ========== 第 9 步：渠道转发 ==========
            logger.info("=== 第 9 步：渠道转发 ===")
            if click_association and click_association.get('publisher'):
                logger.info(f"开始转发到渠道：publisher_id={click_association.get('publisher_id')}")
                await PostbackForwarder.forward_to_publisher(conversion, db, click_association)
                logger.info("渠道转发完成")
            else:
                logger.info("无渠道信息，跳过转发")
            
            # ========== 第 10 步：通知发送 ==========
            logger.info("=== 第 10 步：通知发送 ===")
            await PostbackNotifier.notify_conversion(conversion, db)
            logger.info("通知发送完成")
            
            # ========== 第 11 步：提交事务 ==========
            logger.info("=== 第 11 步：提交事务 ===")
            await db.commit()
            logger.info("事务提交成功")
            
            # ========== 完成 ==========
            logger.info("=== PostBack 处理完成 ===")
            logger.info(
                f"Postback 处理完成：platform={platform}, "
                f"conversion_id={conversion.id}, payout={final_payout}"
            )
            
            return {
                "success": True,
                "message": "PostBack 接收成功",
                "conversion_id": conversion.id,
                "platform": platform,
                "payout": final_payout
            }
        except Exception as e:
            # 发生异常时回滚事务
            await db.rollback()
            logger.error(f"Postback 处理失败，已回滚事务：platform={platform}, error={str(e)}", exc_info=True)
            raise
    
    @staticmethod
    async def _handle_ip_failure(
        platform: str,
        raw_data: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        处理 IP 验证失败
        
        Args:
            platform: 平台名称
            raw_data: 原始数据
            db: 数据库会话
        
        Returns:
            处理结果
        """
        conversion_id_hint = (
            raw_data.get("clk_id")
            or raw_data.get("conversion_id")
            or raw_data.get("click_id")
            or "unknown"
        )
        
        # 发送管理员通知
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
                    "⚠️ Postback IP 验证失败",
                    "",
                    f"平台：{platform}",
                    f"转化 ID/点击 ID: {conversion_id_hint}",
                    "说明：IP 为空或无法获取，已拒绝处理（不入库、不转发）。"
                ]
                
                await TelegramNotificationService.send_admin_notification(
                    message="\n".join(msg_lines),
                    telegram_chat_id=admin_config.telegram_chat_id,
                    notification_type='system_error',
                    db=db
                )
        except Exception as e:
            logger.warning(f"发送 IP 验证失败通知失败：{e}")
        
        return {
            "success": True,
            "message": "PostBack 接收成功（IP 验证失败，未记录）",
            "conversion_id": conversion_id_hint,
            "platform": platform,
            "is_test_data": True
        }


# 向后兼容：导入时自动定义 select
from sqlalchemy import select
