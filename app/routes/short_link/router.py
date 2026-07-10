"""
短链接重定向路由（薄路由层）。

功能说明：
- 注册 ``GET /s/{short_code}`` 公开重定向入口，支持 ``offer_id``、``channel_id`` 查询参数覆盖
- 优先读 Redis 短链缓存，命中走 ``handle_cached_redirect``，未命中走 ``handle_database_redirect``
- 模块加载时挂载斗篷子路由：``/change``、``/report``、``/bridge``（见各 ``register_*_routes``）

在系统中的位置：
- 由 ``app.routes.short_link`` 导出 ``router``，在 ``app.main`` 中 ``include_router``

注意事项：
1. HTTPException 原样抛出；其它异常统一映射为 500，保留浏览器可识别状态码
2. 请求参数键统一转小写后传入 handler，与 URL 构建逻辑一致
3. 本文件不写业务逻辑，新增流程应放入 handlers 或斗篷子模块
"""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.short_link_cache import get_short_link_from_cache
from app.routes.short_link.cloak_bridge import register_bridge_routes
from app.routes.short_link.cloak_change import register_cloak_change_routes
from app.routes.short_link.cloak_report import register_cloak_report_routes
from app.routes.short_link.errors import raise_short_link_bad_config
from app.routes.short_link.handlers import handle_cached_redirect, handle_database_redirect
from app.routes.short_link.short_code_validate import validate_route_short_code

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
    """
    短链接公开重定向入口（/s/{short_code}）。

    优先读 Redis 缓存命中则走 handle_cached_redirect，否则查库走 handle_database_redirect；
    异常统一映射为 404/500，保留浏览器可识别的 HTTP 状态码。
    """
    try:
        short_code = validate_route_short_code(short_code)
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
        raise_short_link_bad_config(f"短链接重定向失败: {str(e)}")


register_cloak_change_routes(router)
register_cloak_report_routes(router)
register_bridge_routes(router)
