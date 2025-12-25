"""
时区工具模块
提供时区检测、验证和统一的时间获取功能
"""
import logging
import os
import subprocess
import platform
from datetime import datetime
import pytz

from app.core.config import settings

logger = logging.getLogger(__name__)

# 应用时区配置（从统一配置读取）
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)


def detect_system_timezone() -> str | None:
    """
    检测系统时区设置
    
    Returns:
        系统时区字符串（如 'Asia/Shanghai', 'UTC'），如果无法检测则返回 None
    """
    try:
        # 方法1: 使用 timedatectl (Linux)
        if platform.system() == "Linux":
            try:
                result = subprocess.run(
                    ["timedatectl", "show", "--property=Timezone", "--value"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    timezone = result.stdout.strip()
                    if timezone:
                        return timezone
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
                pass
        
        # 方法2: 读取 /etc/timezone (Linux)
        if platform.system() == "Linux":
            try:
                with open("/etc/timezone", "r") as f:
                    timezone = f.read().strip()
                    if timezone:
                        return timezone
            except (FileNotFoundError, PermissionError, IOError):
                pass
        
        # 方法3: 读取 TZ 环境变量
        tz_env = os.environ.get("TZ")
        if tz_env:
            return tz_env
        
        # 方法4: 使用 Python 的 time.tzname (可能不准确)
        import time
        tzname = time.tzname[0] if time.tzname else None
        if tzname:
            # 尝试映射常见时区名称
            tz_mapping = {
                "CST": "Asia/Shanghai",  # 中国标准时间
                "UTC": "UTC",
                "GMT": "UTC",
            }
            if tzname in tz_mapping:
                return tz_mapping[tzname]
        
        return None
    except Exception as e:
        logger.warning(f"检测系统时区时出错: {e}")
        return None


def get_system_time_info() -> dict:
    """
    获取系统时间信息
    
    Returns:
        包含系统时区、应用时区、当前时间等信息的字典
    """
    system_tz = detect_system_timezone()
    app_tz = settings.TIMEZONE
    
    # 获取系统当前时间（UTC）
    utc_now = datetime.now(pytz.UTC)
    
    # 获取应用时区的当前时间
    app_now = datetime.now(APP_TIMEZONE)
    
    # 获取系统本地时间（如果系统时区可检测）
    system_now = None
    if system_tz:
        try:
            system_tz_obj = pytz.timezone(system_tz)
            system_now = datetime.now(system_tz_obj)
        except Exception:
            pass
    
    return {
        "system_timezone": system_tz or "未知",
        "app_timezone": app_tz,
        "utc_time": utc_now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "app_time": app_now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "system_time": system_now.strftime("%Y-%m-%d %H:%M:%S %Z") if system_now else "未知",
        "timezone_match": system_tz == app_tz if system_tz else None,
    }


def check_and_validate_timezone() -> bool:
    """
    检查并验证系统时区与配置时区是否一致
    
    Returns:
        bool: 如果时区一致或无法检测系统时区返回 True，不一致返回 False
    """
    time_info = get_system_time_info()
    system_tz = time_info['system_timezone']
    app_tz = time_info['app_timezone']
    timezone_match = time_info['timezone_match']
    
    # 如果无法检测系统时区，返回 True（允许继续运行）
    if timezone_match is None:
        logger.warning("⚠️  无法检测系统时区，应用将使用配置的时区（应用时区）")
        return True
    
    # 如果时区一致，返回 True
    if timezone_match is True:
        logger.info(f"✓ 系统时区 ({system_tz}) 与应用时区 ({app_tz}) 一致")
        return True
    
    # 时区不一致，返回 False 并记录警告
    logger.warning("=" * 60)
    logger.warning("⚠️  时区配置不匹配警告")
    logger.warning("=" * 60)
    logger.warning(f"系统时区: {system_tz}")
    logger.warning(f"应用配置时区: {app_tz}")
    logger.warning(f"UTC 时间: {time_info['utc_time']}")
    logger.warning(f"应用时间: {time_info['app_time']}")
    logger.warning(f"系统时间: {time_info['system_time']}")
    logger.warning("")
    logger.warning("处理方式：")
    logger.warning("  应用将统一使用配置的时区（应用时区）处理所有时间，不受系统时区影响。")
    logger.warning("  所有时间相关的操作（如业务日期、定时任务等）都将基于配置的时区。")
    logger.warning("")
    logger.warning("建议：")
    logger.warning("  1. 如果系统时区与应用时区应该一致，请调整系统时区设置")
    logger.warning("  2. 如果系统使用 UTC 而应用使用其他时区，这是正常的配置，无需调整")
    logger.warning("=" * 60)
    
    return False


def log_timezone_info() -> None:
    """
    在应用启动时记录时区信息
    用于诊断时区配置问题
    """
    time_info = get_system_time_info()
    
    logger.info("=" * 60)
    logger.info("时区配置信息")
    logger.info("=" * 60)
    logger.info(f"系统时区: {time_info['system_timezone']}")
    logger.info(f"应用时区: {time_info['app_timezone']}")
    logger.info(f"UTC 时间: {time_info['utc_time']}")
    logger.info(f"应用时间: {time_info['app_time']}")
    logger.info(f"系统时间: {time_info['system_time']}")
    
    if time_info['timezone_match'] is False:
        logger.warning(
            f"⚠️  系统时区 ({time_info['system_timezone']}) 与应用时区 ({time_info['app_timezone']}) 不匹配！"
        )
        logger.warning(
            "应用将使用配置的时区（应用时区），不受系统时区影响。"
        )
        logger.warning(
            "如果系统使用 UTC 而应用使用北京时间，这是正常的配置。"
        )
    elif time_info['timezone_match'] is True:
        logger.info("✓ 系统时区与应用时区匹配")
    else:
        logger.warning("无法检测系统时区，应用将使用配置的时区")
    
    logger.info("=" * 60)


def validate_timezone(timezone_str: str) -> bool:
    """
    验证时区字符串是否有效
    
    Args:
        timezone_str: 时区字符串（如 'Asia/Shanghai', 'UTC'）
    
    Returns:
        如果时区有效返回 True，否则返回 False
    """
    try:
        pytz.timezone(timezone_str)
        return True
    except pytz.UnknownTimeZoneError:
        return False

