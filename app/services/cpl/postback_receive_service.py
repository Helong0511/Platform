"""Postback 回调接收入口服务。"""
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
    """Postback 回调接收入口服务"""

    async def receive_postback(
            self,
            request: Request,
            platform: str,
            db: AsyncSession,
    ):
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
