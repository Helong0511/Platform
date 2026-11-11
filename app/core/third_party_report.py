"""
第三方广告上报模块
独立于其他模块，避免循环导入问题
"""
import logging
import time
import asyncio
import httpx
import hashlib
import json
from typing import Optional
from datetime import datetime, timedelta

from sqlalchemy import select, update, or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telegram.message_sender import send_telegram_message_async as send_telegram_message
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.models.models import ThirdPartyReportLog
from app.core.log_utils import mask_email, mask_hash_prefix, mask_phone

logger = logging.getLogger(__name__)

REPORT_LOG_LEASE_SECONDS = 300


def sha256_hash(value: Optional[str]) -> str:
    """
    对字符串进行 SHA256 哈希处理
    Facebook 要求：先规范化（去除前后空格，转小写），然后 SHA256 哈希
    """
    if not value:
        return ""
    normalized_value = value.strip().lower()
    return hashlib.sha256(normalized_value.encode('utf-8')).hexdigest()


def build_event_idempotency_key(
    source: str,
    adsid: str,
    event: str,
    conversion_id: Optional[str] = None,
) -> str:
    """构建稳定的事件身份键；同一事件的重试保持不变，不同事件互不覆盖。"""
    parts = (source or "", adsid or "", event or "", conversion_id or "")
    # 长度前缀避免字段中出现分隔符时产生身份碰撞。
    identity = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


async def create_report_log(
        source: str,
        adsid: str,
        event: str,
        email: str,
        ip: str,
        phone: str,
        ua: str,
        max_attempts: int = 3,
        use_hash: bool = True,
        report_params: Optional[str] = None,
        conversion_id: Optional[str] = None,
        currency: Optional[str] = None,
        amount: Optional[float] = None
) -> int:
    """
    按事件身份创建上报日志；相同事件重试复用同一日志，不同事件独立留痕。
    """
    event_key = build_event_idempotency_key(source, adsid, event, conversion_id)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ThirdPartyReportLog.id)
                .where(ThirdPartyReportLog.event_key == event_key)
                .limit(1)
            )
            existing_id = result.scalar_one_or_none()
            if existing_id:
                return int(existing_id)

            log_entry = ThirdPartyReportLog(
                source=source,
                adsid=adsid,
                event=event,
                event_key=event_key,
                conversion_id=conversion_id,
                email=email,
                ip=ip,
                phone=phone,
                ua=ua,
                currency=currency,
                amount=amount,
                use_hash=use_hash,
                report_params=report_params,
                status="pending",
                attempt_count=0,
                max_attempts=max_attempts,
                created_at=get_app_now_naive(),
            )
            db.add(log_entry)
            await db.commit()
            await db.refresh(log_entry)
            return log_entry.id
    except IntegrityError:
        # 并发请求可能同时查询到不存在；唯一键负责仲裁，冲突方读取已创建记录。
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(ThirdPartyReportLog.id)
                    .where(ThirdPartyReportLog.event_key == event_key)
                    .limit(1)
                )
                existing_id = result.scalar_one_or_none()
                if existing_id:
                    return int(existing_id)
        except Exception as lookup_exc:
            logger.warning("[第三方上报] 并发创建冲突后读取事件日志失败: %s", lookup_exc)
    except Exception as e:
        logger.warning("[第三方上报] 创建日志记录失败: %s", e)
    return 0

async def update_report_log(
        log_id: int,
        status: Optional[str] = None,
        attempt_count: Optional[int] = None,
        response_status: Optional[int] = None,
        response_body: Optional[str] = None,
        log_id_from_response: Optional[str] = None,
        error_message: Optional[str] = None,
        report_start_time: Optional[datetime] = None,
        report_success_time: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        report_params: Optional[str] = None
):
    """
    更新第三方上报日志记录
    """
    if not log_id:
        return
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ThirdPartyReportLog).where(ThirdPartyReportLog.id == log_id))
            log_entry = result.scalars().first()
            if log_entry:
                if status is not None:
                    log_entry.status = status
                if attempt_count is not None:
                    log_entry.attempt_count = attempt_count
                if response_status is not None:
                    log_entry.response_status = response_status
                if response_body is not None:
                    log_entry.response_body = response_body
                if log_id_from_response is not None:
                    log_entry.log_id = log_id_from_response
                if error_message is not None:
                    log_entry.error_message = error_message
                if report_start_time is not None:
                    log_entry.report_start_time = report_start_time
                if report_success_time is not None:
                    log_entry.report_success_time = report_success_time
                if completed_at is not None:
                    log_entry.completed_at = completed_at
                if report_params is not None:
                    log_entry.report_params = report_params
                await db.commit()
    except Exception as e:
        logger.warning(f"[第三方上报] 更新日志记录失败: {e}")


