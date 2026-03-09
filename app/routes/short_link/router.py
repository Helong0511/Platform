"""
短链接重定向路由模块
定义短链接重定向的API端点
"""
import logging
from typing import Optional
import os

from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks, HTTPException, status
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.short_link_cache import get_short_link_from_cache
from app.routes.short_link.handlers import handle_cached_redirect, handle_database_redirect

logger = logging.getLogger(__name__)

# 创建FastAPI路由实例
router = APIRouter()


@router.get("/s/{short_code}",
            summary="短链接重定向（推荐）",
            tags=["短链接服务"],
            description="✅ 推荐使用的短链接重定向路由，带缓存优化，性能更好")
async def redirect_short_link_public(
    short_code: str,
    offer_id: Optional[int] = Query(None, description="Offer ID（从URL参数获取）"),
    channel_id: Optional[int] = Query(None, description="渠道ID（从URL参数获取）"),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """
    短链接重定向（公开接口，无需认证）
    
    ✅ **推荐路由**：这是系统推荐使用的短链接重定向路由
    
    性能优化：
    - 使用Redis缓存减少数据库查询，提高响应速度
    - 异步更新点击次数，不阻塞重定向
    - 适合高并发场景
    
    功能特性：
    - 支持查询参数自动合并到原始URL
    - 自动生成click_id并添加到重定向URL
    - 完整的点击记录追踪（IP、设备信息、浏览器信息等）
    """
    try:
        request_url = str(request.url)
        request_params = {k.lower(): v for k, v in request.query_params.items()}
        logger.debug(
            f"[短链接重定向] 收到请求: short_code={short_code}, "
            f"完整URL={request_url}, 查询参数={request_params}"
        )
        
        # 尝试从缓存获取
        cached_data = await get_short_link_from_cache(short_code)
        
        if cached_data:
            return await handle_cached_redirect(
                short_code, cached_data, offer_id, channel_id,
                request, background_tasks, db, request_params
            )
        else:
            return await handle_database_redirect(
                short_code, offer_id, channel_id,
                request, background_tasks, db, request_params
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[短链接重定向] 处理异常: short_code={short_code}, error={str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"短链接重定向失败: {str(e)}"
        )


@router.get("/change",
            summary="打开固定的master.html页面",
            tags=["短链接服务"])
async def open_master_html():
    """
    打开固定的master.html页面
    """
    # 优先使用服务器路径，本地开发时会自动回退到本地路径
    master_html_path = "/data/Platform/scripts/master.html"
    
    # 如果服务器路径不存在，尝试本地路径（用于开发环境）
    if not os.path.exists(master_html_path):
        master_html_path = "E:\Platform\scripts\master.html"
    
    if not os.path.exists(master_html_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="master.html文件不存在"
        )
    
    response = FileResponse(path=master_html_path)
    # 直接设置CSP头，允许内联脚本
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests;"
    return response


@router.get("/change/{short_code}",
            summary="打开master.html并跳转到指定URL",
            tags=["短链接服务"])
async def open_master_html_with_redirect(
    short_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    先打开E:\Platform\scripts\master.html，然后根据短码跳转到指定的original_url
    """
    # 尝试从缓存获取短链接信息
    cached_data = await get_short_link_from_cache(short_code)
    
    original_url = None
    
    if cached_data:
        original_url = cached_data.get("original_url")
    else:
        # 从数据库查询
        from app.models.models import ShortLink
        from sqlalchemy.future import select
        
        result = await db.execute(
            select(ShortLink).where(ShortLink.short_code == short_code)
        )
        short_link = result.scalars().first()
        
        if short_link:
            original_url = short_link.original_url
    
    if not original_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="短链接不存在或未配置原始URL"
        )
    
    # 优先使用服务器路径，本地开发时会自动回退到本地路径
    master_html_path = "/data/Platform/scripts/master.html"
    
    # 如果服务器路径不存在，尝试本地路径（用于开发环境）
    if not os.path.exists(master_html_path):
        master_html_path = "E:\Platform\scripts\master.html"
    
    if not os.path.exists(master_html_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="master.html文件不存在"
        )
    
    with open(master_html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    # 将original_url直接注入到HTML中，替换getOriginalUrl函数的返回值
    # 这样就不需要通过URL参数传递，用户就不会看到参数了
    import re
    # 替换getOriginalUrl函数，使其直接返回原始URL
    html_content = re.sub(
        r'function getOriginalUrl\(\) \{[\s\S]*?return urlParams\.get\(\'original_url\'\) \|\| "https://www\.baidu\.com";[\s\S]*?\}',
        f'function getOriginalUrl() {{ return "{original_url}"; }}',
        html_content
    )
    
    # 返回HTML内容
    from fastapi.responses import HTMLResponse
    response = HTMLResponse(content=html_content)
    # 直接设置CSP头，允许内联脚本
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests;"
    return response

