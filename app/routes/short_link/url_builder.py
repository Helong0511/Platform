"""
URL构建服务
处理URL参数合并和最终URL构建逻辑
"""
import logging
import re
from collections import OrderedDict
from typing import Optional
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

from app.routes.short_link.placeholder import replace_param_value_placeholders

logger = logging.getLogger(__name__)


def merge_url_params(base_url: str, query_params: dict) -> str:
    """
    将查询参数合并到基础URL中
    
    这个函数用于将新的查询参数合并到已有的URL中，处理参数冲突和占位符检测。
    
    Args:
        base_url: 基础URL（可能已包含查询参数）
        query_params: 要合并的查询参数字典
    
    Returns:
        str: 合并后的完整URL
    """
    if not query_params:
        return base_url

    # 解析基础URL
    parsed = urlparse(base_url)
    existing_params = parse_qs(parsed.query, keep_blank_values=True)
    existing_params_lower = {k.lower(): v for k, v in existing_params.items()}

    # 定义占位符模式列表
    all_placeholder_patterns = [
        '{click_id}', '{clickId}', '{clickid}', '{ClickId}', '{CLICK_ID}',
        '{aff_click_id}', '{AFF_CLICK_ID}', '{affclickid}', '{AFFCLICKID}',
        '{offer_id}', '{offerId}', '{offerid}', '{OfferId}', '{OFFER_ID}',
        '{channel_id}', '{channelId}', '{channelid}', '{ChannelId}', '{CHANNEL_ID}',
        '{sub_affid}', '{SUB_AFFID}', '{subaffid}', '{SUBAFFID}',
        '{publisher_id}', '{publisherId}', '{publisherid}', '{PublisherId}', '{PUBLISHER_ID}',
        '{ip}', '{os}', '{device_type}', '{country}', '{advertiser_id}',
    ]

    # 定义参数别名映射（用于检测基础URL中是否已存在参数的别名）
    param_alias_mapping = {
        'click_id': ['click_id', 'aff_click_id', 'clickid', 'clickId', 'CLICK_ID', 'AFF_CLICK_ID', 'clk_id', 'cid',
                     'affclickid', 'AFFCLICKID'],
        'offer_id': ['offer_id', 'offerid', 'offerId', 'OFFER_ID'],
        'channel_id': ['channel_id', 'sub_affid', 'channelid', 'channelId', 'CHANNEL_ID', 'SUB_AFFID', 'subaffid',
                       'SUBAFFID'],
        'publisher_id': ['publisher_id', 'publisherid', 'publisherId', 'PUBLISHER_ID'],
    }

    # 检测基础URL中是否已存在参数的别名
    # 如果基础URL中已经有参数的别名（如 aff_click_id），就不应该添加标准参数名（如 click_id）
    skip_params = set()
    for param_name, aliases in param_alias_mapping.items():
        # 检查基础URL中是否已存在该参数的任何别名
        if any(alias.lower() in existing_params_lower for alias in aliases):
            skip_params.add(param_name)
            logger.debug(f"[合并URL参数] 检测到基础URL中已存在 {param_name} 的别名，跳过添加标准参数名")

    # 过滤包含占位符的参数值
    filtered_query_params = {}
    for key, value in query_params.items():
        param_value_str = str(value) if not isinstance(value, list) else str(value[0]) if value else ''
        contains_placeholder = any(pattern in param_value_str for pattern in all_placeholder_patterns)

        if contains_placeholder:
            logger.debug(f"[合并URL参数] 跳过参数 {key}={value}，因为参数值中包含占位符")
            continue

        filtered_query_params[key] = value

    query_params = filtered_query_params

    # 分离 click_id 和其他参数
    click_id_value = None
    other_params = {}

    for key, value in query_params.items():
        key_lower = key.lower()

        # 如果该参数在基础URL中已存在别名，跳过
        if key_lower in skip_params:
            logger.debug(f"[合并URL参数] 跳过参数 {key}，因为基础URL中已存在该参数的别名")
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

    # 构建最终URL，保持原始参数顺序
    ordered_params = OrderedDict()

    # 先添加基础URL中已有的参数（保持原始顺序）
    for key, value in existing_params.items():
        key_lower = key.lower()
        ordered_params[key_lower] = value

    # 然后添加新的参数（不包括已跳过的参数）
    for key, value in other_params.items():
        if key not in ordered_params:
            ordered_params[key] = value

    # 如果 click_id 不在 skip_params 中，且需要添加，则添加到最前面
    if click_id_value and 'click_id' not in skip_params:
        # 如果 click_id 不在 ordered_params 中，添加到最前面
        if 'click_id' not in ordered_params:
            new_ordered_params = OrderedDict()
            new_ordered_params['click_id'] = click_id_value
            for key, value in ordered_params.items():
                new_ordered_params[key] = value
            ordered_params = new_ordered_params

    # 重新构建URL
    new_query = urlencode(ordered_params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def build_final_url(
        original_url_before_replace: str,
        original_url_after_replace: str,
        click_id: str,
        final_offer_id: Optional[int],
        final_channel_id: Optional[int],
        request_params: dict,
        request_info: Optional[dict] = None,
        advertiser_id: Optional[int] = None,
) -> str:
    """
    构建最终的重定向URL
    
    这是短链接重定向流程中的核心函数，负责：
    1. 检测原始URL中是否已有占位符（避免重复添加参数）
    2. 处理请求参数中包含占位符的情况（尝试替换或过滤）
    3. 合并所有参数到最终URL中
    
    Args:
        original_url_before_replace: 替换占位符之前的原始URL
        original_url_after_replace: 替换占位符之后的URL
        click_id: 系统生成的唯一点击ID
        final_offer_id: 解析后的 Offer 主键（与 replace_short_link_placeholders 一致）
        final_channel_id: 最终使用的渠道（Publisher）主键
        request_params: 用户请求时携带的查询参数字典
        request_info: 请求信息字典（可选）
        advertiser_id: 广告主的数据库主键ID（可选）
    
    Returns:
        str: 最终的重定向URL，包含所有合并后的查询参数
    """
    placeholder_pattern_regex = re.compile(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}')

    # 检测原始URL中的占位符
    placeholder_params_to_check = {
        'click_id': ['{click_id}', '{clickId}', '{clickid}', '{ClickId}', '{CLICK_ID}', '{aff_click_id}',
                     '{AFF_CLICK_ID}'],
        'offer_id': ['{offer_id}', '{offerId}', '{offerid}', '{OfferId}', '{OFFER_ID}'],
        'channel_id': ['{channel_id}', '{channelId}', '{channelid}', '{ChannelId}', '{CHANNEL_ID}', '{sub_affid}',
                       '{SUB_AFFID}'],
        'publisher_id': ['{publisher_id}', '{publisherId}', '{publisherid}', '{PublisherId}', '{PUBLISHER_ID}'],
    }

    has_placeholder = {}
    for param_name, placeholder_variants in placeholder_params_to_check.items():
        has_placeholder[param_name] = any(variant in original_url_before_replace for variant in placeholder_variants)

    # 准备要合并的参数
    request_params_with_click = {}

    # 注意：不再自动添加系统参数
    # 如果原始URL中没有占位符，说明不需要这些参数，不应该添加
    # 只有在用户请求参数中明确包含这些参数时，才会被添加

    # 处理用户请求参数
    param_name_mapping = {
        'click_id': ['click_id', 'aff_click_id', 'clickid', 'clickId', 'CLICK_ID', 'AFF_CLICK_ID'],
        'offer_id': ['offer_id', 'offerid', 'offerId', 'OFFER_ID'],
        'channel_id': ['channel_id', 'sub_affid', 'channelid', 'channelId', 'CHANNEL_ID', 'SUB_AFFID'],
        'publisher_id': ['publisher_id', 'publisherid', 'publisherId', 'PUBLISHER_ID'],
    }

    filtered_params = []
    request_info_for_replace = request_info if request_info else {
        'ip': '', 'os': '', 'device_type': '', 'country': '',
        'user_agent': '', 'referer': '',
    }

    # 遍历用户请求参数
    for key, value in request_params.items():
        key_lower = key.lower()

        # 检查参数值中是否包含占位符
        param_value_str = str(value) if not isinstance(value, list) else str(value[0]) if value else ''
        contains_placeholder = bool(placeholder_pattern_regex.search(param_value_str))

        if contains_placeholder:
            # 参数值包含占位符，尝试替换
            replaced_value, all_replaced = replace_param_value_placeholders(
                param_value_str,
                click_id,
                final_offer_id,
                final_channel_id,
                advertiser_id if advertiser_id is not None else None,
                request_info_for_replace,
            )

            if all_replaced:
                logger.info(f"[构建最终URL] 参数 {key} 中的占位符已替换: {param_value_str} -> {replaced_value}")
                request_params_with_click[key_lower] = replaced_value
            else:
                filtered_params.append(f"{key}={value}")
            continue

        # 查找该参数对应的系统参数名
        corresponding_param_name = None
        for param_name, possible_names in param_name_mapping.items():
            if key_lower in [name.lower() for name in possible_names]:
                corresponding_param_name = param_name
                break

        # 如果该参数是系统参数（click_id, offer_id, channel_id, publisher_id）
        if corresponding_param_name:
            # 如果该参数在原始URL中使用了占位符，跳过（因为已经在原始URL中替换了）
            if has_placeholder.get(corresponding_param_name, False):
                logger.debug(f"[构建最终URL] 跳过参数 {key}，因为原始URL中已有对应的占位符")
                continue

            # 如果该参数在原始URL中没有占位符，也不应该添加（只保留原始URL中的参数）
            logger.debug(f"[构建最终URL] 跳过系统参数 {key}，因为原始URL中没有对应的占位符")
            continue

        # 对于非系统参数，也不应该添加（只保留原始URL中已有的参数）
        # 根据用户需求，最终URL应该就是替换占位符后的URL，不添加额外的参数
        logger.debug(f"[构建最终URL] 跳过参数 {key}，因为原始URL中没有对应的占位符")
        continue

    # 记录过滤信息
    if filtered_params:
        logger.info(f"[构建最终URL] 已过滤掉包含占位符的参数: {', '.join(filtered_params)}")

    # 合并参数到最终URL
    return merge_url_params(original_url_after_replace, request_params_with_click)
