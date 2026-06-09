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
2. 异常映射为 HTTP 状态码时须符合各上游平台 retry 策略
"""
import logging

from fastapi import HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.postback import PostbackProcessor
from app.core.postback.request_parser import collect_postback_raw_data
from app.core.utils import get_client_ip

logger = logging.getLogger(__name__)


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

            await PostbackProcessor.process(
                platform=platform,
                raw_data=raw_data,
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
            logger.error("接收 PostBack 回调时发生错误: %s", e, exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"处理 PostBack 回调失败: {str(e)}",
            )


postback_receive_service = PostbackReceiveService()
ReceiveHandler = PostbackReceiveService
receive_handler = postback_receive_service
