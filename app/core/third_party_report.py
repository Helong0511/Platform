"""
第三方广告上报模块
独立于其他模块，避免循环导入问题
"""
import logging
import time
import asyncio
import httpx
import hashlib

from app.core.auto_bot import send_telegram_message
from app.core.config import settings

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


async def send_third_party_report(
        adsid: str,
        event: str,
        email: str,
        ip: str,
        phone: str,
        ua: str
):
    """
    后台任务：发送第三方广告上报
    从服务器端发送，避免浏览器CORS和广告拦截器问题
    包含智能重试机制，确保网络问题时仍能成功上报

    参数要求：
    - viewWebpage 事件：email, ip, phone, ua 必须提供
    - finishPayment 事件：email, ip, phone, ua 可选
    """
    max_retries = 3
    base_delay = 1  # 基础延迟时间（秒）
    timeout = 5  # 超时时间（秒）
    failure_reasons = []  # 收集失败原因

    # 验证 viewWebpage 事件的必需参数
    if event == "viewWebpage" or event == "finishPayment":
        if not email or not ip or not phone or not ua:
            logger.error(f"[第三方上报] viewWebpage 或 finishPayment 事件缺少必需参数: email={email}, ip={ip}, phone={phone}, ua={ua}")
            raise ValueError("viewWebpage 或 finishPayment 事件需要提供 email, ip, phone, ua 参数")

    for attempt in range(max_retries):
        try:
            url = "https://hhskins.com/UniqueChannelServer/UniqueChannel"
            headers = {
                "token": "HFY2Dgs07J4YjziNPGaTSmxFrY97CN5Z",
                "Content-Type": "application/json"
            }
            send_data = {
                "adsid": adsid,
                "event": event,  # 事件类型  viewWebpage, finishPayment
                "pixid": "2105276563598069",
                "type": "Facebook",
                "unixtime": int(time.time()),
                "userData": {
                    "email": sha256_hash(email),
                    "ip": sha256_hash(ip),
                    "phone": sha256_hash(phone),
                    "ua": ua
                }
            }

            logger.warning(f"[第三方上报] 开始发送 (尝试 {attempt + 1}/{max_retries}): adsid={adsid}, ip={ip}")
            logger.warning(f"[第三方上报] 参数详情 - 原始: email={email}, phone={phone}, ip={ip}, ua={ua}")
            logger.warning(f"[第三方上报] 参数详情 - 哈希后: email_hash={sha256_hash(email)}, phone_hash={sha256_hash(phone)}, ip_hash={sha256_hash(ip)}")

            # 增加超时时间，应对网络延迟
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=send_data, headers=headers)
                logger.warning(f"[第三方上报] 响应: status={response.status_code}, content={response.text[:200]}")

                if response.status_code == 200:
                    try:
                        response_json = response.json()
                        if response_json.get("message") == "success":
                            log_id = response_json.get("logId", "")
                            logger.warning(f"[第三方上报] adsid{adsid} ✓ 成功 (尝试 {attempt + 1}/{max_retries}), logId={log_id}")
                            return
                        else:
                            error_msg = f"message: {response_json.get('message', 'unknown')}, logId: {response_json.get('logId', '')}"
                            failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                            logger.warning(
                                f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                    except Exception as parse_err:
                        error_msg = f"JSON解析失败: {str(parse_err)}, 原始响应: {response.text[:100]}"
                        failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                        logger.warning(
                            f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                else:
                    error_msg = f"状态码: {response.status_code}, 响应: {response.text[:100]}"
                    failure_reasons.append(f"尝试 {attempt + 1}: {error_msg}")
                    logger.warning(
                        f"[第三方上报] ✗ 失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")

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
