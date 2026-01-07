"""
短链接重定向请求处理模块
处理缓存命中和数据库查询两种场景的重定向逻辑
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import Request, BackgroundTasks, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.short_link_cache import (
    get_short_link_from_cache,
    set_short_link_to_cache,
    serialize_short_link
)
from app.core.short_link_click_counter import increment_click_count_async
from app.core.tracking.click_id_generator import generate_click_id_from_timestamp
from app.core.device_info import collect_request_info
from app.core.utils import get_app_now_naive, APP_TIMEZONE
from app.models.models import ShortLink
from app.routes.short_link.utils import resolve_offer_id, create_click_record
from app.routes.short_link.placeholder import replace_short_link_placeholders
from app.routes.short_link.url_builder import build_final_url

logger = logging.getLogger(__name__)


async def handle_cached_redirect(
    short_code: str,
    cached_data: dict,
    offer_id: Optional[int],
    channel_id: Optional[int],
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
    request_params: dict
) -> RedirectResponse:
    """
    处理缓存命中的短链接重定向
    
    当短链接数据在Redis缓存中命中时，使用此函数处理重定向。
    
    Args:
        short_code: 短链接代码
        cached_data: 从Redis缓存获取的短链接数据字典
        offer_id: 从URL参数获取的Offer ID（可选）
        channel_id: 从URL参数获取的渠道ID（可选）
        request: FastAPI请求对象
        background_tasks: FastAPI后台任务对象
        db: 数据库会话
        request_params: 用户请求时携带的查询参数字典
    
    Returns:
        RedirectResponse: HTTP 302重定向响应
    """
    original_url = cached_data["original_url"]
    is_active = cached_data["is_active"]
    expires_at_str = cached_data.get("expires_at")
    
    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="短链接已禁用"
        )
    
    # 检查过期
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            if expires_at.tzinfo is not None:
                expires_at = expires_at.astimezone(APP_TIMEZONE).replace(tzinfo=None)
        except (ValueError, AttributeError):
            expires_at = None
        
        now = get_app_now_naive()
        if expires_at and expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="短链接已过期"
            )
    
    if not original_url or not original_url.startswith(('http://', 'https://')):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="短链接配置错误：原始URL格式无效"
        )
    
    click_id = generate_click_id_from_timestamp()
    short_link_id = cached_data.get("id")
    if not short_link_id:
        try:
            result = await db.execute(
                select(ShortLink.id).where(ShortLink.short_code == short_code)
            )
            short_link_id = result.scalar()
        except Exception:
            short_link_id = None
    
    request_info = collect_request_info(request) if request else {}
    
    # 如果没有从URL参数传入，从短链接记录中获取offer_id和channel_id
    if not offer_id:
        offer_id = cached_data.get("offer_id")
    if not channel_id:
        channel_id = cached_data.get("channel_id")
    
    final_channel_id = channel_id
    final_offer_id, advertiser_id = await resolve_offer_id(offer_id, db)
    
    # 创建点击记录
    if short_link_id:
        await create_click_record(
            click_id, short_link_id, final_offer_id, final_channel_id,
            advertiser_id, request_info, background_tasks
        )
    
    # 更新点击次数
    await increment_click_count_async(short_code)
    
    # 保存原始URL用于检查占位符
    original_url_before_replace = original_url
    
    # 替换占位符并合并参数
    original_url_after_replace = await replace_short_link_placeholders(
        original_url, click_id, final_offer_id, final_channel_id,
        advertiser_id, request_info, db
    )
    
    final_url = build_final_url(
        original_url_before_replace, original_url_after_replace, click_id,
        offer_id, channel_id, final_channel_id, request_params,
        request_info, advertiser_id
    )
    
    # 打印最终跳转链接详细信息
    original_request_url = str(request.url) if request else "N/A"
    logger.warning("=" * 180)
    logger.warning(f"[短链接重定向] 原始点击URL: {original_request_url}")
    logger.warning(f"[短链接重定向] 短链接代码: {short_code}")
    logger.warning(f"[短链接重定向] 点击ID: {click_id}")
    logger.warning(f"[短链接重定向] Offer ID: {final_offer_id}")
    logger.warning(f"[短链接重定向] 渠道ID: {final_channel_id}")
    logger.warning(f"[短链接重定向] 广告主ID: {advertiser_id}")
    logger.warning(f"[短链接重定向] 点击携带的参数: {request_params}")
    logger.warning(f"[短链接重定向] 原始URL（替换前）: {original_url_before_replace}")
    logger.warning(f"[短链接重定向] 替换占位符后: {original_url_after_replace}")
    logger.warning(f"[短链接重定向] 最终跳转URL: {final_url}")
    logger.warning("=" * 180)
    
    return RedirectResponse(url=final_url, status_code=302)


async def handle_database_redirect(
    short_code: str,
    offer_id: Optional[int],
    channel_id: Optional[int],
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
    request_params: dict
) -> RedirectResponse:
    """
    处理数据库查询的短链接重定向
    
    当短链接数据不在Redis缓存中时，从数据库查询并处理重定向。
    
    Args:
        short_code: 短链接代码
        offer_id: 从URL参数获取的Offer ID（可选）
        channel_id: 从URL参数获取的渠道ID（可选）
        request: FastAPI请求对象
        background_tasks: FastAPI后台任务对象
        db: 数据库会话
        request_params: 用户请求时携带的查询参数字典
    
    Returns:
        RedirectResponse: HTTP 302重定向响应
    """
    result = await db.execute(
        select(ShortLink).where(ShortLink.short_code == short_code)
    )
    short_link = result.scalars().first()
    
    if not short_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"短链接不存在: {short_code}"
        )
    
    if not short_link.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="短链接已禁用"
        )
    
    # 检查过期
    if short_link.expires_at:
        expires_at = short_link.expires_at
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(APP_TIMEZONE).replace(tzinfo=None)
        now = get_app_now_naive()
        if expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="短链接已过期"
            )
    
    original_url = short_link.original_url
    if not original_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="短链接配置错误：原始URL为空"
        )
    
    original_url = original_url.strip()
    if not original_url.startswith(('http://', 'https://')):
        if original_url and not original_url.startswith('/'):
            original_url = f"https://{original_url}"
            logger.warning(f"短链接 {short_code} 的原始URL缺少协议，已自动添加https://")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"短链接配置错误：原始URL格式无效"
            )
    
    # 写入缓存
    await set_short_link_to_cache(short_code, serialize_short_link(short_link))
    
    click_id = generate_click_id_from_timestamp()
    request_info = collect_request_info(request) if request else {}
    
    # 如果没有从URL参数传入，从短链接记录中获取offer_id和channel_id
    if not offer_id:
        offer_id = short_link.offer_id
    if not channel_id:
        channel_id = short_link.channel_id
    
    final_channel_id = channel_id
    final_offer_id, advertiser_id = await resolve_offer_id(offer_id, db)
    
    # 创建点击记录
    await create_click_record(
        click_id, short_link.id, final_offer_id, final_channel_id,
        advertiser_id, request_info, background_tasks
    )
    
    # 更新点击次数
    await increment_click_count_async(short_code)
    
    # 保存原始URL用于检查占位符
    original_url_before_replace = original_url
    
    # 替换占位符并合并参数
    original_url_after_replace = await replace_short_link_placeholders(
        original_url, click_id, final_offer_id, final_channel_id,
        advertiser_id, request_info, db
    )
    
    final_url = build_final_url(
        original_url_before_replace, original_url_after_replace, click_id,
        offer_id, channel_id, final_channel_id, request_params,
        request_info, advertiser_id
    )
    
    # 打印最终跳转链接详细信息
    logger.warning("=" * 80)
    logger.warning(f"[短链接重定向] 短链接代码: {short_code}")
    logger.warning(f"[短链接重定向] 原始URL（替换前）: {original_url_before_replace}")
    logger.warning(f"[短链接重定向] 替换占位符后: {original_url_after_replace}")
    logger.warning(f"[短链接重定向] 最终跳转URL: {final_url}")
    logger.warning(f"[短链接重定向] 点击ID: {click_id}")
    logger.warning(f"[短链接重定向] Offer ID: {final_offer_id}")
    logger.warning(f"[短链接重定向] 渠道ID: {final_channel_id}")
    logger.warning(f"[短链接重定向] 广告主ID: {advertiser_id}")
    logger.warning(f"[短链接重定向] 点击携带的参数: {request_params}")
    logger.warning("=" * 80)
    
    return RedirectResponse(url=final_url, status_code=302)

