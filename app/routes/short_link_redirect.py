"""
短链接重定向路由模块
处理短链接的重定向逻辑，包括缓存、点击记录、占位符替换等
"""
import logging
import re
from typing import Optional, Dict, Any
from datetime import datetime
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse, quote
from collections import OrderedDict

from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.short_link_cache import (
    get_short_link_from_cache,
    set_short_link_to_cache,
    serialize_short_link
)
from app.core.short_link_click_counter import increment_click_count_async
from app.core.tracking.click_id_generator import generate_click_id_from_timestamp
from app.core.device_info import collect_request_info
from app.core.utils import get_app_now_naive, APP_TIMEZONE
from app.core.clicks_queue import enqueue_click
from app.core.offer_cache import set_offer_cache
from app.api.api_v1.endpoints.tracking import create_click_background
from app.models.models import ShortLink, Offer, Publisher, Advertiser

logger = logging.getLogger(__name__)

# 创建路由实例
router = APIRouter()


async def _replace_short_link_placeholders(
    original_url: str,
    click_id: str,
    offer_id: Optional[int],
    publisher_id: Optional[int],
    advertiser_id: Optional[int],
    request_info: dict,
    db: AsyncSession
) -> str:
    """
    替换短链接原始URL中的占位符
    
    支持的占位符：
    - {click_id}: 点击ID
    - {offer_id}: Offer ID
    - {publisher_id} 或 {channel_id}: 渠道ID
    - {advertiser_id}: 广告主ID
    - {ip}: IP地址
    - {os}: 操作系统
    - {device_type}: 设备类型
    - {country}: 国家（如果有）
    - 以及其他支持的占位符
    """
    # 使用正则表达式查找所有占位符
    pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    placeholders = re.findall(pattern, original_url)
    
    if not placeholders:
        return original_url
    
    # 构建参数值字典
    values = {
        'click_id': click_id,
        'ip': request_info.get('ip', ''),
        'os': request_info.get('os', ''),
        'device_type': request_info.get('device_type', ''),
        'country': request_info.get('country', ''),
        'user_agent': request_info.get('user_agent', ''),
        'referer': request_info.get('referer', ''),
    }
    
    # Offer、Publisher、Advertiser 字段
    if offer_id:
        values['offer_id'] = str(offer_id)
        try:
            offer_result = await db.execute(
                select(Offer).where(Offer.id == offer_id)
            )
            offer = offer_result.scalars().first()
            if offer:
                values['offer_name'] = offer.offer_name or ''
                values['advertiser_offer_id'] = offer.advertiser_offer_id or ''
                values['offer_payout'] = str(offer.payout) if offer.payout is not None else ''
                values['affiliate_payout'] = str(offer.affiliate_payout) if offer.affiliate_payout is not None else ''
                values['offer_country'] = offer.country or ''
                values['offer_category'] = offer.category or ''
                values['offer_type'] = offer.type or ''
                values['offer_status'] = offer.status or ''
        except Exception as e:
            logger.warning(f"查询Offer信息失败: offer_id={offer_id}, error={e}")
    else:
        values['offer_id'] = ''
        values['offer_name'] = ''
        values['advertiser_offer_id'] = ''
    
    # 处理 publisher_id（渠道ID）
    if publisher_id is not None:
        publisher_id_str = str(publisher_id)
        values['publisher_id'] = publisher_id_str
        values['channel_id'] = publisher_id_str
        try:
            publisher_result = await db.execute(
                select(Publisher).where(Publisher.id == publisher_id)
            )
            publisher = publisher_result.scalars().first()
            if publisher:
                values['publisher_name'] = publisher.publisher_name or ''
                values['publisher_email'] = publisher.email or ''
        except Exception as e:
            logger.warning(f"查询Publisher信息失败: publisher_id={publisher_id}, error={e}")
    else:
        values['publisher_id'] = ''
        values['channel_id'] = ''
        values['publisher_name'] = ''
        values['publisher_email'] = ''
    
    if advertiser_id:
        values['advertiser_id'] = str(advertiser_id)
        try:
            advertiser_result = await db.execute(
                select(Advertiser).where(Advertiser.id == advertiser_id)
            )
            advertiser = advertiser_result.scalars().first()
            if advertiser:
                values['advertiser_name'] = advertiser.advertiser_name or ''
                values['advertiser_email'] = advertiser.email or ''
        except Exception as e:
            logger.warning(f"查询Advertiser信息失败: advertiser_id={advertiser_id}, error={e}")
    else:
        values['advertiser_id'] = ''
        values['advertiser_name'] = ''
        values['advertiser_email'] = ''
    
    # 支持别名
    alias_map = {
        'clickid': 'click_id',
        'clickId': 'click_id',
        'clk_id': 'click_id',
        'cid': 'click_id',
        'aff_click_id': 'click_id',
        'affclickid': 'click_id',
        'publisherId': 'publisher_id',
        'publisherid': 'publisher_id',
        'channelId': 'channel_id',
        'channelid': 'channel_id',
        'sub_affid': 'channel_id',
        'subaffid': 'channel_id',
        'offerId': 'offer_id',
        'offerid': 'offer_id',
    }
    
    # 替换占位符
    result_url = original_url
    for placeholder in placeholders:
        normalized_key = placeholder.lower()
        
        if normalized_key in alias_map:
            normalized_key = alias_map[normalized_key]
        else:
            normalized_key = re.sub(r'(?<!^)(?=[A-Z])', '_', placeholder).lower()
        
        # channel_id 和 sub_affid 都映射到 publisher_id
        if normalized_key == 'channel_id' or normalized_key == 'sub_affid':
            normalized_key = 'publisher_id'
        
        value = values.get(normalized_key, '')
        
        if not value:
            # 如果值为空，记录警告但不替换（保留原始占位符）
            logger.warning(f"占位符 {{{placeholder}}} 的值为空，将保留原始占位符")
            continue
        
        encoded_value = quote(str(value), safe='')
        result_url = result_url.replace(f'{{{placeholder}}}', encoded_value)
    
    # 将URL中的所有参数名转小写
    parsed = urlparse(result_url)
    if parsed.query:
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_params_lower = {k.lower(): v for k, v in query_params.items()}
        new_query = urlencode(query_params_lower, doseq=True)
        result_url = urlunparse(parsed._replace(query=new_query))
    
    return result_url


