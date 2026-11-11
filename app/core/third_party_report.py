"""
第三方广告上报模块
独立于其他模块，避免循环导入问题
"""
import logging
import time
import httpx
import hashlib
import json
from typing import Optional
from datetime import datetime, timedelta

from sqlalchemy import select, update, or_
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
    platform: Optional[str] = None,
) -> str:
    """构建稳定的事件身份键；同一事件的重试保持不变，不同事件互不覆盖。"""
    # ViewContent 是点击/浏览事件；Purchase 到来后补写 conversion_id 只是关联元数据，
    # 不得改变已创建 ViewContent 的幂等身份。Purchase 等转化事件仍使用 conversion_id。
    identity_conversion_id = "" if event == "ViewContent" else (conversion_id or "")
    parts = (source or "", adsid or "", event or "", identity_conversion_id)
    if platform:
        parts = (*parts, platform.strip())
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
    # 此函数尚未接收外部 event_key；必须从稳定业务字段生成，避免引用未定义局部变量。
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
                next_retry_time=get_app_now_naive(),
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
            logger.warning("[第三方上报] 并发创建冲突后读取事件日志失败：%s", type(lookup_exc).__name__)
    except Exception as e:
        logger.warning("[第三方上报] 创建日志记录失败：%s", type(e).__name__)
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
        report_params: Optional[str] = None,
        next_retry_time: Optional[datetime] = None,
        clear_next_retry_time: bool = False,
):
    """
    更新第三方上报日志记录
    """
    if not log_id:
        return
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ThirdPartyReportLog)
                .where(ThirdPartyReportLog.id == log_id)
                .with_for_update()
            )
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
                if next_retry_time is not None:
                    log_entry.next_retry_time = next_retry_time
                if clear_next_retry_time:
                    log_entry.next_retry_time = None
                await db.commit()
    except Exception as e:
        logger.warning("[第三方上报] 更新日志记录失败：%s", type(e).__name__)


