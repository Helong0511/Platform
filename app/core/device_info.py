"""
设备与客户端信息采集工具。

职责：解析 User-Agent、请求头，输出 OS/浏览器/设备类型等结构化字段，供点击与转化归因。

在系统中的位置：``app.core.device_info``，被 Postback 解析与短链跳转链路引用。
"""
import re
import json
from typing import Dict, Optional, Any
from fastapi import Request
from app.core.utils import get_client_ip


def parse_user_agent(user_agent: Optional[str]) -> Dict[str, Optional[str]]:
    """
    解析User-Agent字符串，提取软件和硬件信息
    
    Args:
        user_agent: User-Agent字符串
        
    Returns:
        包含解析结果的字典：
        {
            'os': 操作系统名称,
            'os_version': 操作系统版本,
            'browser': 浏览器名称,
            'browser_version': 浏览器版本,
            'device_type': 设备类型 (mobile/tablet/desktop),
            'device_brand': 设备品牌,
            'device_model': 设备型号,
            'is_bot': 是否为爬虫/机器人
        }
    """
    if not user_agent:
        return {
            'os': None,
            'os_version': None,
            'browser': None,
            'browser_version': None,
            'device_type': None,
            'device_brand': None,
            'device_model': None,
            'is_bot': False
        }
    
    ua = user_agent.lower()
    result = {
        'os': None,
        'os_version': None,
        'browser': None,
        'browser_version': None,
        'device_type': None,
        'device_brand': None,
        'device_model': None,
        'is_bot': False
    }
    
    # 检测是否为机器人/爬虫
    bot_patterns = [
        r'bot', r'crawler', r'spider', r'scanner', r'curl', r'wget',
        r'python', r'java', r'http', r'go-http', r'okhttp'
    ]
    if any(re.search(pattern, ua) for pattern in bot_patterns):
        result['is_bot'] = True
    
    # 解析操作系统
    # Windows
    if 'windows' in ua:
        result['os'] = 'Windows'
        win_version_match = re.search(r'windows nt (\d+\.?\d*)', ua)
        if win_version_match:
            version = win_version_match.group(1)
            version_map = {
                '10.0': '10/11',
                '6.3': '8.1',
                '6.2': '8',
                '6.1': '7',
                '6.0': 'Vista',
                '5.1': 'XP',
                '5.0': '2000'
            }
            result['os_version'] = version_map.get(version, version)
        else:
            result['os_version'] = 'Unknown'
    
    # macOS
    elif 'mac os x' in ua or 'macintosh' in ua:
        result['os'] = 'macOS'
        mac_version_match = re.search(r'mac os x (\d+[._]\d+)', ua)
        if mac_version_match:
            result['os_version'] = mac_version_match.group(1).replace('_', '.')
        else:
            result['os_version'] = 'Unknown'
    
    # iOS
    elif 'iphone os' in ua or 'ipad' in ua or 'ipod' in ua:
        result['os'] = 'iOS'
        ios_version_match = re.search(r'os (\d+[._]\d+)', ua)
        if ios_version_match:
            result['os_version'] = ios_version_match.group(1).replace('_', '.')
        else:
            result['os_version'] = 'Unknown'
        
        # 设备信息
        if 'iphone' in ua:
            result['device_type'] = 'mobile'
            result['device_brand'] = 'Apple'
            iphone_model_match = re.search(r'iphone(\d+,\d+)', ua)
            if iphone_model_match:
                result['device_model'] = f"iPhone {iphone_model_match.group(1).replace(',', '.')}"
            else:
                result['device_model'] = 'iPhone'
        elif 'ipad' in ua:
            result['device_type'] = 'tablet'
            result['device_brand'] = 'Apple'
            result['device_model'] = 'iPad'
        elif 'ipod' in ua:
            result['device_type'] = 'mobile'
            result['device_brand'] = 'Apple'
            result['device_model'] = 'iPod'
    
    # Android
    elif 'android' in ua:
        result['os'] = 'Android'
        android_version_match = re.search(r'android (\d+\.?\d*)', ua)
        if android_version_match:
            result['os_version'] = android_version_match.group(1)
        else:
            result['os_version'] = 'Unknown'
        
        # 设备信息
        device_match = re.search(r'\(([^)]+)\)', ua)
        if device_match:
            device_info = device_match.group(1)
            parts = device_info.split(';')
            if len(parts) >= 2:
                result['device_model'] = parts[-1].strip()
                # 尝试提取品牌
                brand_match = re.search(r'([a-z]+)', parts[-1].lower())
                if brand_match:
                    result['device_brand'] = brand_match.group(1).capitalize()
        
        # 判断设备类型
        if 'mobile' in ua:
            result['device_type'] = 'mobile'
        elif 'tablet' in ua:
            result['device_type'] = 'tablet'
        else:
            result['device_type'] = 'mobile'  # 默认移动设备
    
    # Linux
    elif 'linux' in ua:
        result['os'] = 'Linux'
        linux_distro_match = re.search(r'(ubuntu|debian|fedora|centos|redhat)', ua)
        if linux_distro_match:
            result['os_version'] = linux_distro_match.group(1)
        else:
            result['os_version'] = 'Unknown'
    
    # 其他操作系统
    elif 'x11' in ua:
        result['os'] = 'Unix'
    elif 'bsd' in ua:
        result['os'] = 'BSD'
    
    # 解析浏览器
    # Chrome
    if 'chrome' in ua and 'edg' not in ua and 'opr' not in ua:
        result['browser'] = 'Chrome'
        chrome_version_match = re.search(r'chrome/(\d+\.?\d*\.?\d*\.?\d*)', ua)
        if chrome_version_match:
            result['browser_version'] = chrome_version_match.group(1)
    
    # Edge
    elif 'edg' in ua or 'edge' in ua:
        result['browser'] = 'Edge'
        edge_version_match = re.search(r'edg[ea]?/(\d+\.?\d*\.?\d*\.?\d*)', ua)
        if edge_version_match:
            result['browser_version'] = edge_version_match.group(1)
    
    # Firefox
    elif 'firefox' in ua:
        result['browser'] = 'Firefox'
        firefox_version_match = re.search(r'firefox/(\d+\.?\d*\.?\d*)', ua)
        if firefox_version_match:
            result['browser_version'] = firefox_version_match.group(1)
    
    # Safari
    elif 'safari' in ua and 'chrome' not in ua:
        result['browser'] = 'Safari'
        safari_version_match = re.search(r'version/(\d+\.?\d*\.?\d*)', ua)
        if safari_version_match:
            result['browser_version'] = safari_version_match.group(1)
    
    # Opera
    elif 'opr' in ua or 'opera' in ua:
        result['browser'] = 'Opera'
        opera_version_match = re.search(r'(?:opr|opera)/(\d+\.?\d*\.?\d*)', ua)
        if opera_version_match:
            result['browser_version'] = opera_version_match.group(1)
    
    # 微信内置浏览器
    elif 'micromessenger' in ua:
        result['browser'] = 'WeChat'
        wechat_version_match = re.search(r'micromessenger/(\d+\.?\d*\.?\d*)', ua)
        if wechat_version_match:
            result['browser_version'] = wechat_version_match.group(1)
    
    # QQ浏览器
    elif 'qqbrowser' in ua or 'mqqbrowser' in ua:
        result['browser'] = 'QQ Browser'
        qq_version_match = re.search(r'(?:qq|mqq)browser/(\d+\.?\d*\.?\d*)', ua)
        if qq_version_match:
            result['browser_version'] = qq_version_match.group(1)
    
    # UC浏览器
    elif 'ucbrowser' in ua or 'ucweb' in ua:
        result['browser'] = 'UC Browser'
        uc_version_match = re.search(r'ucbrowser/(\d+\.?\d*\.?\d*)', ua)
        if uc_version_match:
            result['browser_version'] = uc_version_match.group(1)
    
    # 如果没有检测到设备类型，根据其他信息判断
    if not result['device_type']:
        if 'mobile' in ua or 'android' in ua or 'iphone' in ua:
            result['device_type'] = 'mobile'
        elif 'tablet' in ua or 'ipad' in ua:
            result['device_type'] = 'tablet'
        else:
            result['device_type'] = 'desktop'
    
    return result


