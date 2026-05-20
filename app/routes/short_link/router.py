"""
短链接重定向路由（薄路由层）
"""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.short_link_cache import get_short_link_from_cache
from app.routes.short_link.cloak_bridge import register_bridge_routes
from app.routes.short_link.cloak_change import register_cloak_change_routes
from app.routes.short_link.cloak_report import register_cloak_report_routes
from app.routes.short_link.handlers import handle_cached_redirect, handle_database_redirect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/s/{short_code}",
    summary="短链接重定向（推荐）",
    tags=["短链接服务"],
    description="推荐使用的短链接重定向路由，带缓存优化",
)
async def redirect_short_link_public(
        short_code: str,
        offer_id: Optional[int] = Query(None, description="Offer ID（从URL参数获取）"),
        channel_id: Optional[int] = Query(None, description="渠道ID（从URL参数获取）"),
        request: Request = None,
        background_tasks: BackgroundTasks = None,
        db: AsyncSession = Depends(get_db),
):
    try:
        request_url = str(request.url)
        request_params = {k.lower(): v for k, v in request.query_params.items()}
        logger.warning(
            "[短链接重定向] 收到请求: short_code=%s URL=%s params=%s",
            short_code,
            request_url,
            request_params,
        )
        cached_data = await get_short_link_from_cache(short_code)
        if cached_data:
            return await handle_cached_redirect(
                short_code,
                cached_data,
                offer_id,
                channel_id,
                request,
                background_tasks,
                db,
                request_params,
            )
        return await handle_database_redirect(
            short_code,
            offer_id,
            channel_id,
            request,
            background_tasks,
            db,
            request_params,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[短链接重定向] 处理异常: short_code=%s error=%s",
            short_code,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"短链接重定向失败: {str(e)}",
        )


register_cloak_change_routes(router)
register_cloak_report_routes(router)
register_bridge_routes(router)
