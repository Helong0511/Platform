"""
工具函数模块
提供通用的工具函数，避免代码重复
"""
import math
import pytz
from datetime import datetime
from typing import Any
from fastapi import Request
from app.core.middleware import get_device_type
from app.core.config import settings

# 应用时区配置（从统一配置读取）
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)


def get_client_ip(request: Request) -> str:
    """
    从请求中获取客户端IP地址
    支持代理情况（X-Forwarded-For头）
    
    Args:
        request: FastAPI请求对象
        
    Returns:
        客户端IP地址字符串，如果无法获取则返回"unknown"
    """
    try:
        client_ip = request.client.host if request.client else "unknown"
        if "x-forwarded-for" in request.headers:
            forwarded_ips = request.headers["x-forwarded-for"].split(",")
            client_ip = forwarded_ips[0].strip()
        return client_ip
    except AttributeError:
        # 处理request.client为None的情况
        return "unknown"


def optimize_page_size_for_device(request: Request, page_size: int, default_page_size: int = 10) -> int:
    """
    根据设备类型优化分页大小
    桌面端：使用原始分页大小或默认值
    平板端：适当减小分页大小，限制最大值
    手机端：使用较小的分页大小，限制最大值
    
    Args:
        request: FastAPI请求对象
        page_size: 请求的分页大小
        default_page_size: 默认分页大小
        
    Returns:
        优化后的分页大小
    """
    device_type = get_device_type(request)

    # 如果使用默认值，根据设备类型调整
    if page_size == default_page_size:
        if device_type == 'desktop':
            # 桌面端保持默认值
            return default_page_size
        elif device_type == 'tablet':
            # 平板端：使用稍大的默认值
            return 15
        else:  # mobile
            # 手机端：使用较小的默认值
            return 10

    # 如果用户指定了分页大小，根据设备类型限制最大值
    if device_type == 'desktop':
        # 桌面端：允许较大的分页大小
        return min(page_size, 100)
    elif device_type == 'tablet':
        # 平板端：限制最大值为25
        return min(page_size, 25)
    else:  # mobile
        # 手机端：限制最大值为15
        return min(page_size, 15)


def truncate_to_2_decimal(value: float) -> float:
    """
    截断浮点数到两位小数（砍掉第三位及之后的所有数字）
    不使用四舍五入，直接向下截断
    
    Args:
        value: 要截断的浮点数
    
    Returns:
        截断到两位小数的浮点数
    """
    return math.floor(value * 100) / 100


def get_date_range(date_obj: datetime | Any) -> tuple[datetime, datetime]:
    """
    获取日期范围（当天的开始和结束时间）
    
    Args:
        date_obj: 日期对象（datetime 或 date 类型）
    
    Returns:
        (date_start, date_end): 当天的开始和结束时间
    """
    if isinstance(date_obj, datetime):
        date_start = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_obj.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        date_start = datetime.combine(date_obj, datetime.min.time())
        date_end = datetime.combine(date_obj, datetime.max.time())
    return date_start, date_end


def normalize_date_for_ad_data(date_obj: datetime | Any) -> datetime:
    """
    规范化日期对象用于 AdData（转换为当天的 00:00:00）
    
    Args:
        date_obj: 日期对象（datetime 或 date 类型）
    
    Returns:
        datetime: 规范化后的日期对象（当天的 00:00:00）
    """
    if isinstance(date_obj, datetime):
        return date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        return datetime.combine(date_obj, datetime.min.time())


def get_app_now() -> datetime:
    """
    获取应用时区的当前时间
    
    无论系统使用什么时区（UTC 或本地时间），都返回应用配置时区（默认北京时间）的当前时间
    
    Returns:
        datetime: 应用时区的当前时间（带时区信息）
    """
    return datetime.now(APP_TIMEZONE)


def get_app_now_naive() -> datetime:
    """
    获取应用时区的当前时间（naive datetime，不带时区信息）
    
    用于业务日期字段，与数据库存储格式一致
    
    Returns:
        datetime: 应用时区的当前时间（naive，不带时区信息）
    """
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)