async def _get_report_status(report_log_id: int) -> Optional[str]:
    """读取事件上报状态；读取失败由调用方按不可安全发送处理。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ThirdPartyReportLog.status)
            .where(ThirdPartyReportLog.id == report_log_id)
            .limit(1)
        )
        return result.scalar_one_or_none()


async def _claim_report_log(report_log_id: int, lease_seconds: int = REPORT_LOG_LEASE_SECONDS) -> bool:
    """原子认领一条待上报事件，避免并发请求同时发送同一事件。

    失败状态允许立即重试；pending 状态仅允许首次认领或租约过期后恢复。
    发送进程异常退出时，租约到期后可由后续请求接管。
    """
    now = get_app_now_naive()
    stale_before = now - timedelta(seconds=max(30, lease_seconds))
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(ThirdPartyReportLog)
            .where(
                ThirdPartyReportLog.id == report_log_id,
                ThirdPartyReportLog.status.in_(("pending", "failed")),
                or_(
                    ThirdPartyReportLog.report_start_time.is_(None),
                    ThirdPartyReportLog.report_start_time < stale_before,
                ),
            )
            .values(report_start_time=now)
        )
        await db.commit()
        return (result.rowcount or 0) == 1


async def send_third_party_report(
        adsid: str,
        event: str,
        email: Optional[str],
        ip: Optional[str],
        phone: Optional[str],
        ua: Optional[str],
        facebook_pixel_id: str,  # 必须参数
        facebook_access_token: str,  # 必须参数
        source: str = "unknown",
        use_hash: bool = True,
        conversion_id: Optional[str] = None,
        currency: Optional[str] = None,
        amount: Optional[float] = None,
        click_time: Optional[datetime] = None,
        facebook_api_version: Optional[str] = "v23.0"  # 可选参数，默认与全局 FACEBOOK_API_VERSION 对齐
):
    """
    后台任务：发送第三方广告上报
    从服务器端发送，避免浏览器 CORS 和广告拦截器问题
    包含智能重试机制，确保网络问题时仍能成功上报

    参数要求：
    - ViewContent 事件：email, ip, phone, ua 必须提供
    - Purchase 事件：email, ip, phone, ua 必须提供
    
    必须参数：
    - facebook_pixel_id: Facebook Pixel ID（必须）
    - facebook_access_token: Facebook Access Token（必须）
    
    可选参数：
    - click_time: 点击时间（datetime 对象），如果提供，将使用该时间作为 event_time
    - conversion_id: 转化 ID（Purchase 事件必需）
    - currency: 货币类型（默认为 USD）
    - amount: 金额（Purchase 事件必需）
    - facebook_api_version: Facebook API 版本（可选，默认 v21.0）
    """
    max_retries = 3
    base_delay = 1  # 基础延迟时间（秒）
    timeout = 5  # 超时时间（秒）
    failure_reasons = []  # 收集失败原因

    # 统一清理字段，避免 None 影响日志入库与参数构造
    email = (email or "").strip()
    phone = (phone or "").strip()
    ip = (ip or "").strip()
    ua = (ua or "").strip()
    adsid = (adsid or "").strip()

    # 像素凭证须由调用方显式传入（短链 / 斗篷）；不再回退全局 FACEBOOK_*
    pixel_id = (facebook_pixel_id or "").strip()
    access_token = (facebook_access_token or "").strip()
    api_version = (facebook_api_version or settings.FACEBOOK_API_VERSION or "v23.0").strip()
    if not pixel_id or not access_token:
        logger.warning(
            "[第三方上报] 缺少像素凭证，跳过 Facebook CAPI：event=%s pixel_id=%s",
            event,
            "empty" if not pixel_id else pixel_id[:10],
        )
        return {
            "success": False,
            "skipped": True,
            "reason": "missing_facebook_credentials",
        }

    # 创建上报日志记录，传递conversion_id
    report_log_id = await create_report_log(
        source=source,
        adsid=adsid,
        event=event,
        email=email,
        ip=ip,
        phone=phone,
        ua=ua,
        max_attempts=max_retries,
        use_hash=use_hash,
        conversion_id=conversion_id,
        currency=currency,
        amount=amount
    )

    if not report_log_id:
        error_msg = "创建上报日志记录失败"
        logger.error(f"[第三方上报] {error_msg}")
        raise ValueError(error_msg)

    event_key = build_event_idempotency_key(source, adsid, event, conversion_id)
    try:
        claimed = await _claim_report_log(report_log_id)
        if not claimed:
            existing_status = await _get_report_status(report_log_id)
            if existing_status == "success":
                logger.info(
                    "[第三方上报] 相同事件已成功上报，跳过重复发送: source=%s adsid=%s event=%s conversion_id=%s",
                    source,
                    adsid,
                    event,
                    conversion_id,
                )
                return {"success": True, "deduplicated": True, "report_log_id": report_log_id}
            return {
                "success": False,
                "retryable": True,
                "reason": "report_in_progress",
                "report_log_id": report_log_id,
            }
    except Exception as claim_exc:
        # 无法确认是否成功认领时禁止发送，避免并发重复上报。
        logger.error(
            "[第三方上报] 事件认领失败，跳过发送: id=%s error=%s",
            report_log_id,
            claim_exc,
            exc_info=True,
        )
        return {"success": False, "retryable": True, "reason": "report_claim_unavailable"}



    async def _mark_failed_and_raise(error_msg: str):
        """将上报日志标为 failed 后抛出 ValueError，供上层中断流程。"""
        logger.error(f"[第三方上报] {error_msg}")
        await update_report_log(
            report_log_id,
            status="failed",
            error_message=error_msg,
            # 将租约标记为已释放，允许失败事件立即被后续重试认领。
            report_start_time=get_app_now_naive() - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
            completed_at=get_app_now_naive()
        )
        raise ValueError(error_msg)

    # Purchase 事件必须提供 conversion_id
    if event == "Purchase" and not conversion_id:
        await _mark_failed_and_raise("Purchase 事件必须提供 conversion_id 参数")

    # Purchase 事件必须提供 amount
    if event == "Purchase" and amount is None:
        await _mark_failed_and_raise("Purchase 事件必须提供 amount 参数")

    # 对用户字段改为“软校验”：允许继续上报，但记录缺失字段用于排障
    if event in ("ViewContent", "Purchase"):
        missing_fields = []
        if not email:
            missing_fields.append("email")
        if not phone:
            missing_fields.append("phone")
        if not ip:
            missing_fields.append("ip")
        if not ua:
            missing_fields.append("ua")
        if missing_fields:
            logger.warning(
                f"[第三方上报] {event} 事件字段不完整，仍尝试上报: "
                f"missing_fields={missing_fields}, adsid={adsid}, conversion_id={conversion_id}"
            )

    # 如果是 Purchase 事件，更新对应的 ViewContent 事件的 conversion_id
    if event == "Purchase" and conversion_id:
        try:
            async with AsyncSessionLocal() as db:
                # 查找相同 adsid 的 ViewContent 事件
                result = await db.execute(
                    select(ThirdPartyReportLog)
                    .where(ThirdPartyReportLog.source == source)
                    .where(ThirdPartyReportLog.adsid == adsid)
                    .where(ThirdPartyReportLog.event == "ViewContent")
                    .where(ThirdPartyReportLog.conversion_id.is_(None))  # 只更新未设置 conversion_id 的记录
                )
                view_content_log = result.scalars().first()
                
                if view_content_log:
                    # 更新 ViewContent 事件的 conversion_id
                    view_content_log.conversion_id = conversion_id
                    await db.commit()
                    logger.info(f"[第三方上报] 已更新 ViewContent 事件的 conversion_id: adsid={adsid}, conversion_id={conversion_id}")
                else:
                    logger.info(f"[第三方上报] 未找到对应的 ViewContent 事件: adsid={adsid}")
        except Exception as e:
            logger.warning(f"[第三方上报] 更新 ViewContent 事件的 conversion_id 失败: {e}")

    logger.info("[第三方上报] 使用像素配置 - Pixel ID: %s, API 版本：%s", pixel_id, api_version)
    
    for attempt in range(max_retries):
        try:
            # 使用 Facebook Graph API
            url = f"https://graph.facebook.com/{api_version}/{pixel_id}/events"
            params = {
                "access_token": access_token
            }

            # 直接使用事件类型
            fb_event_name = event

            # 构建事件数据
            # 使用click_time作为event_time（如果提供），否则使用当前时间戳
            if click_time:
                event_time = int(click_time.timestamp())
            else:
                event_time = int(time.time())

            # fbc 中段时间必须与 fbclid 产生时的点击时间一致（秒级 Unix 时间戳）。
            # 若误用「发送请求时的 time.time()」而 event_time 仍为点击时间，会出现
            # event_time < fbc 内嵌时间，Meta 侧常表现为无法归因或报表中不可见。
            fbc_ts = int(click_time.timestamp()) if click_time else event_time

            # 构建用户数据
            user_data = {}
            if use_hash:
                if email:
                    user_data["em"] = sha256_hash(email)
                if phone:
                    user_data["ph"] = sha256_hash(phone)
            else:
                if email:
                    user_data["em"] = email
                if phone:
                    user_data["ph"] = phone
            if ip:
                user_data["client_ip_address"] = ip
            if ua:
                user_data["client_user_agent"] = ua

            if adsid:
                user_data["fbc"] = f"fb.1.{fbc_ts}.{adsid}"
            event_data = {
                "event_name": fb_event_name,
                "event_time": event_time,
                "action_source": "website",
                "event_id": event_key,  # 同一业务事件的重试必须复用稳定 event_id
                "user_data": user_data
            }

            # 购物事件必须添加 custom_data（Meta 要求 value + currency）
            if fb_event_name == "Purchase" and amount is not None:
                event_data["custom_data"] = {
                    "currency": (currency or "USD"),
                    "value": float(amount),
                }

            # 构建请求数据
            send_data = {
                "data": [event_data]
            }

            # 存储完整上报参数
            report_params_json = json.dumps(send_data, ensure_ascii=False)
            await update_report_log(report_log_id, report_params=report_params_json, attempt_count=attempt + 1)

            logger.info(
                "[第三方上报] 开始发送 (尝试 %s/%s): adsid=%s, ip=%s, use_hash=%s, email=%s, phone=%s",
                attempt + 1, max_retries, adsid, ip, use_hash,
                mask_email(email), mask_phone(phone),
            )
            if use_hash and (email or phone):
                logger.debug(
                    "[第三方上报] 哈希摘要: email_hash=%s, phone_hash=%s",
                    mask_hash_prefix(sha256_hash(email)),
                    mask_hash_prefix(sha256_hash(phone)),
                )

            # 增加超时时间，应对网络延迟
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=send_data, params=params)
                logger.debug(
                    "[第三方上报] 响应: status=%s, content=%s",
                    response.status_code, response.text[:200],
                )

                if response.status_code == 200:
                    try:
                        response_json = response.json()
                        if response_json.get("events_received"):
                            log_id = response_json.get("fbtrace_id", "")
                            report_success_time = get_app_now_naive()
                            logger.info(
                                "[第三方上报] adsid=%s 成功 (尝试 %s/%s), fbtrace_id=%s",
                                adsid, attempt + 1, max_retries, log_id,
                            )
                            
                            await update_report_log(
                                report_log_id,
                                status="success",
                                response_status=response.status_code,
                                response_body=response.text[:2000],
                                log_id_from_response=log_id,
                                report_success_time=report_success_time,
                                completed_at=report_success_time
                            )
                            
                            # 当Purchase事件上报成功时，发送Telegram通知
                            if fb_event_name == "Purchase":
                                notification_message = f"💰 Purchase事件上报成功！\n"
                                notification_message += f"广告事件ID: {adsid}\n"
                                if amount:
                                    notification_message += f"金额: {amount} {currency if currency else ''}\n"
                                notification_message += f"时间: {report_success_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                notification_message += f"跟踪ID: {log_id}"
                                
                                # 发送Telegram通知
                                if settings.TELEGRAM_ADMIN:
                                    await send_telegram_message(settings.TELEGRAM_ADMIN, notification_message)
                                else:
                                    logger.warning("TELEGRAM_ADMIN 未配置，无法发送 Purchase 事件通知")
                            
                            return
                        else:
                            error_msg = f"message: {response_json.get('messages', 'unknown')}, fbtrace_id: {response_json.get('fbtrace_id', '')}"
                            failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                            logger.warning(
                                f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                            await update_report_log(
                                report_log_id,
                                response_status=response.status_code,
                                response_body=response.text[:2000]
                            )
                    except Exception as parse_err:
                        error_msg = f"JSON解析失败: {str(parse_err)}, 原始响应: {response.text[:100]}"
                        failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                        logger.warning(
                            f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                        await update_report_log(
                            report_log_id,
                            response_status=response.status_code,
                            response_body=response.text[:2000]
                        )
                else:
                    error_msg = f"状态码: {response.status_code}, 响应: {response.text[:100]}"
                    failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                    logger.warning(
                        f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                    await update_report_log(
                        report_log_id,
                        response_status=response.status_code,
                        response_body=response.text[:2000]
                    )

        except httpx.TimeoutException:
            error_msg = "请求超时"
            failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
            logger.warning(f"[第三方上报] ✗ 超时 (尝试 {attempt + 1}/{max_retries})")
        except httpx.ConnectError:
            error_msg = "连接失败"
            failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
            logger.warning(f"[第三方上报] ✗ 连接失败 (尝试 {attempt + 1}/{max_retries})")
        except Exception as e:
            error_msg = f"异常: {str(e)}"
            failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
            logger.warning(f"[第三方上报] ✗ 异常 (尝试 {attempt + 1}/{max_retries}): {str(e)}")

        # 指数退避策略
        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)
            logger.debug("[第三方上报] 等待 %s 秒后重试...", delay)
            await asyncio.sleep(delay)

    # 构建失败原因字符串
    failure_reasons_str = "\n" + "\n".join(failure_reasons) if failure_reasons else "\n无详细信息"
    
    # 如果使用哈希失败，尝试一次不使用哈希
    if use_hash:
        logger.warning(f"[第三方上报] 所有哈希尝试失败，尝试一次不使用哈希...")
        try:
            # 使用 Facebook Graph API（使用自定义或全局配置）
            url = f"https://graph.facebook.com/{api_version}/{pixel_id}/events"
            params = {
                "access_token": access_token
            }
            
            # 构建用户数据（不使用哈希）
            user_data = {}
            if email:
                user_data["em"] = email
            if phone:
                user_data["ph"] = phone
            if ip:
                user_data["client_ip_address"] = ip
            if ua:
                user_data["client_user_agent"] = ua

            # 直接使用事件类型
            fb_event_name = event

            # 构建事件数据
            # 使用click_time作为event_time（如果提供），否则使用当前时间戳
            if click_time:
                event_time = int(click_time.timestamp())
            else:
                event_time = int(time.time())
            fbc_ts = int(click_time.timestamp()) if click_time else event_time
            if adsid:
                user_data["fbc"] = f"fb.1.{fbc_ts}.{adsid}"
            event_data = {
                "event_name": fb_event_name,
                "event_time": event_time,
                "action_source": "website",
                "event_id": event_key,
                "user_data": user_data
            }

            # 购物事件必须添加 custom_data（Meta 要求 value + currency）
            if fb_event_name == "Purchase" and amount is not None:
                event_data["custom_data"] = {
                    "currency": (currency or "USD"),
                    "value": float(amount),
                }

            # 构建请求数据
            send_data = {
                "data": [event_data],
                "test": False
            }

            # 存储完整上报参数
            report_params_json = json.dumps(send_data, ensure_ascii=False)
            await update_report_log(report_log_id, report_params=report_params_json, attempt_count=max_retries + 1)

            logger.info(
                "[第三方上报] 开始发送 (尝试 %s/%s - 不使用哈希): adsid=%s, ip=%s, email=%s, phone=%s",
                max_retries + 1, max_retries + 1, adsid, ip,
                mask_email(email), mask_phone(phone),
            )

            # 增加超时时间，应对网络延迟
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=send_data, params=params)
                logger.debug(
                    "[第三方上报] 响应: status=%s, content=%s",
                    response.status_code, response.text[:200],
                )

                if response.status_code == 200:
                    try:
                        response_json = response.json()
                        if response_json.get("events_received"):
                            log_id = response_json.get("fbtrace_id", "")
                            report_success_time = get_app_now_naive()
                            logger.info(
                                "[第三方上报] adsid=%s 成功 (尝试 %s/%s - 不使用哈希), fbtrace_id=%s",
                                adsid, max_retries + 1, max_retries + 1, log_id,
                            )
                            
                            await update_report_log(
                                report_log_id,
                                status="success",
                                response_status=response.status_code,
                                response_body=response.text[:2000],
                                log_id_from_response=log_id,
                                report_success_time=report_success_time,
                                completed_at=report_success_time
                            )
                            return
                        else:
                            error_msg = f"message: {response_json.get('messages', 'unknown')}, fbtrace_id: {response_json.get('fbtrace_id', '')}"
                            failure_reasons.append(f"尝试 {max_retries + 1} (不使用哈希): {error_msg}")
                            logger.warning(
                                f"[第三方上报] ✗ 失败 (尝试 {max_retries + 1}/{max_retries + 1} - 不使用哈希): {error_msg}")
                            await update_report_log(
                                report_log_id,
                                response_status=response.status_code,
                                response_body=response.text[:2000]
                            )
                    except Exception as parse_err:
                        error_msg = f"JSON解析失败: {str(parse_err)}, 原始响应: {response.text[:100]}"
                        failure_reasons.append(f"尝试 {max_retries + 1} (不使用哈希): {error_msg}")
                        logger.warning(
                            f"[第三方上报] ✗ 失败 (尝试 {max_retries + 1}/{max_retries + 1} - 不使用哈希): {error_msg}")
                        await update_report_log(
                            report_log_id,
                            response_status=response.status_code,
                            response_body=response.text[:2000]
                        )
                else:
                    error_msg = f"状态码: {response.status_code}, 响应: {response.text[:100]}"
                    failure_reasons.append(f"尝试 {max_retries + 1} (不使用哈希): {error_msg}")
                    logger.warning(
                        f"[第三方上报] ✗ 失败 (尝试 {max_retries + 1}/{max_retries + 1} - 不使用哈希): {error_msg}")
                    await update_report_log(
                        report_log_id,
                        response_status=response.status_code,
                        response_body=response.text[:2000]
                    )

        except httpx.TimeoutException:
            error_msg = "请求超时"
            failure_reasons.append(f"尝试 {max_retries + 1} (不使用哈希): {error_msg}")
            logger.warning(f"[第三方上报] ✗ 超时 (尝试 {max_retries + 1}/{max_retries + 1} - 不使用哈希)")
        except httpx.ConnectError:
            error_msg = "连接失败"
            failure_reasons.append(f"尝试 {max_retries + 1} (不使用哈希): {error_msg}")
            logger.warning(f"[第三方上报] ✗ 连接失败 (尝试 {max_retries + 1}/{max_retries + 1} - 不使用哈希)")
        except Exception as e:
            error_msg = f"异常: {str(e)}"
            failure_reasons.append(f"尝试 {max_retries + 1} (不使用哈希): {error_msg}")
            logger.warning(f"[第三方上报] ✗ 异常 (尝试 {max_retries + 1}/{max_retries + 1} - 不使用哈希): {str(e)}")

    # 更新失败原因字符串
    failure_reasons_str = "\n" + "\n".join(failure_reasons) if failure_reasons else "\n无详细信息"
    logger.error(f"[第三方上报] ❌ 全部 {len(failure_reasons)} 次尝试失败: adsid={adsid}, 失败原因:{failure_reasons_str}")

    # 更新日志记录为失败状态
    await update_report_log(
        report_log_id,
        status="failed",
        error_message=failure_reasons_str.strip(),
        # 失败后释放发送租约；下一次重试仍需通过数据库原子认领。
        report_start_time=get_app_now_naive() - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
        completed_at=get_app_now_naive()
    )

    # 发送告警
    try:
        await send_telegram_message(
            settings.TELEGRAM_ADMIN,
            f"⚠️ 第三方上报失败\n\n"
            f"AdsID: {adsid}\n"
            f"IP: {ip}\n"
            f"尝试次数: {max_retries}\n"
            f"失败原因:{failure_reasons_str}\n"
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logger.info("[第三方上报] 告警已发送")
    except Exception as notify_err:
        logger.warning(f"[第三方上报] 发送告警失败: {notify_err}")


async def retry_report_log(log_id: int):
    """
    重新上报指定的日志记录
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ThirdPartyReportLog).where(ThirdPartyReportLog.id == log_id))
            log_entry = result.scalars().first()
            
            if not log_entry:
                logger.warning(f"[第三方上报] 日志记录不存在: id={log_id}")
                return False
            
            # 重置日志状态
            log_entry.status = "pending"
            log_entry.attempt_count = 0
            log_entry.response_status = None
            log_entry.response_body = None
            log_entry.log_id = None
            log_entry.error_message = None
            log_entry.report_start_time = None
            log_entry.report_success_time = None
            log_entry.completed_at = None
            
            await db.commit()
            
            # 在后台任务中重新发送上报
            from fastapi import BackgroundTasks
            
            # 创建一个后台任务来发送上报
            async def background_send():
                """后台重试：从日志条目解析金额/币种后再次调用第三方上报 API。"""
                # ---------- 解析金额与币种 ----------
                currency = log_entry.currency or "USD"
                amount = log_entry.amount or 0.0
                
                # 如果log_entry中没有，从report_params中提取（向后兼容）
                if not currency or amount is None:
                    if log_entry.report_params:
                        try:
                            report_params = json.loads(log_entry.report_params)
                            # 处理旧的 payData 格式
                            if "payData" in report_params:
                                currency = report_params["payData"].get("currency", "USD")
                                amount = report_params["payData"].get("amount", 0.0)
                            # 处理新的 Facebook API custom_data 格式
                            elif "data" in report_params and len(report_params["data"]) > 0:
                                event_data = report_params["data"][0]
                                if "custom_data" in event_data:
                                    currency = event_data["custom_data"].get("currency", "USD")
                                    amount = event_data["custom_data"].get("value", 0.0)
                        except (KeyError, TypeError, AttributeError):
                            pass
                
                await send_third_party_report(
                    adsid=log_entry.adsid,
                    event=log_entry.event,
                    email=log_entry.email,
                    ip=log_entry.ip,
                    phone=log_entry.phone,
                    ua=log_entry.ua,
                    source=log_entry.source,
                    use_hash=log_entry.use_hash,
                    conversion_id=log_entry.conversion_id,
                    currency=currency,
                    amount=amount
                )
            asyncio.create_task(background_send())
            
            logger.info("[第三方上报] 已触发重新上报: id=%s", log_id)
            return True
            
    except Exception as e:
        logger.warning(f"[第三方上报] 重新上报失败: {e}")
        return False