async def _get_report_status(report_log_id: int) -> Optional[str]:
    """读取事件上报状态；读取失败由调用方按不可安全发送处理。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ThirdPartyReportLog.status)
            .where(ThirdPartyReportLog.id == report_log_id)
            .limit(1)
        )
        return result.scalar_one_or_none()


async def _get_report_attempt_state(report_log_id: int) -> tuple[int, int]:
    """读取累计尝试次数与总上限，供 Outbox 跨 worker 计算重试预算。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ThirdPartyReportLog.attempt_count, ThirdPartyReportLog.max_attempts)
            .where(ThirdPartyReportLog.id == report_log_id)
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            raise RuntimeError(f"第三方上报日志不存在：{report_log_id}")
        return max(0, int(row[0] or 0)), max(1, int(row[1] or 1))


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
                # PII 清理与发送认领必须在同一行锁/条件 UPDATE 上仲裁：
                # 若清理先提交，已复制到 Worker 内存的旧载荷也不得再发送。
                ThirdPartyReportLog.pii_scrubbed_at.is_(None),
                # 认领阶段即阻止耗尽预算的事件，避免空转占用 5 分钟租约。
                ThirdPartyReportLog.attempt_count < ThirdPartyReportLog.max_attempts,
                or_(
                    ThirdPartyReportLog.report_start_time.is_(None),
                    ThirdPartyReportLog.report_start_time < stale_before,
                ),
                or_(
                    ThirdPartyReportLog.next_retry_time.is_(None),
                    ThirdPartyReportLog.next_retry_time <= now,
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
        facebook_api_version: Optional[str] = "v23.0",  # 可选参数，默认与全局 FACEBOOK_API_VERSION 对齐
        report_log_id: Optional[int] = None,
        event_key: Optional[str] = None,
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
            "[第三方上报] 缺少像素凭证，暂缓 Facebook CAPI：event=%s pixel_id=%s",
            event,
            "empty" if not pixel_id else pixel_id[:10],
        )
        if report_log_id:
            now = get_app_now_naive()
            await update_report_log(
                report_log_id,
                status="failed",
                error_message="像素凭证暂不可用，Outbox 将自动重试",
                report_start_time=now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
                completed_at=now,
                next_retry_time=now + timedelta(minutes=5),
            )
            return {"success": False, "retryable": True, "reason": "missing_facebook_credentials"}
        return {
            "success": False,
            "skipped": True,
            "reason": "missing_facebook_credentials",
        }

    # 直接发送路径创建日志；事务性 Outbox 路径复用转化事务中已提交的日志行。
    using_existing_report_log = bool(report_log_id)
    if not report_log_id:
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
            amount=amount,
        )

    if not report_log_id:
        error_msg = "创建上报日志记录失败"
        logger.error(f"[第三方上报] {error_msg}")
        raise ValueError(error_msg)

    event_key = event_key or build_event_idempotency_key(source, adsid, event, conversion_id)
    try:
        claimed = await _claim_report_log(report_log_id)
        if not claimed:
            existing_status = await _get_report_status(report_log_id)
            if existing_status == "success":
                logger.info(
                    "[第三方上报] 相同事件已成功上报，跳过重复发送: report_log_id=%s event=%s",
                    report_log_id,
                    event,
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
            "[第三方上报] 事件认领失败，跳过发送：id=%s error_type=%s",
            report_log_id,
            type(claim_exc).__name__,
        )
        return {"success": False, "retryable": True, "reason": "report_claim_unavailable"}



    if using_existing_report_log:
        base_attempt_count, max_attempts_total = await _get_report_attempt_state(report_log_id)
    else:
        base_attempt_count = 0
        max_attempts_total = max_retries + (1 if use_hash else 0)
    if base_attempt_count >= max_attempts_total:
        # 不留住刚取得的租约；该事件已耗尽预算，不得继续发起外部请求。
        await update_report_log(
            report_log_id,
            status="failed",
            report_start_time=get_app_now_naive() - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
            completed_at=get_app_now_naive(),
            clear_next_retry_time=True,
        )
        return {"success": False, "retryable": False, "reason": "max_attempts_exhausted"}

    # 每次 Worker 执行的总请求数（哈希请求 + 可选非哈希兜底）不得超过
    # 数据库中剩余的累计预算，防止接近上限时仍固定发送 4 次而超额。
    remaining_attempts = max_attempts_total - base_attempt_count
    hash_attempts = min(
        max_retries,
        max(0, remaining_attempts - (1 if use_hash else 0)),
    )
    fallback_allowed = bool(use_hash and remaining_attempts > hash_attempts)

    async def _mark_failed_and_raise(error_msg: str):
        """将上报日志标为 failed 后抛出 ValueError，供上层中断流程。"""
        logger.error(f"[第三方上报] {error_msg}")
        await update_report_log(
            report_log_id,
            status="failed",
            error_message=error_msg,
            # 将租约标记为已释放，允许失败事件立即被后续重试认领。
            report_start_time=get_app_now_naive() - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
            completed_at=get_app_now_naive(),
            clear_next_retry_time=True,
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
                f"report_log_id={report_log_id}, missing_fields={missing_fields}"
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
                    logger.info("[第三方上报] 已关联 ViewContent 转化日志：report_log_id=%s", report_log_id)
                else:
                    logger.info("[第三方上报] 未找到可关联的 ViewContent 事件：report_log_id=%s", report_log_id)
        except Exception as e:
            logger.warning("[第三方上报] 关联 ViewContent 事件失败：%s", type(e).__name__)

    logger.info("[第三方上报] 使用像素配置 - Pixel ID: %s, API 版本：%s", pixel_id, api_version)
    
    for attempt in range(hash_attempts):
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
            await update_report_log(
                report_log_id,
                report_params=report_params_json,
                attempt_count=base_attempt_count + attempt + 1,
            )

            logger.info(
                "[第三方上报] 开始发送 (尝试 %s/%s): report_log_id=%s event=%s use_hash=%s",
                attempt + 1, hash_attempts, report_log_id, event, use_hash,
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
                # 第三方响应可能回显 user_data；日志只记录状态，不记录响应正文。
                logger.debug("[第三方上报] 响应状态: status=%s", response.status_code)

                if response.status_code == 200:
                    try:
                        response_json = response.json()
                        if response_json.get("events_received"):
                            log_id = response_json.get("fbtrace_id", "")
                            report_success_time = get_app_now_naive()
                            logger.info(
                                "[第三方上报] report_log_id=%s 成功 (尝试 %s/%s), fbtrace_id=%s",
                                report_log_id, attempt + 1, hash_attempts, log_id,
                            )
                            
                            await update_report_log(
                                report_log_id,
                                status="success",
                                response_status=response.status_code,
                                response_body=None,
                                log_id_from_response=log_id,
                                report_success_time=report_success_time,
                                completed_at=report_success_time,
                                clear_next_retry_time=True,
                            )
                            
                            # 当Purchase事件上报成功时，发送Telegram通知
                            if fb_event_name == "Purchase":
                                notification_message = f"💰 Purchase事件上报成功！\n"
                                notification_message += f"上报日志ID: {report_log_id}\n"
                                if amount:
                                    notification_message += f"金额: {amount} {currency if currency else ''}\n"
                                notification_message += f"时间: {report_success_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                notification_message += f"跟踪ID: {log_id}"
                                
                                # 发送Telegram通知
                                if settings.TELEGRAM_ADMIN:
                                    # 通知失败不能反向改变已经成功的第三方上报结果，
                                    # 更不能因此重新发送同一笔 Purchase 事件。
                                    try:
                                        await send_telegram_message(
                                            settings.TELEGRAM_ADMIN,
                                            notification_message,
                                        )
                                    except Exception as notify_err:
                                        logger.warning(
                                            "[第三方上报] Purchase 已成功，但 Telegram 通知失败：%s",
                                            type(notify_err).__name__,
                                        )
                                else:
                                    logger.warning("TELEGRAM_ADMIN 未配置，无法发送 Purchase 事件通知")
                            
                            return
                        else:
                            error_msg = "第三方未确认接收事件"
                            failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                            logger.warning(
                                f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                            await update_report_log(
                                report_log_id,
                                response_status=response.status_code,
                                response_body=None
                            )
                    except Exception:
                        error_msg = "第三方响应 JSON 解析失败"
                        failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                        logger.warning(
                            f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                        await update_report_log(
                            report_log_id,
                            response_status=response.status_code,
                            response_body=None
                        )
                else:
                    error_msg = f"第三方返回 HTTP {response.status_code}"
                    failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                    logger.warning(
                        f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                    await update_report_log(
                        report_log_id,
                        response_status=response.status_code,
                        response_body=None
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
            error_msg = f"请求异常（{type(e).__name__}）"
            failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
            logger.warning("[第三方上报] 请求异常（尝试 %s/%s）：%s", attempt + 1, max_retries, type(e).__name__)

        # 指数退避策略
        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)
            logger.debug("[第三方上报] 等待 %s 秒后重试...", delay)
            await asyncio.sleep(delay)

    # 构建失败原因字符串
    failure_reasons_str = "\n" + "\n".join(failure_reasons) if failure_reasons else "\n无详细信息"
    
    # 如果使用哈希失败，尝试一次不使用哈希
    if fallback_allowed:
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
            await update_report_log(
                report_log_id,
                report_params=report_params_json,
                attempt_count=base_attempt_count + hash_attempts + 1,
            )

            logger.info(
                "[第三方上报] 开始发送 (尝试 %s/%s - 不使用哈希): report_log_id=%s event=%s",
                hash_attempts + 1, hash_attempts + 1, report_log_id, event,
            )

            # 增加超时时间，应对网络延迟
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=send_data, params=params)
                # 第三方响应可能回显 user_data；日志只记录状态，不记录响应正文。
                logger.debug("[第三方上报] 响应状态: status=%s", response.status_code)

                if response.status_code == 200:
                    try:
                        response_json = response.json()
                        if response_json.get("events_received"):
                            log_id = response_json.get("fbtrace_id", "")
                            report_success_time = get_app_now_naive()
                            logger.info(
                                "[第三方上报] report_log_id=%s 成功 (尝试 %s/%s - 不使用哈希), fbtrace_id=%s",
                                report_log_id, hash_attempts + 1, hash_attempts + 1, log_id,
                            )
                            
                            await update_report_log(
                                report_log_id,
                                status="success",
                                response_status=response.status_code,
                                response_body=None,
                                log_id_from_response=log_id,
                                report_success_time=report_success_time,
                                completed_at=report_success_time,
                                clear_next_retry_time=True,
                            )
                            return
                        else:
                            error_msg = "第三方未确认接收事件"
                            failure_reasons.append(f"尝试 {max_retries + 1} (不使用哈希): {error_msg}")
                            logger.warning(
                                f"[第三方上报] ✗ 失败 (尝试 {max_retries + 1}/{max_retries + 1} - 不使用哈希): {error_msg}")
                            await update_report_log(
                                report_log_id,
                                response_status=response.status_code,
                                response_body=None
                            )
                    except Exception:
                        error_msg = "第三方响应 JSON 解析失败"
                        failure_reasons.append(f"尝试 {max_retries + 1} (不使用哈希): {error_msg}")
                        logger.warning(
                            f"[第三方上报] ✗ 失败 (尝试 {max_retries + 1}/{max_retries + 1} - 不使用哈希): {error_msg}")
                        await update_report_log(
                            report_log_id,
                            response_status=response.status_code,
                            response_body=None
                        )
                else:
                    error_msg = f"第三方返回 HTTP {response.status_code}"
                    failure_reasons.append(f"尝试 {max_retries + 1} (不使用哈希): {error_msg}")
                    logger.warning(
                        f"[第三方上报] ✗ 失败 (尝试 {max_retries + 1}/{max_retries + 1} - 不使用哈希): {error_msg}")
                    await update_report_log(
                        report_log_id,
                        response_status=response.status_code,
                        response_body=None
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
            error_msg = f"请求异常（{type(e).__name__}）"
            failure_reasons.append(f"尝试 {max_retries + 1} (不使用哈希): {error_msg}")
            logger.warning("[第三方上报] 请求异常（不使用哈希）：%s", type(e).__name__)

    # 更新失败原因字符串
    failure_reasons_str = "\n" + "\n".join(failure_reasons) if failure_reasons else "\n无详细信息"
    logger.error(
        "[第三方上报] 全部尝试失败：report_log_id=%s event=%s attempts=%s",
        report_log_id, event, len(failure_reasons),
    )

    # 失败后释放发送租约；按累计尝试次数安排退避，达到预算后转为人工重试。
    final_attempt_count = base_attempt_count + (hash_attempts + (1 if fallback_allowed else 0))
    retry_at = None
    if final_attempt_count < max_attempts_total:
        retry_delay_minutes = min(5 * (2 ** (base_attempt_count // 4)), 60)
        retry_at = get_app_now_naive() + timedelta(minutes=retry_delay_minutes)
    await update_report_log(
        report_log_id,
        status="failed",
        attempt_count=final_attempt_count,
        error_message=failure_reasons_str.strip(),
        report_start_time=get_app_now_naive() - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1),
        completed_at=get_app_now_naive(),
        next_retry_time=retry_at,
        clear_next_retry_time=retry_at is None,
    )

    # 发送告警
    try:
        await send_telegram_message(
            settings.TELEGRAM_ADMIN,
            f"⚠️ 第三方上报失败\n\n"
            f"日志ID: {report_log_id}\n"
            f"事件类型: {event}\n"
            f"尝试次数: {final_attempt_count}\n"
            f"失败原因:{failure_reasons_str}\n"
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logger.info("[第三方上报] 告警已发送")
    except Exception as notify_err:
        logger.warning("[第三方上报] 发送告警失败：%s", type(notify_err).__name__)


def is_outbox_payload_editable(report_log, now: Optional[datetime] = None) -> bool:
    """只有尚未尝试发送、失败且租约已释放的 Outbox 才允许修正发送载荷。"""
    if not getattr(report_log, "outbox_enqueued", False):
        return False
    if getattr(report_log, "pii_scrubbed_at", None) is not None:
        return False
    if getattr(report_log, "status", None) != "failed":
        return False
    if int(getattr(report_log, "attempt_count", 0) or 0) > 0:
        return False
    now = now or get_app_now_naive()
    stale_lease_time = now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1)
    report_start_time = getattr(report_log, "report_start_time", None)
    return report_start_time is None or report_start_time < stale_lease_time


async def retry_report_log(log_id: int):
    """
    将失败的持久化 Outbox 事件重新排队。

    不在请求进程中创建非持久化 asyncio task，也不从日志读取旧凭据；
    worker 在实际发送时按短链/斗篷配置引用解析当前有效凭据。
    非 Outbox 日志缺少可靠配置引用，拒绝伪装成可重试成功。
    """
    now = get_app_now_naive()
    stale_lease_time = now - timedelta(seconds=REPORT_LOG_LEASE_SECONDS + 1)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(ThirdPartyReportLog)
                .where(
                    ThirdPartyReportLog.id == log_id,
                    ThirdPartyReportLog.outbox_enqueued.is_(True),
                    ThirdPartyReportLog.status == "failed",
                    ThirdPartyReportLog.pii_scrubbed_at.is_(None),
                    or_(
                        ThirdPartyReportLog.error_message.is_(None),
                        ThirdPartyReportLog.error_message != "短链接已删除，无法解析像素配置",
                    ),
                    or_(
                        ThirdPartyReportLog.short_link_id.is_not(None),
                        (
                            ThirdPartyReportLog.cloak_name.is_not(None)
                            & ThirdPartyReportLog.short_code.is_not(None)
                        ),
                    ),
                    or_(
                        ThirdPartyReportLog.report_start_time.is_(None),
                        ThirdPartyReportLog.report_start_time < stale_lease_time,
                    ),
                )
                .values(
                    status="pending",
                    attempt_count=0,
                    response_status=None,
                    response_body=None,
                    log_id=None,
                    error_message=None,
                    report_start_time=stale_lease_time,
                    report_success_time=None,
                    completed_at=None,
                    next_retry_time=now,
                )
            )
            await db.commit()
            if (result.rowcount or 0) != 1:
                logger.info(
                    "[第三方上报] 重试未入队：日志不存在、非 Outbox、非失败状态或租约仍有效: id=%s",
                    log_id,
                )
                return False
            logger.info("[第三方上报] Outbox 事件已重新排队，等待持久化 worker：id=%s", log_id)
            return True
    except Exception as exc:
        logger.warning("[第三方上报] Outbox 重试入队失败：id=%s error_type=%s", log_id, type(exc).__name__)
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
            if getattr(log_entry, "pii_scrubbed_at", None) is not None:
                logger.warning("[第三方上报] 已按保留策略清理个人信息的日志不可重新写入载荷: id=%s", log_id)
                return False
            
            # 事件身份必须与 event_key 保持一致。
            identity_changed = (
                (adsid is not None and adsid != log_entry.adsid)
                or (event is not None and event != log_entry.event)
                or (conversion_id is not None and conversion_id != log_entry.conversion_id)
            )
            # Outbox event_key 还包含平台维度，但日志表不保存平台字段；
            # 因此不允许管理员修改已入队事件的身份字段，避免无法正确重算幂等键。
            if log_entry.outbox_enqueued and identity_changed:
                logger.warning(
                    "[第三方上报] 拒绝修改 Outbox 事件身份字段: id=%s",
                    log_id,
                )
                return False

            payload_updates_requested = any(value is not None for value in (
                email, ip, phone, ua, currency, amount, report_params, use_hash
            ))
            if (
                log_entry.outbox_enqueued
                and payload_updates_requested
                and not is_outbox_payload_editable(log_entry)
            ):
                logger.warning(
                    "[第三方上报] 已开始发送或已完成的 Outbox 载荷不可修改: id=%s attempts=%s status=%s",
                    log_id,
                    log_entry.attempt_count,
                    log_entry.status,
                )
                return False

            # 普通历史日志允许修正身份字段，但必须同步重算唯一幂等键。
            if adsid is not None:
                log_entry.adsid = adsid
            if event is not None:
                log_entry.event = event
            if conversion_id is not None:
                log_entry.conversion_id = conversion_id
            if identity_changed:
                log_entry.event_key = build_event_idempotency_key(
                    log_entry.source,
                    log_entry.adsid,
                    log_entry.event,
                    log_entry.conversion_id,
                )
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
        logger.warning("[第三方上报] 更新日志参数失败：%s", type(e).__name__)
        return False
