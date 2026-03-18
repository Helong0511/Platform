"""
占位符替换服务
处理短链接URL中的占位符替换逻辑
"""
import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse, quote

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import Offer, Publisher, Advertiser

logger = logging.getLogger(__name__)

# 占位符别名映射表
PLACEHOLDER_ALIAS_MAP = {
    # click_id 的别名
    'clickid': 'click_id',
    'clickId': 'click_id',
    'clk_id': 'click_id',
    'cid': 'click_id',
    'aff_click_id': 'click_id',
    'affclickid': 'click_id',

    # publisher_id 的别名
    'publisherId': 'publisher_id',
    'publisherid': 'publisher_id',

    # channel_id 的别名
    'channelId': 'channel_id',
    'channelid': 'channel_id',
    'sub_affid': 'channel_id',
    'subaffid': 'channel_id',

    # offer_id 的别名
    'offerId': 'offer_id',
    'offerid': 'offer_id',
}


async def replace_short_link_placeholders(
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
    
    这是短链接系统的核心功能之一，用于将原始URL中的占位符（如 {click_id}、{channel_id}）
    替换为实际的值。支持多种占位符格式和别名。
    
    Args:
        original_url: 原始URL字符串，可能包含占位符
        click_id: 系统生成的唯一点击ID
        offer_id: Offer的数据库主键ID（可选）
        publisher_id: 渠道（Publisher）的数据库主键ID（可选）
        advertiser_id: 广告主的数据库主键ID（可选）
        request_info: 请求信息字典
        db: 数据库异步会话
    
    Returns:
        替换后的URL字符串，所有占位符已被替换为实际值
    """
    # 使用正则表达式查找所有占位符
    pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    placeholders = re.findall(pattern, original_url)

    # 如果没有找到占位符，直接返回原始URL
    if not placeholders:
        return original_url

    # 构建基础占位符值字典
    values = {
        'click_id': click_id,
        'ip': request_info.get('ip', ''),
        'os': request_info.get('os', ''),
        'device_type': request_info.get('device_type', ''),
        'country': request_info.get('country', ''),
        'user_agent': request_info.get('user_agent', ''),
        'referer': request_info.get('referer', ''),
    }

    # 并行查询数据库（优化性能）
    query_tasks = []

    # Offer 查询任务
    if offer_id:
        values['offer_id'] = str(offer_id)

        async def query_offer():
            try:
                offer_result = await db.execute(
                    select(Offer).where(Offer.id == offer_id)
                )
                return offer_result.scalars().first()
            except Exception as e:
                logger.warning(f"查询Offer信息失败: offer_id={offer_id}, error={e}")
                return None

        query_tasks.append(('offer', query_offer()))
    else:
        values['offer_id'] = ''
        values['offer_name'] = ''
        values['advertiser_offer_id'] = ''

    # Publisher 查询任务
    if publisher_id is not None:
        publisher_id_str = str(publisher_id)
        values['publisher_id'] = publisher_id_str
        values['channel_id'] = publisher_id_str

        async def query_publisher():
            try:
                publisher_result = await db.execute(
                    select(Publisher).where(Publisher.id == publisher_id)
                )
                return publisher_result.scalars().first()
            except Exception as e:
                logger.warning(f"查询Publisher信息失败: publisher_id={publisher_id}, error={e}")
                return None

        query_tasks.append(('publisher', query_publisher()))
    else:
        values['publisher_id'] = ''
        values['channel_id'] = ''
        values['publisher_name'] = ''
        values['publisher_email'] = ''

    # Advertiser 查询任务
    if advertiser_id:
        values['advertiser_id'] = str(advertiser_id)

        async def query_advertiser():
            try:
                advertiser_result = await db.execute(
                    select(Advertiser).where(Advertiser.id == advertiser_id)
                )
                return advertiser_result.scalars().first()
            except Exception as e:
                logger.warning(f"查询Advertiser信息失败: advertiser_id={advertiser_id}, error={e}")
                return None

        query_tasks.append(('advertiser', query_advertiser()))
    else:
        values['advertiser_id'] = ''
        values['advertiser_name'] = ''
        values['advertiser_email'] = ''

    # 并行执行所有查询
    if query_tasks:
        results = await asyncio.gather(*[task[1] for task in query_tasks], return_exceptions=True)

        # 处理查询结果
        for i, (entity_type, _) in enumerate(query_tasks):
            result = results[i]

            if isinstance(result, Exception) or result is None:
                continue

            if entity_type == 'offer':
                offer = result
                if offer:
                    values['offer_name'] = offer.offer_name or ''
                    values['advertiser_offer_id'] = offer.advertiser_offer_id or ''
                    values['offer_payout'] = str(offer.payout) if offer.payout is not None else ''
                    values['affiliate_payout'] = str(
                        offer.affiliate_payout) if offer.affiliate_payout is not None else ''
                    values['offer_country'] = offer.country or ''
                    values['offer_category'] = offer.category or ''
                    values['offer_type'] = offer.type or ''
                    values['offer_status'] = offer.status or ''
            elif entity_type == 'publisher':
                publisher = result
                if publisher:
                    values['publisher_name'] = publisher.publisher_name or ''
                    values['publisher_email'] = publisher.email or ''
            elif entity_type == 'advertiser':
                advertiser = result
                if advertiser:
                    values['advertiser_name'] = advertiser.advertiser_name or ''
                    values['advertiser_email'] = advertiser.email or ''

    # 开始替换占位符
    result_url = original_url
    unreplaced_placeholders = []

    for placeholder in placeholders:
        # 标准化占位符键名
        normalized_key = placeholder.lower()
        original_normalized_key = normalized_key

        # 检查别名映射表
        if normalized_key in PLACEHOLDER_ALIAS_MAP:
            normalized_key = PLACEHOLDER_ALIAS_MAP[normalized_key]
        else:
            # 驼峰命名转下划线命名
            normalized_key = re.sub(r'(?<!^)(?=[A-Z])', '_', placeholder).lower()

        # 特殊映射：channel_id 和 sub_affid 都映射到 publisher_id
        if normalized_key == 'channel_id' or normalized_key == 'sub_affid':
            normalized_key = 'publisher_id'

        # 获取对应的值
        value = values.get(normalized_key, '')

        if not value:
            logger.warning(
                f"[占位符替换] 占位符 {{{placeholder}}} (映射到 {normalized_key}) 的值为空，将移除包含该占位符的参数")
            unreplaced_placeholders.append(placeholder)
            continue

        # 替换占位符为实际值（URL编码）
        encoded_value = quote(str(value), safe='')
        result_url = result_url.replace(f'{{{placeholder}}}', encoded_value)

    # 移除包含未替换占位符的URL参数
    if unreplaced_placeholders:
        parsed = urlparse(result_url)

        if parsed.query:
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            query_params_lower = {k.lower(): v for k, v in query_params.items()}

            params_to_remove = []
            for param_name, param_values in query_params_lower.items():
                for param_value in param_values:
                    for unreplaced_placeholder in unreplaced_placeholders:
                        placeholder_pattern = f'{{{unreplaced_placeholder}}}'
                        if placeholder_pattern in param_value:
                            params_to_remove.append(param_name)
                            break
                    if param_name in params_to_remove:
                        break

            for param_name in params_to_remove:
                query_params_lower.pop(param_name, None)

            if query_params_lower:
                new_query = urlencode(query_params_lower, doseq=True)
                result_url = urlunparse(parsed._replace(query=new_query))
            else:
                result_url = urlunparse(parsed._replace(query=''))

    # 统一URL参数名为小写
    parsed = urlparse(result_url)
    if parsed.query:
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_params_lower = {k.lower(): v for k, v in query_params.items()}
        new_query = urlencode(query_params_lower, doseq=True)
        result_url = urlunparse(parsed._replace(query=new_query))

    return result_url


def replace_param_value_placeholders(
        param_value: str,
        click_id: str,
        offer_id: Optional[int],
        channel_id: Optional[int],
        advertiser_id: Optional[int],
        request_info: dict
) -> tuple[str, bool]:
    """
    替换URL参数值中的占位符
    
    Args:
        param_value: 参数值字符串，可能包含占位符
        click_id: 系统生成的唯一点击ID
        offer_id: Offer的数据库主键ID（可选）
        channel_id: 渠道ID（可选）
        advertiser_id: 广告主的数据库主键ID（可选）
        request_info: 请求信息字典
    
    Returns:
        tuple[str, bool]: 替换后的参数值字符串和是否所有占位符都被成功替换
    """
    pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    placeholders = re.findall(pattern, param_value)

    if not placeholders:
        return param_value, True

    # 构建占位符值字典
    values = {
        'click_id': click_id,
        'ip': request_info.get('ip', ''),
        'os': request_info.get('os', ''),
        'device_type': request_info.get('device_type', ''),
        'country': request_info.get('country', ''),
        'user_agent': request_info.get('user_agent', ''),
        'referer': request_info.get('referer', ''),
    }

    if offer_id:
        values['offer_id'] = str(offer_id)
    else:
        values['offer_id'] = ''

    if channel_id is not None:
        publisher_id_str = str(channel_id)
        values['publisher_id'] = publisher_id_str
        values['channel_id'] = publisher_id_str
    else:
        values['publisher_id'] = ''
        values['channel_id'] = ''

    if advertiser_id:
        values['advertiser_id'] = str(advertiser_id)
    else:
        values['advertiser_id'] = ''

    # 开始替换占位符
    result_value = param_value
    all_replaced = True

    for placeholder in placeholders:
        normalized_key = placeholder.lower()
        original_normalized_key = normalized_key

        if normalized_key in PLACEHOLDER_ALIAS_MAP:
            normalized_key = PLACEHOLDER_ALIAS_MAP[normalized_key]
        else:
            normalized_key = re.sub(r'(?<!^)(?=[A-Z])', '_', placeholder).lower()

        if normalized_key == 'channel_id' or normalized_key == 'sub_affid':
            normalized_key = 'publisher_id'

        value = values.get(normalized_key, '')

        if not value:
            all_replaced = False
            continue

        encoded_value = quote(str(value), safe='')
        result_value = result_value.replace(f'{{{placeholder}}}', encoded_value)

    return result_value, all_replaced
