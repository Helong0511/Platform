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
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auto_bot import send_telegram_message
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.models.models import ThirdPartyReportLog

logger = logging.getLogger(__name__)


def sha256_hash(value: str) -> str:
    """
    对字符串进行 SHA256 哈希处理
    Facebook 要求：先规范化（去除前后空格，转小写），然后 SHA256 哈希
    """
    if not value:
        return ""
    normalized_value = value.strip().lower()
    return hashlib.sha256(normalized_value.encode('utf-8')).hexdigest()


async def create_report_log(
        source: str,
        adsid: str,
        event: str,
        email: str,
        ip: str,
        phone: str,
        ua: str,
        max_attempts: int = 3,
        use_hash: bool = True
) -> int:
    """
    创建第三方上报日志记录
    """
    try:
        async with AsyncSessionLocal() as db:
            log_entry = ThirdPartyReportLog(
                source=source,
                adsid=adsid,
                event=event,
                email=email,
                ip=ip,
                phone=phone,
                ua=ua,
                use_hash=use_hash,
                status="pending",
                attempt_count=0,
                max_attempts=max_attempts,
                created_at=get_app_now_naive()
            )
            db.add(log_entry)
            await db.commit()
            await db.refresh(log_entry)
            return log_entry.id
    except Exception as e:
        logger.warning(f"[第三方上报] 创建日志记录失败: {e}")
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
        completed_at: Optional[datetime] = None
):
    """
    更新第三方上报日志记录
    """
    if not log_id:
        return
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
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
                await db.commit()
    except Exception as e:
        logger.warning(f"[第三方上报] 更新日志记录失败: {e}")


