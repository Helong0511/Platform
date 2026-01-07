"""
URL构建服务
处理URL参数合并和最终URL构建逻辑
"""
import logging
import re
from typing import Optional, Dict, Any
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
from collections import OrderedDict

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
    
    # 检测基础URL中的占位符
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
    
    # 重新构建URL
    new_query = urlencode(ordered_params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def build_final_url(
    original_url_before_replace: str,
    original_url_after_replace: str,
    click_id: str,
    offer_id: Optional[int],
    channel_id: Optional[int],
    final_channel_id: Optional[int],
    request_params: dict,
    request_info: Optional[dict] = None,
    advertiser_id: Optional[int] = None
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
        offer_id: Offer的数据库主键ID（可选）
        channel_id: 渠道ID（从URL参数获取，可能为None）
        final_channel_id: 最终使用的渠道ID
        request_params: 用户请求时携带的查询参数字典
        request_info: 请求信息字典（可选）
        advertiser_id: 广告主的数据库主键ID（可选）
    
    Returns:
        str: 最终的重定向URL，包含所有合并后的查询参数
    """
    placeholder_pattern_regex = re.compile(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}')
    
    # 检测原始URL中的占位符
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
    
    # 添加系统参数（如果原始URL中没有占位符）
    for param_name, has_placeholder_flag in has_placeholder.items():
        if not has_placeholder_flag:
            if param_name == 'click_id':
                request_params_with_click['click_id'] = click_id
            elif param_name == 'offer_id' and offer_id:
                request_params_with_click['offer_id'] = offer_id
            elif param_name == 'channel_id' and final_channel_id:
                if not has_placeholder.get('publisher_id', False):
                    request_params_with_click['channel_id'] = final_channel_id
    
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
                offer_id,
                final_channel_id,
                advertiser_id if advertiser_id is not None else None,
                request_info_for_replace
            )
            
            if all_replaced:
                logger.info(f"[构建最终URL] 参数 {key} 中的占位符已替换: {param_value_str} -> {replaced_value}")
                request_params_with_click[key_lower] = replaced_value
            else:
                filtered_params.append(f"{key}={value}")
                logger.warning(f"[构建最终URL] 跳过参数 {key}={value}，因为参数值中包含无法识别的占位符")
            continue
        
        # 查找该参数对应的系统参数名
        corresponding_param_name = None
        for param_name, possible_names in param_name_mapping.items():
            if key_lower in [name.lower() for name in possible_names]:
                corresponding_param_name = param_name
                break
        
        # 如果该参数在原始URL中使用了占位符，跳过
        if corresponding_param_name and has_placeholder.get(corresponding_param_name, False):
            continue
        
        # 处理 channel_id 和 publisher_id 的互斥关系
        if key_lower == 'channel_id' and has_placeholder.get('publisher_id', False):
            continue
        if key_lower == 'publisher_id' and has_placeholder.get('channel_id', False):
            continue
        
        # 参数通过所有检查，添加到合并列表
        request_params_with_click[key_lower] = value
    
    # 记录过滤信息
    if filtered_params:
        logger.info(f"[构建最终URL] 已过滤掉包含占位符的参数: {', '.join(filtered_params)}")
    
    # 合并参数到最终URL
    return merge_url_params(original_url_after_replace, request_params_with_click)

