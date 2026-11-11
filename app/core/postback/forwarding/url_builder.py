"""
URL 构建器

构建 Postback 转发 URL
"""
import logging
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse, quote

from app.core.url.url_params_util import (
    normalize_url_params,
    parse_stored_url_params,
    scalar_query_value,
)

logger = logging.getLogger(__name__)


class UrlBuilder:
    """URL 构建器"""
    
    @staticmethod
    def build_postback_url(
        base_url: str,
        conversion_data: Dict[str, Any],
        click_association: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Dict[str, str]]:
        """
        构建 Postback URL
        
        Args:
            base_url: 基础 URL
            conversion_data: 转化数据
            click_association: Click 关联信息
        
        Returns:
            tuple: (完整 URL, 参数字典)
        """
        # 解析基础 URL
        parsed = urlparse(base_url)
        
        # 解析现有查询参数
        existing_params = parse_qs(parsed.query)
        
        # 构建新参数
        new_params = UrlBuilder._build_params(conversion_data, click_association)
        
        # 合并参数
        merged_params = {**existing_params, **new_params}
        
        # 重新构建 URL
        new_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(merged_params, doseq=True),
            parsed.fragment
        ))
        
        logger.debug(
            "构建 Postback URL 完成：parameter_count=%s",
            len(merged_params),
        )
        
        return new_url, merged_params
    
    @staticmethod
    def _build_params(
        conversion_data: Dict[str, Any],
        click_association: Optional[Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        构建查询参数
        
        Args:
            conversion_data: 转化数据
            click_association: Click 关联信息
        
        Returns:
            dict: 参数字典
        """
        params = {}

        url_params: Dict[str, Any] = {}
        if click_association:
            raw_up = click_association.get("url_params")
            if isinstance(raw_up, dict):
                url_params = normalize_url_params(raw_up)
            elif isinstance(raw_up, str) and raw_up.strip():
                url_params = parse_stored_url_params(raw_up)
        
        # 转化相关参数
        if conversion_data.get('conversion_id'):
            params['conversion_id'] = str(conversion_data['conversion_id'])
        
        if conversion_data.get('payout'):
            params['payout'] = str(conversion_data['payout'])
        
        if conversion_data.get('event_name'):
            params['event_name'] = str(conversion_data['event_name'])
        
        # Click 相关参数 - 优先从 url_params 中获取
        if click_association:
            cid = scalar_query_value(url_params.get("click_id")) or (
                str(click_association["click_id"])
                if click_association.get("click_id") is not None
                else None
            )
            if cid:
                params["click_id"] = cid
                params["clickid"] = cid

            for key, assoc_key in (
                ("offer_id", "offer_id"),
                ("publisher_id", "publisher_id"),
                ("advertiser_id", "advertiser_id"),
                ("short_link_id", "short_link_id"),
            ):
                val = scalar_query_value(url_params.get(key))
                if val is not None:
                    params[key] = val
                elif click_association.get(assoc_key) is not None:
                    params[key] = str(click_association[assoc_key])
        
        return params
