"""BFT S2S PostBack 接收接口（薄路由层）。

向后兼容路径：/bft/postback
推荐统一入口：/api/v1/postback/{platform}。

说明：处理上游转化回调、下游转发、去重诊断与 IP 白名单管理。"""
import logging

from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_postback_db
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
        db: AsyncSession = Depends(get_postback_db),
):
    """
    接收 BFT 平台 S2S Postback（GET/POST 均可，参数由服务层解析）。

    保留路径 /bft/postback 以兼容历史对接；新接入请使用 /postback/bft。
    """
    try:
        return await postback_bft_service.receive_bft_postback(request, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("接收 BFT PostBack 回调时发生错误: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Postback processing failed, please retry",
        ) from e
