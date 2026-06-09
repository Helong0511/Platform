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
import json
import logging
from typing import Any, Dict

from fastapi import HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.postback import PostbackProcessor
from app.core.postback.request_parser import collect_postback_raw_data
from app.core.telegram import send_telegram_message_async
from app.core.telegram_utils import truncate_message
from app.core.utils import get_app_now_naive, get_client_ip

logger = logging.getLogger(__name__)


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
            client_ip = get_client_ip(request)
            if client_ip == "unknown":
                client_ip = "未知"
            clk_id = raw_data.get("clk_id")
            event_name = raw_data.get("event_name")
            current_time = get_app_now_naive().strftime("%Y-%m-%d %H:%M:%S")

            telegram_msg = (
                f"🔔 BFT PostBack 收到数据\n\n"
                f"⏰ 时间: {current_time}\n"
                f"📡 方法: {request.method}\n"
                f"🌐 IP: {client_ip}\n"
            )
            if event_name:
                telegram_msg += f"📌 事件: {event_name}\n"
            if clk_id:
                telegram_msg += f"🆔 Click ID: {clk_id}\n"
            telegram_msg += f"\n📋 接收到的参数 ({len(raw_data)} 个):\n"
            telegram_msg += "-" * 40 + "\n"
            if raw_data:
                for key, value in sorted(raw_data.items()):
                    if value is None:
                        value_str = "None"
                    elif isinstance(value, (dict, list)):
                        try:
                            value_str = json.dumps(value, ensure_ascii=False)
                        except Exception:
                            value_str = str(value)
                    else:
                        value_str = str(value)
                    if len(value_str) > 150:
                        value_str = value_str[:150] + "..."
                    telegram_msg += f"• {key}: {value_str}\n"
            else:
                telegram_msg += "无参数\n"
            if len(telegram_msg) > 4096:
                telegram_msg = truncate_message(telegram_msg)
            asyncio.create_task(
                send_telegram_message_async(settings.TELEGRAM_ADMIN, telegram_msg)
            )
        except Exception as e:
            logger.warning("发送 BFT PostBack Telegram 通知失败: %s", e)

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
                    "BFT PostBack raw keys=%s clk_id=%s event=%s",
                    list(mapped_data.keys()),
                    mapped_data.get("clk_id"),
                    mapped_data.get("event_name"),
                )
            else:
                logger.info(
                    "BFT PostBack clk_id=%s event_name=%s",
                    mapped_data.get("clk_id"),
                    mapped_data.get("event_name"),
                )

            await PostbackProcessor.process(
                platform="bft",
                raw_data=mapped_data,
                db=db,
                request_ip=client_ip,
            )
            return Response(
                content="ok",
                media_type="text/plain; charset=utf-8",
                status_code=200,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(
                "处理 BFT PostBack 回调时发生错误: %s: %s",
                type(e).__name__,
                str(e)[:200],
            )
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"处理 PostBack 回调失败：{str(e)}",
            )


postback_bft_service = PostbackBftService()
