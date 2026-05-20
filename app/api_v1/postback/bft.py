"""
BFT S2S PostBack 接收接口（薄路由层）。

向后兼容路径：/bft/postback
推荐统一入口：/api/v1/postback/{platform}
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.services.cpl.postback_bft_service import postback_bft_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.api_route(
    "/bft/postback",
    methods=["GET", "POST"],
    summary="接收 BFT PostBack 回调（支持 GET 和 POST，接收任意参数）",
)
async def receive_bft_postback(
        request: Request,
        db: AsyncSession = Depends(get_db),
):
    try:
        return await postback_bft_service.receive_bft_postback(request, db)
    except Exception as e:
        logger.error("接收 BFT PostBack 回调时发生错误: %s", e, exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"处理 PostBack 回调失败：{str(e)}",
        )
