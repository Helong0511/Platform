"""Postback 上游回调接收入口。"""
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_postback_db

from ..handlers import receive_handler

router = APIRouter()


@router.api_route(
    "/postback/{platform}",
    methods=["GET", "POST"],
    summary="接收任意平台的 PostBack 回调（支持 GET 和 POST，接收任意参数）",
)
async def receive_postback(
    request: Request,
    platform: str,
    db: AsyncSession = Depends(get_postback_db),
):
    return await receive_handler.receive_postback(request, platform, db)