async def send_third_party_report(
        adsid: str,
        event: str,
        email: str,
        ip: str,
        phone: str,
        ua: str,
        source: str = "unknown",
        use_hash: bool = True,
        report_log_id: Optional[int] = None
):
    """
    后台任务：发送第三方广告上报
    从服务器端发送，避免浏览器CORS和广告拦截器问题
    包含智能重试机制，确保网络问题时仍能成功上报

    参数要求：
    - viewWebpage 事件：email, ip, phone, ua 必须提供
    - finishPayment 事件：email, ip, phone, ua 可选
    - report_log_id：可选，指定使用现有的日志记录进行上报
    """
    max_retries = 3
    base_delay = 1  # 基础延迟时间（秒）
    timeout = 5  # 超时时间（秒）
    failure_reasons = []  # 收集失败原因

    # 如果没有提供 report_log_id，则创建新的日志记录
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
            use_hash=use_hash
        )
    else:
        # 如果提供了 report_log_id，重置日志状态
        await update_report_log(
            report_log_id,
            status="pending",
            attempt_count=0,
            response_status=None,
            response_body=None,
            log_id_from_response=None,
            error_message=None,
            report_start_time=None,
            report_success_time=None,
            completed_at=None
        )

    # 验证 viewWebpage 事件的必需参数
    if event == "viewWebpage" or event == "finishPayment":
        if not email or not ip or not phone or not ua:
            error_msg = f"viewWebpage 或 finishPayment 事件缺少必需参数: email={email}, ip={ip}, phone={phone}, ua={ua}"
            logger.error(f"[第三方上报] {error_msg}")
            await update_report_log(
                report_log_id,
                status="failed",
                error_message=error_msg,
                completed_at=get_app_now_naive()
            )
            raise ValueError("viewWebpage 或 finishPayment 事件需要提供 email, ip, phone, ua 参数")

    report_start_time = get_app_now_naive()
    await update_report_log(report_log_id, report_start_time=report_start_time)

    for attempt in range(max_retries):
        try:
            url = "https://hhskins.com/UniqueChannelServer/UniqueChannel"
            headers = {
                "token": "HFY2Dgs07J4YjziNPGaTSmxFrY97CN5Z",
                "Content-Type": "application/json"
            }
            user_data = {
                "ua": ua
            }
            if use_hash:
                user_data["email"] = sha256_hash(email)
                user_data["ip"] = sha256_hash(ip)
                user_data["phone"] = sha256_hash(phone)
            else:
                user_data["email"] = email
                user_data["ip"] = ip
                user_data["phone"] = phone

            send_data = {
                "adsid": adsid,
                "event": event,  # 事件类型  viewWebpage, finishPayment
                "pixid": "2105276563598069",
                "type": "Facebook",
                "unixtime": int(time.time()),
                "userData": json.dumps(user_data)
            }

            logger.warning(f"[第三方上报] 开始发送 (尝试 {attempt + 1}/{max_retries}): adsid={adsid}, ip={ip}, use_hash={use_hash}")
            logger.warning(f"[第三方上报] 参数详情 - 原始: email={email}, phone={phone}, ip={ip}, ua={ua}")
            if use_hash:
                logger.warning(f"[第三方上报] 参数详情 - 哈希后: email_hash={sha256_hash(email)}, phone_hash={sha256_hash(phone)}, ip_hash={sha256_hash(ip)}")
            else:
                logger.warning(f"[第三方上报] 参数详情 - 不哈希: email={email}, phone={phone}, ip={ip}")

            await update_report_log(report_log_id, attempt_count=attempt + 1)

            # 增加超时时间，应对网络延迟
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=send_data, headers=headers)
                logger.warning(f"[第三方上报] 响应: status={response.status_code}, content={response.text[:200]}")

                if response.status_code == 200:
                    try:
                        response_json = response.json()
                        if response_json.get("message") == "success":
                            log_id = response_json.get("logId", "")
                            report_success_time = get_app_now_naive()
                            logger.warning(f"[第三方上报] adsid{adsid} ✓ 成功 (尝试 {attempt + 1}/{max_retries}), logId={log_id}")
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
                            error_msg = f"message: {response_json.get('message', 'unknown')}, logId: {response_json.get('logId', '')}"
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
            logger.warning(f"[第三方上报] 等待 {delay} 秒后重试...")
            await asyncio.sleep(delay)

    # 构建失败原因字符串
    failure_reasons_str = "\n" + "\n".join(failure_reasons) if failure_reasons else "\n无详细信息"
    logger.error(f"[第三方上报] ❌ 全部 {max_retries} 次尝试失败: adsid={adsid}, 失败原因:{failure_reasons_str}")

    # 更新日志记录为失败状态
    await update_report_log(
        report_log_id,
        status="failed",
        error_message=failure_reasons_str.strip(),
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
        logger.warning(f"[第三方上报] 告警已发送")
    except Exception as notify_err:
        logger.warning(f"[第三方上报] 发送告警失败: {notify_err}")


async def retry_report_log(log_id: int):
    """
    重新上报指定的日志记录
    """
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
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
            import asyncio
            
            # 创建一个后台任务来发送上报
            async def background_send():
                await send_third_party_report(
                    adsid=log_entry.adsid,
                    event=log_entry.event,
                    email=log_entry.email,
                    ip=log_entry.ip,
                    phone=log_entry.phone,
                    ua=log_entry.ua,
                    source=log_entry.source,
                    use_hash=log_entry.use_hash,
                    report_log_id=log_id
                )
            asyncio.create_task(background_send())
            
            logger.warning(f"[第三方上报] 已触发重新上报: id={log_id}")
            return True
            
    except Exception as e:
        logger.warning(f"[第三方上报] 重新上报失败: {e}")
        return False


async def update_report_log_params(
        log_id: int,
        adsid: Optional[str] = None,
        event: Optional[str] = None,
        email: Optional[str] = None,
        ip: Optional[str] = None,
        phone: Optional[str] = None,
        ua: Optional[str] = None,
        use_hash: Optional[bool] = None
):
    """
    更新日志记录的参数
    """
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
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
            if email is not None:
                log_entry.email = email
            if ip is not None:
                log_entry.ip = ip
            if phone is not None:
                log_entry.phone = phone
            if ua is not None:
                log_entry.ua = ua
            if use_hash is not None:
                log_entry.use_hash = use_hash
            
            await db.commit()
            logger.warning(f"[第三方上报] 已更新日志参数: id={log_id}")
            return True
            
    except Exception as e:
        logger.warning(f"[第三方上报] 更新日志参数失败: {e}")
        return False
