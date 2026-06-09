"""
短链接重定向请求处理模块。

功能说明：
- ``handle_cached_redirect``：Redis 缓存命中时校验状态/过期、替换占位符、写点击、302 跳转
- ``handle_database_redirect``：缓存未命中时查库、回写缓存，其余流程与缓存路径一致
- ``log_redirect_details``：以 WARNING 级别输出完整重定向链路日志，便于线上排查

处理流程（两条路径共用）：
1. 校验短链启用与过期 → 2. 解析 Offer/渠道 → 3. 生成 click_id
4. 占位符替换 → 5. 构建最终 URL → 6. 异步写点击 → 7. 递增点击计数 → 8. 302

在系统中的位置：
- 由 ``router.redirect_short_link_public`` 调用；依赖 ``placeholder``、``url_builder``、``utils``

注意事项：
1. 缓存路径若缺少 short_link_id 会回查数据库补全，避免点击记录丢失主键
2. 原始 URL 缺协议时数据库路径会尝试补 ``https://``，缓存路径则直接 500
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.device_info import collect_request_info
from app.core.short_link_cache import (
    set_short_link_to_cache,
    serialize_short_link
)
from app.core.short_link_click_counter import increment_click_count_async
from app.core.tracking.click_id_generator import generate_click_id_unified
from app.core.utils import get_app_now_naive, APP_TIMEZONE
from app.models.models import ShortLink
from app.routes.short_link.placeholder import replace_short_link_placeholders
from app.routes.short_link.url_builder import build_final_url
from app.routes.short_link.errors import raise_short_link_bad_config, raise_short_link_not_found
from app.routes.short_link.utils import (
    resolve_offer_id,
    resolve_default_publisher_for_offer,
    create_click_record,
)

logger = logging.getLogger(__name__)


def log_redirect_details(
        short_code: str,
        click_id: str,
        final_offer_id: Optional[int],
        final_channel_id: Optional[int],
        advertiser_id: Optional[int],
        request_params: dict,
        original_url_before_replace: str,
        original_url_after_replace: str,
        final_url: str,
        request: Optional[Request] = None
) -> None:
    """
    记录短链接重定向的详细信息
    
    Args:
        short_code: 短链接代码
        click_id: 点击ID
        final_offer_id: 最终Offer ID
        final_channel_id: 最终渠道ID
        advertiser_id: 广告主ID
        request_params: 点击携带的参数
        original_url_before_replace: 原始URL（替换前）
        original_url_after_replace: 替换占位符后
        final_url: 最终跳转URL
        request: FastAPI请求对象（可选）
    """
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
        raise_short_link_not_found("短链接已禁用")

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
            raise_short_link_not_found("短链接已过期")

    if not original_url or not original_url.startswith(('http://', 'https://')):
        raise_short_link_bad_config("短链接配置错误：原始URL格式无效")

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
    if final_channel_id is None and final_offer_id is not None:
        fb = await resolve_default_publisher_for_offer(final_offer_id, db)
        if fb is not None:
            final_channel_id = fb

    click_id = generate_click_id_unified(
        offer_id=final_offer_id,
        publisher_id=final_channel_id,
        advertiser_id=advertiser_id,
        short_link_id=short_link_id,
        url_params=request_info.get("url_params_dict") if isinstance(request_info.get("url_params_dict"), dict) else None,
        for_short_link=True,
    )

    # 保存原始URL用于检查占位符
    original_url_before_replace = original_url

    # 替换占位符并合并参数
    original_url_after_replace = await replace_short_link_placeholders(
        original_url, click_id, final_offer_id, final_channel_id,
        advertiser_id, request_info, db
    )

    final_url = build_final_url(
        original_url_before_replace,
        original_url_after_replace,
        click_id,
        final_offer_id,
        final_channel_id,
        request_params,
        request_info,
        advertiser_id,
    )

    # 获取原始请求URL
    original_request_url = str(request.url) if request else None

    # 创建点击记录（传入原始请求URL和最终跳转URL）
    if short_link_id:
        await create_click_record(
            click_id, short_link_id, final_offer_id, final_channel_id,
            advertiser_id, request_info, background_tasks,
            original_request_url=original_request_url,
            final_redirect_url=final_url
        )

    # 更新点击次数
    await increment_click_count_async(short_code)

    # 打印最终跳转链接详细信息
    log_redirect_details(
        short_code=short_code,
        click_id=click_id,
        final_offer_id=final_offer_id,
        final_channel_id=final_channel_id,
        advertiser_id=advertiser_id,
        request_params=request_params,
        original_url_before_replace=original_url_before_replace,
        original_url_after_replace=original_url_after_replace,
        final_url=final_url,
        request=request
    )

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
        raise_short_link_not_found(f"短链接不存在: {short_code}")

    if not short_link.is_active:
        raise_short_link_not_found("短链接已禁用")

    # 检查过期
    if short_link.expires_at:
        expires_at = short_link.expires_at
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(APP_TIMEZONE).replace(tzinfo=None)
        now = get_app_now_naive()
        if expires_at < now:
            raise_short_link_not_found("短链接已过期")

    original_url = short_link.original_url
    if not original_url:
        raise_short_link_bad_config("短链接配置错误：原始URL为空")

    original_url = original_url.strip()
    if not original_url.startswith(('http://', 'https://')):
        if original_url and not original_url.startswith('/'):
            original_url = f"https://{original_url}"
            logger.warning(f"短链接 {short_code} 的原始URL缺少协议，已自动添加https://")
        else:
            raise_short_link_bad_config("短链接配置错误：原始URL格式无效")

    # 写入缓存
    await set_short_link_to_cache(short_code, serialize_short_link(short_link))

    request_info = collect_request_info(request) if request else {}

    # 如果没有从URL参数传入，从短链接记录中获取offer_id和channel_id
    if not offer_id:
        offer_id = short_link.offer_id
    if not channel_id:
        channel_id = short_link.channel_id

    final_channel_id = channel_id
    final_offer_id, advertiser_id = await resolve_offer_id(offer_id, db)
    if final_channel_id is None and final_offer_id is not None:
        fb = await resolve_default_publisher_for_offer(final_offer_id, db)
        if fb is not None:
            final_channel_id = fb

    click_id = generate_click_id_unified(
        offer_id=final_offer_id,
        publisher_id=final_channel_id,
        advertiser_id=advertiser_id,
        short_link_id=short_link.id,
        url_params=request_info.get("url_params_dict") if isinstance(request_info.get("url_params_dict"), dict) else None,
        for_short_link=True,
    )

    # 保存原始URL用于检查占位符
    original_url_before_replace = original_url

    # 替换占位符并合并参数
    original_url_after_replace = await replace_short_link_placeholders(
        original_url, click_id, final_offer_id, final_channel_id,
        advertiser_id, request_info, db
    )

    final_url = build_final_url(
        original_url_before_replace,
        original_url_after_replace,
        click_id,
        final_offer_id,
        final_channel_id,
        request_params,
        request_info,
        advertiser_id,
    )

    # 获取原始请求URL
    original_request_url = str(request.url) if request else None

    # 创建点击记录（传入原始请求URL和最终跳转URL）
    await create_click_record(
        click_id, short_link.id, final_offer_id, final_channel_id,
        advertiser_id, request_info, background_tasks,
        original_request_url=original_request_url,
        final_redirect_url=final_url
    )

    # 更新点击次数
    await increment_click_count_async(short_code)

    # 打印最终跳转链接详细信息
    log_redirect_details(
        short_code=short_code,
        click_id=click_id,
        final_offer_id=final_offer_id,
        final_channel_id=final_channel_id,
        advertiser_id=advertiser_id,
        request_params=request_params,
        original_url_before_replace=original_url_before_replace,
        original_url_after_replace=original_url_after_replace,
        final_url=final_url,
        request=request
    )

    return RedirectResponse(url=final_url, status_code=302)
