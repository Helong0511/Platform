"""
BFT S2S Postback 接收服务。

功能说明：
- 处理 BFT 平台专用回调路径：解析请求、字段别名归一化
- 非阻塞发送 Telegram 管理员通知，便于即时感知回调流量
- 委托 ``PostbackProcessor``（platform=bft）完成与通用 Postback 相同的入库流程

在系统中的位置：
- 被 BFT 专用 Postback 路由调用

注意事项：
1. BFT 字段映射变更须同步更新 Schema 与诊断工具
2. Telegram 通知失败不得影响返回「ok」给上游
"""
import asyncio
import logging
from typing import Any, Dict

from fastapi import HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.postback import PostbackProcessor
from app.core.postback.request_parser import collect_postback_raw_data
from app.core.telegram import send_telegram_message_async
from app.core.telegram_utils import truncate_message
from app.core.utils import get_app_now_naive, get_client_ip
from app.services.cpl.postback_receive_service import (
    build_postback_ok_response,
    raise_if_postback_retryable,
)

logger = logging.getLogger(__name__)

_BFT_NOTIFICATION_SAFE_KEYS = frozenset({
    "platform", "event", "eventname", "eventtype", "status",
    "conversionstatus", "payout", "originalpayout", "currency",
    "timestamp", "eventtime", "productid", "clientid",
    "offerid", "publisherid", "advertiserid",
})
_BFT_NOTIFICATION_SENSITIVE_KEY_PARTS = (
    "token", "secret", "password", "authorization", "apikey",
    "accesskey", "email", "phone", "mobile", "clickid", "clkid",
    "fbclid", "gclid", "conversionid", "deviceid", "userid", "subid",
)
_BFT_NOTIFICATION_SENSITIVE_IP_KEYS = frozenset({
    "ip", "ipaddress", "clientip", "requestip", "remoteip",
})


def _format_bft_notification_value(key: str, value: Any) -> str:
    """仅展示白名单业务字段；敏感和未知回调参数不向 Telegram 转发原值。"""
    normalized_key = "".join(char for char in key.lower() if char.isalnum())
    if (
        normalized_key in _BFT_NOTIFICATION_SENSITIVE_IP_KEYS
        or any(part in normalized_key for part in _BFT_NOTIFICATION_SENSITIVE_KEY_PARTS)
    ):
        return "[已脱敏]"
    if normalized_key not in _BFT_NOTIFICATION_SAFE_KEYS:
        return "[非白名单字段已省略]"
    if value is None:
        return "None"
    if isinstance(value, (dict, list, tuple, set)):
        return "[结构化内容已省略]"
    value_str = str(value)
    return value_str[:150] + ("..." if len(value_str) > 150 else "")


