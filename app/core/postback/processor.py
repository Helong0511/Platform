"""
Postback 统一处理器模块（重构版）

协调各子模块完成 Postback 处理流程：
1. IP 验证 → 2. 数据验证 → 3. 数据标准化 → 4. Click 关联 → 5. 重复检测
6. Cap 检查 → 7. 扣量计算 → 8. 保存记录 → 9. 渠道转发 → 10. 通知发送
"""
import logging
from typing import Dict, Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postback.checks.cap_checker import CapChecker
from app.core.postback.pipeline import attribution_ids_from_association
from app.core.postback.validators.ip_validator import IpValidator
from app.core.postback.validators.data_validator import DataValidator
from app.core.postback.transformers.normalizer import DataNormalizer
from app.core.postback.pipeline import (
    PostbackPipelineContext,
    step_apply_discount,
    step_associate_click,
    step_check_cap,
    step_check_duplicate,
    step_save_conversion,
)
from app.core.postback.forwarder import PostbackForwarder
from app.core.postback.notifier import PostbackNotifier
from app.models.models import AdminNotificationConfig, CloakConfig, ShortLink
from app.services.telegram_notification_service import TelegramNotificationService
from app.core.third_party_report import send_third_party_report
from app.core.url.url_params_util import (
    parse_stored_url_params,
    resolve_dp_from_url_params,
    scalar_query_value,
)

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
        logger.debug(f"原始数据键: {list(raw_data.keys()) if isinstance(raw_data, dict) else type(raw_data)}")
        
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
            
            pipe_ctx = PostbackPipelineContext(
                platform=platform,
                raw_data=raw_data,
                db=db,
                request_ip=request_ip,
                normalized_data=normalized_data,
            )
            click_association = await step_associate_click(pipe_ctx)
            click_association = pipe_ctx.click_association

            logger.info(f"Click 关联结果: {click_association}")

            # ========== 第 5 步：重复检测 ==========
            logger.info("=== 第 5 步：重复检测 ===")
            conversion_id = normalized_data.get('conversion_id')
            event_name = normalized_data.get('event_name')
            logger.info(f"检测重复：conversion_id={conversion_id}, event_name={event_name}")
            
            pipe_ctx.normalized_data = normalized_data
            is_dup = await step_check_duplicate(pipe_ctx)

            if is_dup:
                logger.info(f"检测到重复转化，跳过处理：platform={platform}")
                return {
                    "success": True,
                    "message": "重复转化，已跳过"
                }

            # 去重通过后再做第三方像素上报，避免重复 CAPI 事件
            await PostbackProcessor._send_third_party_report_if_needed(
                click_association=click_association,
                normalized_data=normalized_data,
                raw_data=raw_data,
                db=db,
            )
            
            # ========== 第 6–8 步：Cap / 扣量 / 保存（pipeline） ==========
            logger.info("=== 第 6 步：Cap 检查 ====")
            pipe_ctx.click_association = click_association
            cap_ok, cap_status = await step_check_cap(pipe_ctx)
            conversion_status = pipe_ctx.conversion_status
            logger.info(f"Cap 检查结果：{cap_ok}, 状态：{conversion_status}")

            logger.info("=== 第 7 步：扣量计算 ===")
            final_payout, deduction_info = await step_apply_discount(pipe_ctx)
            logger.info(f"扣量计算结果：final_payout={final_payout}, 扣量信息：{deduction_info}")

            if pipe_ctx.skip_save_and_forward:
                await db.commit()
                logger.info("扣量命中，已记录日志，跳过入库与下游转发")
                return {
                    "success": True,
                    "message": "转化已扣量，未入库",
                    "platform": platform,
                    "payout": 0.0,
                }

            if not cap_ok:
                pipe_ctx.final_payout = 0.0
                final_payout = 0.0

            logger.info("=== 第 8 步：保存转化记录 ====")
            try:
                conversion = await step_save_conversion(pipe_ctx)
            except IntegrityError:
                await db.rollback()
                logger.info("并发重复转化，已跳过：platform=%s", platform)
                return {
                    "success": True,
                    "message": "重复转化，已跳过",
                }
            logger.info(
                f"转化记录保存成功：ID={conversion.id}, "
                f"conversion_id={conversion.conversion_id}"
            )

            if cap_ok:
                offer_id, publisher_id, advertiser_id = attribution_ids_from_association(
                    click_association
                )
                incremented = await CapChecker.increment(
                    offer_id=offer_id,
                    publisher_id=publisher_id,
                    advertiser_id=advertiser_id,
                    db=db,
                    commit=False,
                )
                if not incremented:
                    logger.error(
                        "Cap 计数递增失败，回滚转化入库：offer_id=%s publisher_id=%s",
                        offer_id,
                        publisher_id,
                    )
                    await db.rollback()
                    return {
                        "success": False,
                        "message": "Cap 计数更新失败，转化未入库",
                    }
            
            # ========== 第 11 步：提交事务（转化 + Cap 计数原子提交） ==========
            logger.info("=== 第 11 步：提交事务 ====")
            await db.commit()
            logger.info("事务提交成功")
            
            # ========== 第 9 步：渠道转发（Cap 超限或扣量时不转发） ==========
            logger.info("=== 第 9 步：渠道转发 ====")
            try:
                if (
                    cap_ok
                    and not pipe_ctx.skip_save_and_forward
                    and click_association
                    and click_association.get('publisher_id')
                ):
                    logger.info(f"开始转发到渠道：publisher_id={click_association.get('publisher_id')}")
                    await PostbackForwarder.forward_to_publisher(conversion, db, click_association)
                    logger.info("渠道转发完成")
                else:
                    logger.info("跳过渠道转发（Cap 超限、扣量或无渠道信息）")
            except Exception as e:
                logger.warning(f"渠道转发失败：{e}", exc_info=True)
            
            # ========== 第 10 步：通知发送 ==========
            logger.info("=== 第 10 步：通知发送 ====")
            try:
                await PostbackNotifier.notify_conversion(conversion, db)
                logger.info("通知发送完成")
            except Exception as e:
                logger.warning(f"通知发送失败：{e}", exc_info=True)
            
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
    async def _send_third_party_report_if_needed(
        click_association: Optional[Dict[str, Any]],
        normalized_data: Dict[str, Any],
        raw_data: Dict[str, Any],
        db: AsyncSession,
    ) -> None:
        """去重通过后执行第三方像素上报，避免重复 CAPI 事件。"""
        if not click_association:
            return

        raw_url_params = click_association.get("url_params")
        if isinstance(raw_url_params, dict):
            url_params = raw_url_params
        elif isinstance(raw_url_params, str):
            url_params = parse_stored_url_params(raw_url_params)
        else:
            url_params = {}

        click_id = click_association.get("click_id")
        ip = click_association.get("ip")
        ua = click_association.get("user_agent")
        fbclid = scalar_query_value(url_params.get("fbclid"))
        dp = resolve_dp_from_url_params(url_params)
        email = scalar_query_value(url_params.get("email"))
        phone = scalar_query_value(url_params.get("phone"))

        amount_raw = raw_data.get("payout")
        if amount_raw is None:
            amount = 0.0
        else:
            try:
                amount = float(str(amount_raw).strip())
                if amount < 0:
                    amount = 0.0
            except (ValueError, TypeError, AttributeError):
                amount = 0.0

        if not fbclid and not dp:
            logger.debug("未检测到 fbclid/dp，跳过第三方上报")
            return

        cloak_cfg_pb = None
        if dp:
            try:
                cr_pb = await db.execute(
                    select(CloakConfig).where(CloakConfig.cloak_name == str(dp).strip())
                )
                cloak_cfg_pb = cr_pb.scalars().first()
            except Exception as exc:
                logger.warning("查询斗篷 postback 配置失败：%s", exc)

        from app.core.config import settings
        from app.services.cloak_pixel_mapping import get_cloak_pixel_config

        facebook_pixel_id = settings.FACEBOOK_PIXEL_ID
        facebook_access_token = settings.FACEBOOK_ACCESS_TOKEN
        facebook_api_version = settings.FACEBOOK_API_VERSION
        config_source = "全局配置"
        short_link = None

        short_link_id = click_association.get("short_link_id")
        if short_link_id:
            try:
                result = await db.execute(select(ShortLink).where(ShortLink.id == short_link_id))
                short_link = result.scalars().first()
                if short_link and short_link.facebook_pixel_id and short_link.facebook_access_token:
                    facebook_pixel_id = short_link.facebook_pixel_id
                    facebook_access_token = short_link.facebook_access_token
                    facebook_api_version = short_link.facebook_api_version or "v21.0"
                    config_source = f"数据库配置 (short_link_id={short_link_id})"
            except Exception as exc:
                logger.warning("查询数据库像素配置失败：%s", exc)

        if config_source == "全局配置" and dp and short_link and short_link.short_code:
            try:
                cloak_pixel_config = await get_cloak_pixel_config(
                    db=db,
                    dp=dp,
                    short_code=short_link.short_code,
                    use_cache=True,
                )
                if cloak_pixel_config:
                    facebook_pixel_id = cloak_pixel_config.get(
                        "facebook_pixel_id", settings.FACEBOOK_PIXEL_ID
                    )
                    facebook_access_token = cloak_pixel_config.get(
                        "facebook_access_token", settings.FACEBOOK_ACCESS_TOKEN
                    )
                    facebook_api_version = cloak_pixel_config.get(
                        "facebook_api_version", settings.FACEBOOK_API_VERSION
                    )
                    config_source = f"斗篷配置表[{dp}]"
            except Exception as exc:
                logger.warning("查询斗篷配置表失败：%s", exc)

        logger.info("像素配置来源：%s", config_source)

        try:
            click_time = click_association.get("click_time")
            use_cfg_pb = bool(
                cloak_cfg_pb and getattr(cloak_cfg_pb, "postback_report_enabled", False)
            )
            if use_cfg_pb:
                fb_event = (cloak_cfg_pb.postback_report_event or "Purchase").strip() or "Purchase"
                cur_send = (cloak_cfg_pb.postback_report_currency or "USD").strip().upper() or "USD"
                fixed_val = getattr(cloak_cfg_pb, "postback_report_value", None)
                try:
                    fixed_val = float(fixed_val) if fixed_val is not None else None
                except (TypeError, ValueError):
                    fixed_val = None
                if fb_event == "Purchase":
                    amt_send = fixed_val if (fixed_val is not None and fixed_val > 0) else amount
                else:
                    amt_send = None
                    cur_send = None
            else:
                fb_event = "Purchase"
                cur_send = "USD"
                amt_send = amount

            if fb_event == "Purchase" and (amt_send is None or amt_send <= 0):
                logger.warning("Purchase 金额无效，跳过第三方上报")
                return

            report_adsid = fbclid or (
                scalar_query_value(url_params.get("click_id"))
                or scalar_query_value(url_params.get("cid"))
                or (str(click_id).strip() if click_id else None)
                or (
                    str(normalized_data.get("conversion_id")).strip()
                    if normalized_data.get("conversion_id")
                    else None
                )
            )
            if not report_adsid:
                logger.warning("缺少可用 adsid，跳过第三方上报")
                return

            report_kw: Dict[str, Any] = {
                "adsid": report_adsid,
                "conversion_id": str(click_id)[:200],
                "event": fb_event,
                "email": email,
                "ip": ip,
                "phone": phone,
                "ua": ua,
                "source": "postback",
                "click_time": click_time,
                "facebook_pixel_id": facebook_pixel_id,
                "facebook_access_token": facebook_access_token,
                "facebook_api_version": facebook_api_version,
            }
            if fb_event == "Purchase":
                report_kw["currency"] = cur_send or "USD"
                report_kw["amount"] = float(amt_send)

            await send_third_party_report(**report_kw)
            logger.info(
                "第三方上报成功：adsid=%s fbclid=%s dp=%s event=%s",
                report_adsid,
                fbclid,
                dp,
                fb_event,
            )
        except Exception as exc:
            logger.error("第三方上报失败：%s", exc)

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

