"""Postback 模块通用工具函数"""
import logging
from typing import Optional, Dict, Any

from fastapi import Request

logger = logging.getLogger(__name__)


def extract_client_ip(request: Request) -> str:
    """
    从请求中提取客户端IP地址
    
    Args:
        request: FastAPI 请求对象
    
    Returns:
        str: 客户端IP地址
    """
    # 尝试从 X-Forwarded-For 头获取
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        # 多个IP地址时，取第一个（最原始的客户端IP）
        return x_forwarded_for.split(",")[0].strip()
    
    # 尝试从 X-Real-IP 头获取
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip
    
    # 从 request.client 获取
    if request.client:
        return request.client.host
    
    return "unknown"


def validate_platform_name(platform: str) -> bool:
    """
    验证平台名称是否有效
    
    Args:
        platform: 平台名称
    
    Returns:
        bool: 是否有效
    """
    if not platform or not isinstance(platform, str):
        return False
    
    # 平台名称长度限制
    if len(platform) > 50:
        return False
    
    # 平台名称只能包含字母、数字、下划线和连字符
    for char in platform:
        if not (char.isalnum() or char in ["_", "-"]):
            return False
    
    return True


def sanitize_postback_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    清理 Postback 数据，移除敏感信息
    
    Args:
        data: Postback 原始数据
    
    Returns:
        Dict[str, Any]: 清理后的数据
    """
    if not isinstance(data, dict):
        return {}
    
    # 敏感字段列表
    sensitive_fields = ["password", "token", "secret", "key", "auth"]
    
    sanitized_data = {}
    for key, value in data.items():
        # 检查是否为敏感字段
        if any(sensitive in key.lower() for sensitive in sensitive_fields):
            sanitized_data[key] = "[REDACTED]"
        else:
            # 限制值的长度
            if isinstance(value, str) and len(value) > 1000:
                sanitized_data[key] = value[:1000] + "..."
            else:
                sanitized_data[key] = value
    
    return sanitized_data


def format_postback_response(message: str, success: bool = True) -> Dict[str, Any]:
    """
    格式化 Postback 响应
    
    Args:
        message: 响应消息
        success: 是否成功
    
    Returns:
        Dict[str, Any]: 格式化后的响应
    """
    return {
        "success": success,
        "message": message,
        "timestamp": "2026-03-19T10:00:00Z"  # 示例时间戳
    }