async def update_report_log_params(
        log_id: int,
        adsid: Optional[str] = None,
        event: Optional[str] = None,
        conversion_id: Optional[str] = None,
        email: Optional[str] = None,
        ip: Optional[str] = None,
        phone: Optional[str] = None,
        ua: Optional[str] = None,
        currency: Optional[str] = None,
        amount: Optional[float] = None,
        report_params: Optional[str] = None,
        use_hash: Optional[bool] = None
):
    """
    更新日志记录的参数
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ThirdPartyReportLog).where(ThirdPartyReportLog.id == log_id))
            log_entry = result.scalars().first()
            
            if not log_entry:
                logger.warning(f"[第三方上报] 日志记录不存在: id={log_id}")
                return False
            
            # 更新参数
            if adsid is not None:
                log_entry.adsid = adsid
            if event is not None:
                log_entry.event = event
            if conversion_id is not None:
                log_entry.conversion_id = conversion_id
            if email is not None:
                log_entry.email = email
            if ip is not None:
                log_entry.ip = ip
            if phone is not None:
                log_entry.phone = phone
            if ua is not None:
                log_entry.ua = ua
            if currency is not None:
                log_entry.currency = currency
            if amount is not None:
                log_entry.amount = amount
            if report_params is not None:
                log_entry.report_params = report_params
            if use_hash is not None:
                log_entry.use_hash = use_hash
            
            await db.commit()
            logger.info("[第三方上报] 已更新日志参数: id=%s", log_id)
            return True
            
    except Exception as e:
        logger.warning(f"[第三方上报] 更新日志参数失败: {e}")
        return False