def merge_url_params(base_url: str, query_params: dict) -> str:
    """将查询参数合并到基础URL中"""
    if not query_params:
        return base_url
    
    parsed = urlparse(base_url)
    existing_params = parse_qs(parsed.query, keep_blank_values=True)
    existing_params_lower = {k.lower(): v for k, v in existing_params.items()}
    
    # 检查占位符
    placeholder_params = {'click_id', 'offer_id', 'channel_id', 'publisher_id'}
    skip_params = set()
    for param in placeholder_params:
        placeholder_variants = [
            f'{{{param}}}',
            f'{{{param.lower()}}}',
            f'{{{param.upper()}}}',
            f'{{{param.capitalize()}}}',
        ]
        camel_case = ''.join(word.capitalize() if i > 0 else word.lower() 
                           for i, word in enumerate(param.split('_')))
        placeholder_variants.extend([
            f'{{{camel_case}}}',
            f'{{{camel_case.lower()}}}',
        ])
        
        if any(variant in base_url for variant in placeholder_variants):
            skip_params.add(param)
    
    # 分离 click_id 和其他参数
    click_id_value = None
    other_params = {}
    
    for key, value in query_params.items():
        key_lower = key.lower()
        if key_lower in skip_params:
            continue
        
        if key_lower == 'click_id':
            click_id_value = [str(v) for v in value] if isinstance(value, list) else [str(value)]
        else:
            other_params[key_lower] = [str(v) for v in value] if isinstance(value, list) else [str(value)]
    
    # 合并参数
    for key, value in other_params.items():
        existing_params_lower[key] = value
    
    if click_id_value and 'click_id' not in skip_params:
        existing_params_lower['click_id'] = click_id_value
    
    # 确保 click_id 在最前面
    ordered_params = OrderedDict()
    if 'click_id' in existing_params_lower and 'click_id' not in skip_params:
        ordered_params['click_id'] = existing_params_lower['click_id']
    
    for key, value in existing_params_lower.items():
        if key != 'click_id':
            ordered_params[key.lower()] = value
    
    new_query = urlencode(ordered_params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


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
            return await _handle_cached_redirect(
                short_code, cached_data, offer_id, channel_id,
                request, background_tasks, db, request_params
            )
        else:
            return await _handle_database_redirect(
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


async def _handle_cached_redirect(
    short_code: str,
    cached_data: dict,
    offer_id: Optional[int],
    channel_id: Optional[int],
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
    request_params: dict
) -> RedirectResponse:
    """处理缓存命中的重定向"""
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
    final_offer_id, advertiser_id = await _resolve_offer_id(offer_id, db)
    
    # 创建点击记录
    if short_link_id:
        await _create_click_record(
            click_id, short_link_id, final_offer_id, final_channel_id,
            advertiser_id, request_info, background_tasks
        )
    
    # 更新点击次数
    await increment_click_count_async(short_code)
    
    # 保存原始URL用于检查占位符
    original_url_before_replace = original_url
    
    # 替换占位符并合并参数
    original_url = await _replace_short_link_placeholders(
        original_url, click_id, final_offer_id, final_channel_id,
        advertiser_id, request_info, db
    )
    
    final_url = _build_final_url(original_url_before_replace, original_url, click_id, offer_id, channel_id,
                                 final_channel_id, request_params)
    
    # 打印最终跳转链接
    logger.info(f"[短链接重定向] 最终跳转链接: {final_url}")
    
    return RedirectResponse(url=final_url, status_code=302)


async def _handle_database_redirect(
    short_code: str,
    offer_id: Optional[int],
    channel_id: Optional[int],
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
    request_params: dict
) -> RedirectResponse:
    """处理数据库查询的重定向"""
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
    final_offer_id, advertiser_id = await _resolve_offer_id(offer_id, db)
    
    # 创建点击记录
    await _create_click_record(
        click_id, short_link.id, final_offer_id, final_channel_id,
        advertiser_id, request_info, background_tasks
    )
    
    # 更新点击次数
    await increment_click_count_async(short_code)
    
    # 保存原始URL用于检查占位符
    original_url_before_replace = original_url
    
    # 替换占位符并合并参数
    original_url = await _replace_short_link_placeholders(
        original_url, click_id, final_offer_id, final_channel_id,
        advertiser_id, request_info, db
    )
    
    final_url = _build_final_url(original_url_before_replace, original_url, click_id, offer_id, channel_id,
                                 final_channel_id, request_params)
    
    # 打印最终跳转链接
    logger.info(f"[短链接重定向] 最终跳转链接: short_code={short_code}, final_url={final_url}, click_id={click_id}")
    print(f"[短链接重定向] 最终跳转链接: short_code={short_code}, final_url={final_url}, click_id={click_id}")
    
    return RedirectResponse(url=final_url, status_code=302)


async def _resolve_offer_id(offer_id: Optional[int], db: AsyncSession) -> tuple[Optional[int], Optional[int]]:
    """解析Offer ID，返回(offer_id, advertiser_id)"""
    if not offer_id:
        return None, None
    
    try:
        # 先尝试作为主键ID查询
        offer_result = await db.execute(
            select(Offer).where(Offer.id == offer_id)
        )
        offer = offer_result.scalars().first()
        
        # 如果找不到，尝试作为上游Offer ID查询
        if not offer:
            offer_result = await db.execute(
                select(Offer).where(Offer.advertiser_offer_id == str(offer_id))
            )
            offer = offer_result.scalars().first()
        
        if offer:
            await set_offer_cache(offer.id, offer.advertiser_id, offer.offer_name)
            return offer.id, offer.advertiser_id
    except Exception as e:
        logger.warning(f"查询Offer失败: offer_id={offer_id}, error={e}")
    
    return None, None


async def _create_click_record(
    click_id: str,
    short_link_id: int,
    offer_id: Optional[int],
    publisher_id: Optional[int],
    advertiser_id: Optional[int],
    request_info: dict,
    background_tasks: BackgroundTasks
):
    """创建点击记录"""
    click_data = {
        "click_id": click_id,
        "short_link_id": short_link_id,
        "offer_id": offer_id,
        "publisher_id": publisher_id,
        "advertiser_id": advertiser_id,
        "click_time": get_app_now_naive().isoformat(),
        "ip": request_info.get('ip'),
        "user_agent": request_info.get('user_agent'),
        "referer": request_info.get('referer'),
        "country": None,
        "os": request_info.get('os'),
        "os_version": request_info.get('os_version'),
        "browser": request_info.get('browser'),
        "browser_version": request_info.get('browser_version'),
        "accept_language": request_info.get('accept_language'),
        "accept_encoding": request_info.get('accept_encoding'),
        "is_bot": request_info.get('is_bot', False),
        "device_type": request_info.get('device_type'),
        "device_brand": request_info.get('device_brand'),
        "device_model": request_info.get('device_model'),
        "url_params": request_info.get('url_params'),
        "all_headers": request_info.get('all_headers'),
        "device": request_info.get('device_type')
    }
    
    enqueued = await enqueue_click(click_data)
    if not enqueued:
        click_data['click_time'] = get_app_now_naive()
        background_tasks.add_task(create_click_background, click_data)


def _build_final_url(
    original_url_before_replace: str,
    original_url_after_replace: str,
    click_id: str,
    offer_id: Optional[int],
    channel_id: Optional[int],
    final_channel_id: Optional[int],
    request_params: dict
) -> str:
    """构建最终的重定向URL
    
    Args:
        original_url_before_replace: 替换占位符之前的原始URL（用于检查占位符）
        original_url_after_replace: 替换占位符之后的URL（用于合并参数）
        click_id: 点击ID
        offer_id: Offer ID
        channel_id: 渠道ID（URL参数）
        final_channel_id: 最终使用的渠道ID
        request_params: 请求参数
    """
    # 检查占位符（使用替换前的原始URL）
    placeholder_params_to_check = {
        'click_id': ['{click_id}', '{clickId}', '{clickid}', '{ClickId}', '{CLICK_ID}', '{aff_click_id}', '{AFF_CLICK_ID}'],
        'offer_id': ['{offer_id}', '{offerId}', '{offerid}', '{OfferId}', '{OFFER_ID}'],
        'channel_id': ['{channel_id}', '{channelId}', '{channelid}', '{ChannelId}', '{CHANNEL_ID}', '{sub_affid}', '{SUB_AFFID}'],
        'publisher_id': ['{publisher_id}', '{publisherId}', '{publisherid}', '{PublisherId}', '{PUBLISHER_ID}'],
    }
    
    has_placeholder = {}
    for param_name, placeholder_variants in placeholder_params_to_check.items():
        has_placeholder[param_name] = any(variant in original_url_before_replace for variant in placeholder_variants)
    
    # 准备要合并的参数
    request_params_with_click = {}
    
    # 如果占位符已经被替换，就不需要再添加查询参数
    for param_name, has_placeholder_flag in has_placeholder.items():
        if not has_placeholder_flag:
            # 占位符不存在，需要添加查询参数
            if param_name == 'click_id':
                request_params_with_click['click_id'] = click_id
            elif param_name == 'offer_id' and offer_id:
                request_params_with_click['offer_id'] = offer_id
            elif param_name == 'channel_id' and final_channel_id:
                if not has_placeholder.get('publisher_id', False):
                    request_params_with_click['channel_id'] = final_channel_id
            elif param_name == 'publisher_id' and final_channel_id:
                if not has_placeholder.get('channel_id', False):
                    request_params_with_click['publisher_id'] = final_channel_id
    
    # 添加其他请求参数（排除已经在占位符中使用的参数）
    param_name_mapping = {
        'click_id': ['click_id', 'aff_click_id', 'clickid', 'clickId', 'CLICK_ID', 'AFF_CLICK_ID'],
        'offer_id': ['offer_id', 'offerid', 'offerId', 'OFFER_ID'],
        'channel_id': ['channel_id', 'sub_affid', 'channelid', 'channelId', 'CHANNEL_ID', 'SUB_AFFID'],
        'publisher_id': ['publisher_id', 'publisherid', 'publisherId', 'PUBLISHER_ID'],
    }
    
    for key, value in request_params.items():
        key_lower = key.lower()
        corresponding_param_name = None
        for param_name, possible_names in param_name_mapping.items():
            if key_lower in [name.lower() for name in possible_names]:
                corresponding_param_name = param_name
                break
        
        # 如果该参数在原始URL中使用了占位符，跳过（因为已经被替换了）
        if corresponding_param_name and has_placeholder.get(corresponding_param_name, False):
            continue
        
        # 处理channel_id和publisher_id的互斥关系
        if key_lower == 'publisher_id' and has_placeholder.get('channel_id', False):
            continue
        if key_lower == 'channel_id' and has_placeholder.get('publisher_id', False):
            continue
        
        request_params_with_click[key_lower] = value
    
    # 使用替换后的URL作为基础URL
    return merge_url_params(original_url_after_replace, request_params_with_click)