def collect_request_info(request: Request) -> Dict[str, Any]:
    """
    收集请求的完整信息，包括软件、硬件和URL参数
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        包含所有请求信息的字典
    """
    # 获取User-Agent
    user_agent = request.headers.get("user-agent")
    
    # 解析User-Agent
    device_info = parse_user_agent(user_agent)
    
    # 获取客户端IP（使用统一的工具函数）
    client_ip = get_client_ip(request)
    
    # 收集所有请求头
    headers = {}
    for key, value in request.headers.items():
        headers[key] = value
    
    # 收集URL参数（必须保留全部：含重复 key、空值；用于 clicks 访问记录）
    # - url_params: JSON(dict[str, list[str]]) 便于存库与后续追加字段
    # - url_params_dict: dict[str, str|list[str]] 便于生成 click_id 令牌使用
    url_params_multi: Dict[str, list[str]] = {}
    for k, v in request.query_params.multi_items():
        ks = str(k)
        vs = "" if v is None else str(v)
        url_params_multi.setdefault(ks, []).append(vs)

    url_params_dict: Dict[str, Any] = {}
    for k, vals in url_params_multi.items():
        if len(vals) == 1:
            url_params_dict[k] = vals[0]
        else:
            url_params_dict[k] = vals
    
    # 获取其他重要信息
    referer = request.headers.get("referer")
    accept_language = request.headers.get("accept-language")
    accept_encoding = request.headers.get("accept-encoding")
    
    # 构建完整信息
    info = {
        # 基础信息
        'ip': client_ip,
        'user_agent': user_agent,
        'referer': referer,
        'accept_language': accept_language,
        'accept_encoding': accept_encoding,
        
        # 软件信息（从User-Agent解析）
        'os': device_info.get('os'),
        'os_version': device_info.get('os_version'),
        'browser': device_info.get('browser'),
        'browser_version': device_info.get('browser_version'),
        'is_bot': device_info.get('is_bot'),
        
        # 硬件信息（从User-Agent解析）
        'device_type': device_info.get('device_type'),
        'device_brand': device_info.get('device_brand'),
        'device_model': device_info.get('device_model'),
        
        # URL参数（JSON格式存储，保留全部参数与重复值）
        'url_params': json.dumps(url_params_multi, ensure_ascii=False) if url_params_multi else None,
        # 给令牌生成用（dict 形式，不丢重复值）
        'url_params_dict': url_params_dict if url_params_multi else None,
        
        # 所有请求头（JSON格式存储，用于详细分析）
        'all_headers': json.dumps(headers) if headers else None,
    }
    
    return info