def _map_bft_click_and_event(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 BFT 及常见上游别名映射为 clk_id / event_name。

    处理器与日志统一依赖标准键名；未映射到的字段原样保留。
    """
    mapped = raw_data.copy()
    if not mapped.get("clk_id"):
        click_id = (
            mapped.get("click_id")
            or mapped.get("cid")
            or mapped.get("clickid")
            or mapped.get("clickId")
            or mapped.get("ClickId")
            or mapped.get("conversion_id")
            or mapped.get("conversionId")
        )
        if click_id:
            mapped["clk_id"] = click_id
    if not mapped.get("event_name"):
        event_name = (
            mapped.get("event_id")
            or mapped.get("eventId")
            or mapped.get("event")
            or mapped.get("eventName")
            or mapped.get("EventName")
        )
        if event_name:
            mapped["event_name"] = event_name
    return mapped


class PostbackBftService:
    """BFT Postback 回调：Telegram 即时通知 + 统一转化处理流水线。"""

    async def _notify_telegram(self, request: Request, raw_data: Dict[str, Any]) -> None:
        """
        异步发送 BFT 回调摘要至管理员 Telegram（fire-and-forget）。

        失败仅打 warning，不影响主流程入库。
        """
        try:
            event_name = raw_data.get("event_name")
            current_time = get_app_now_naive().strftime("%Y-%m-%d %H:%M:%S")

            telegram_msg = (
                f"🔔 BFT PostBack 收到数据\n\n"
                f"⏰ 时间: {current_time}\n"
                f"📡 方法: {request.method}\n"
                f"🌐 来源 IP: 已隐藏\n"
                f"🆔 Click ID: {'已隐藏' if raw_data.get('clk_id') else '未提供'}\n"
            )
            if event_name:
                telegram_msg += (
                    f"📌 事件: {_format_bft_notification_value('event_name', event_name)}\n"
                )
            telegram_msg += f"\n📋 接收到的参数 ({len(raw_data)} 个):\n"
            telegram_msg += "-" * 40 + "\n"
            if raw_data:
                for key, value in sorted(raw_data.items()):
                    value_str = _format_bft_notification_value(str(key), value)
                    telegram_msg += f"• {key}: {value_str}\n"
            else:
                telegram_msg += "无参数\n"
            if len(telegram_msg) > 4096:
                telegram_msg = truncate_message(telegram_msg)
            notification_task = asyncio.create_task(
                send_telegram_message_async(settings.TELEGRAM_ADMIN, telegram_msg)
            )

            def _log_notification_result(task: asyncio.Task) -> None:
                try:
                    sent = task.result()
                except asyncio.CancelledError:
                    logger.debug("BFT Postback Telegram 通知任务已取消")
                except Exception as exc:
                    logger.warning(
                        "BFT Postback Telegram 通知任务异常；error_type=%s",
                        type(exc).__name__,
                    )
                else:
                    if not sent:
                        logger.warning("BFT Postback Telegram 通知发送失败（发送器返回 False）")

            notification_task.add_done_callback(_log_notification_result)
        except Exception as e:
            logger.warning("发送 BFT PostBack Telegram 通知失败: error_type=%s", type(e).__name__)

    async def receive_bft_postback(
            self,
            request: Request,
            db: AsyncSession,
    ) -> Response:
        """
        BFT 回调 HTTP 入口。

        解析原始参数 → 发送 Telegram 通知 → 执行 process_bft_postback。

        Args:
            request: FastAPI 请求。
            db: 异步数据库会话。

        Returns:
            text/plain「ok」，HTTP 200。
        """
        raw_data = await collect_postback_raw_data(request)
        await self._notify_telegram(request, raw_data)
        return await self.process_bft_postback(request, raw_data, db)

    async def process_bft_postback(
            self,
            request: Request,
            raw_data: Dict[str, Any],
            db: AsyncSession,
    ) -> Response:
        """
        BFT 转化处理核心：补 IP、字段映射后交给 PostbackProcessor。

        Args:
            request: 用于提取客户端 IP 与日志上下文。
            raw_data: 已解析的回调参数字典（可含别名键）。
            db: 异步数据库会话。

        Returns:
            text/plain「ok」，HTTP 200；业务异常转为 API 异常。
        """
        try:
            client_ip = get_client_ip(request)
            if client_ip and client_ip != "unknown" and "ip" not in raw_data:
                raw_data["ip"] = client_ip

            mapped_data = _map_bft_click_and_event(raw_data)

            if not settings.is_production:
                logger.debug(
                    "BFT PostBack raw_keys_count=%s click_id_present=%s event=%s",
                    len(mapped_data),
                    bool(mapped_data.get("clk_id")),
                    mapped_data.get("event_name"),
                )
            else:
                logger.info(
                    "BFT PostBack click_id_present=%s event_name=%s",
                    bool(mapped_data.get("clk_id")),
                    mapped_data.get("event_name"),
                )

            result = await PostbackProcessor.process(
                platform="bft",
                raw_data=mapped_data,
                db=db,
                request_ip=client_ip,
            )
            raise_if_postback_retryable(result)
            return build_postback_ok_response()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "处理 BFT PostBack 回调时发生错误: error_type=%s",
                type(e).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Postback processing failed, please retry",
            )


postback_bft_service = PostbackBftService()
