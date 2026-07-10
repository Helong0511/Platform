"""
Postback 回调接收入口服务。

功能说明：
- 解析 HTTP 请求中的 Postback 原始参数（query/body）
- 补充客户端 IP 后委托 ``PostbackProcessor`` 完成校验、入库与下游转发
- 对上游广告主返回固定 plain text「ok」，符合常见 S2S 回调约定

在系统中的位置：
- 被 ``app.api_v1`` Postback 公开回调路由调用

注意事项：
1. 响应须快速返回，耗时逻辑（通知、转发）应异步或后台执行
2. 可恢复错误返回 5xx 促使上游重试；业务拒绝（重复、校验失败）仍返回 200 ok
"""
import logging

from fastapi import HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postback import PostbackProcessor
from app.core.postback.request_parser import collect_postback_raw_data
from app.core.utils import get_client_ip

logger = logging.getLogger(__name__)

# 返回给上游的通用重试提示（不泄露内部细节）
_POSTBACK_RETRY_HINT = "Postback processing failed, please retry"


def raise_if_postback_retryable(result: dict) -> None:
    """S2S 可恢复失败 → HTTP 503，促使上游重试。"""
    if result.get("success") is False and result.get("retryable", True):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.get("message") or _POSTBACK_RETRY_HINT,
        )


def build_postback_ok_response() -> Response:
    """S2S 成功响应：固定 plain text ok。"""
    return Response(
        content="ok",
        media_type="text/plain; charset=utf-8",
        status_code=200,
    )


class PostbackReceiveService:
    """通用 Postback 回调接收入口，按 platform 路由至统一处理流水线。"""

    async def receive_postback(
            self,
            request: Request,
            platform: str,
            db: AsyncSession,
    ):
        """
        接收并处理指定平台的 Postback 回调。

        Args:
            request: FastAPI 请求对象，用于解析参数与 IP。
            platform: 平台标识（如 bft、各广告主 slug），传入 PostbackProcessor。
            db: 异步数据库会话。

        Returns:
            text/plain 响应，内容为「ok」，HTTP 200。
        """
        try:
            raw_data = await collect_postback_raw_data(request)
            client_ip = get_client_ip(request)
            if client_ip and client_ip != "unknown" and "ip" not in raw_data:
                raw_data["ip"] = client_ip

            result = await PostbackProcessor.process(
                platform=platform,
                raw_data=raw_data,
                db=db,
                request_ip=client_ip,
            )
            raise_if_postback_retryable(result)
            return build_postback_ok_response()
        except HTTPException:
            raise
        except Exception as e:
            logger.error("接收 PostBack 回调时发生错误: %s", e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_POSTBACK_RETRY_HINT,
            ) from e


postback_receive_service = PostbackReceiveService()
ReceiveHandler = PostbackReceiveService
receive_handler = postback_receive_service
