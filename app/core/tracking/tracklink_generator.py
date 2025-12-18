"""
Tracklink 生成器
用于生成上游和下游的 Tracklink
"""
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs, urlencode as urlencode_func

logger = logging.getLogger(__name__)


def generate_upstream_tracklink(
    advertiser_tracklink: str,
    click_id: str,
    offer_id: str,
    publisher_id: Optional[str] = None
) -> str:
    """
    生成上游 Tracklink（包含我们的参数）
    
    Args:
        advertiser_tracklink: 上游的原始 Tracklink
        click_id: 我们生成的 Click ID
        offer_id: Offer ID
        publisher_id: 渠道ID（可选）
        
    Returns:
        包含我们参数的上游 Tracklink
    """
    try:
        # 解析原始 URL
        parsed = urlparse(advertiser_tracklink)
        query_params = parse_qs(parsed.query)
        
        # 添加我们的参数
        query_params['our_click_id'] = [click_id]
        query_params['our_offer_id'] = [offer_id]
        if publisher_id:
            query_params['our_publisher_id'] = [publisher_id]
        
        # 重新构建 URL
        new_query = urlencode(query_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        
        return urlunparse(new_parsed)
    except Exception as e:
        logger.error(f"生成上游 Tracklink 失败: {str(e)}")
        # 如果解析失败，简单追加参数
        separator = '&' if '?' in advertiser_tracklink else '?'
        return f"{advertiser_tracklink}{separator}our_click_id={click_id}&our_offer_id={offer_id}"


def generate_downstream_tracklink(
    base_url: str,
    offer_id: str,
    publisher_id: str,
    click_id: str,
    additional_params: Optional[Dict[str, Any]] = None
) -> str:
    """
    生成给下游的 Tracklink
    
    Args:
        base_url: 基础URL（我们的追踪域名）
        offer_id: Offer ID
        publisher_id: 渠道ID
        click_id: Click ID
        additional_params: 额外参数（可选）
        
    Returns:
        给下游的 Tracklink
    """
    try:
        # 构建参数
        params = {
            'offer_id': offer_id,
            'publisher_id': publisher_id,
            'click_id': click_id
        }
        
        # 添加额外参数
        if additional_params:
            params.update(additional_params)
        
        # 构建完整 URL
        query_string = urlencode(params)
        tracklink = f"{base_url.rstrip('/')}/track/click?{query_string}"
        
        return tracklink
    except Exception as e:
        logger.error(f"生成下游 Tracklink 失败: {str(e)}")
        return f"{base_url}/track/click?offer_id={offer_id}&publisher_id={publisher_id}&click_id={click_id}"


def generate_postback_url(
    base_url: str,
    click_id: str,
    offer_id: str,
    publisher_id: Optional[str] = None,
    additional_params: Optional[Dict[str, Any]] = None
) -> str:
    """
    生成 Postback URL（配置我们的参数）
    
    Args:
        base_url: 基础URL（我们的Postback接收地址）
        click_id: Click ID
        offer_id: Offer ID
        publisher_id: 渠道ID（可选）
        additional_params: 额外参数（可选）
        
    Returns:
        Postback URL
    """
    try:
        params = {
            'click_id': click_id,
            'offer_id': offer_id
        }
        
        if publisher_id:
            params['publisher_id'] = publisher_id
        
        if additional_params:
            params.update(additional_params)
        
        query_string = urlencode(params)
        postback_url = f"{base_url.rstrip('/')}?{query_string}"
        
        return postback_url
    except Exception as e:
        logger.error(f"生成 Postback URL 失败: {str(e)}")
        return f"{base_url}?click_id={click_id}&offer_id={offer_id}"

