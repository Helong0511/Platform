"""
定时任务工具函数
提供通用的任务执行辅助功能，减少重复代码
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import User, UserRole

logger = logging.getLogger(__name__)

# 应用时区配置
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)


def get_current_time_str() -> str:
    """
    获取当前时间的格式化字符串
    
    Returns:
        格式化的时间字符串，格式：YYYY-MM-DD HH:MM:SS
    """
    app_time = datetime.now(APP_TIMEZONE)
    return app_time.strftime("%Y-%m-%d %H:%M:%S")


def log_task_start(task_name: str, additional_info: Optional[str] = None) -> None:
    """
    记录任务开始执行的日志
    
    Args:
        task_name: 任务名称
        additional_info: 额外的日志信息（可选）
    """
    current_time_str = get_current_time_str()
    timezone_info = f"（时区: {settings.TIMEZONE}）"

    if additional_info:
        # 只记录一次，使用info级别（定时任务调度器会记录执行结果）
        logger.info(f"{task_name} 开始执行 - {current_time_str}{timezone_info} - {additional_info}")
    else:
        # 只记录一次，使用info级别（定时任务调度器会记录执行结果）
        logger.info(f"{task_name} 开始执行 - {current_time_str}{timezone_info}")


def log_task_result(task_name: str, result_summary: str, level: str = "info") -> None:
    """
    记录任务执行结果
    
    Args:
        task_name: 任务名称
        result_summary: 结果摘要
        level: 日志级别，'info' 或 'warning'（默认：'info'）
    """
    if level == "warning":
        logger.warning(f"[定时任务执行] {task_name} 执行完成: {result_summary}")
    logger.info(f"{task_name} 执行完成: {result_summary}")


def log_task_error(task_name: str, error_msg: str, exc_info: bool = True) -> None:
    """
    记录任务执行错误
    
    Args:
        task_name: 任务名称
        error_msg: 错误信息
        exc_info: 是否记录异常堆栈（默认：True）
    """
    full_error_msg = f"{task_name} 执行失败: {error_msg}"
    logger.error(full_error_msg, exc_info=exc_info)
    logger.warning(f"[{task_name}] {full_error_msg}")


def format_result_summary(
        inserted: int = 0,
        updated: int = 0,
        skipped: int = 0,
        error: int = 0,
        success: int = 0,
        processed: int = 0,
        **kwargs
) -> str:
    """
    格式化任务执行结果摘要
    
    Args:
        inserted: 插入数量
        updated: 更新数量
        skipped: 跳过数量
        error: 错误数量
        success: 成功数量
        processed: 处理数量
        **kwargs: 其他自定义统计项，格式：key=value
        
    Returns:
        格式化的结果摘要字符串
        
    Examples:
        >>> format_result_summary(inserted=10, updated=5, skipped=2, error=1)
        '成功插入 10 条, 成功更新 5 条, 跳过重复 2 条, 错误 1 条'
        
        >>> format_result_summary(success=100, processed=120)
        '成功处理 100 条, 共处理 120 条'
    """
    parts = []

    if inserted > 0:
        parts.append(f"成功插入 {inserted} 条")
    if updated > 0:
        parts.append(f"成功更新 {updated} 条")
    if skipped > 0:
        parts.append(f"跳过重复 {skipped} 条")
    if error > 0:
        parts.append(f"错误 {error} 条")
    if success > 0:
        parts.append(f"成功处理 {success} 条")
    if processed > 0:
        parts.append(f"共处理 {processed} 条")

    # 添加自定义统计项
    for key, value in kwargs.items():
        if value > 0:
            parts.append(f"{key} {value} 条")

    if not parts:
        return "无数据"

    return ", ".join(parts)


async def get_admin_user(db: AsyncSession) -> Optional[User]:
    """
    获取管理员用户（用于产品查找/创建等操作）
    
    优先查找 username 为 'data' 的管理员，如果不存在则查找任意一个管理员
    
    Args:
        db: 数据库会话
        
    Returns:
        管理员用户对象，如果不存在返回 None
    """
    # 优先查找 username 为 'data' 的管理员
    admin_user_query = select(User).where(
        User.role == UserRole.ADMIN,
        User.username == 'data'
    ).limit(1)
    admin_user_result = await db.execute(admin_user_query)
    admin_user = admin_user_result.scalar_one_or_none()

    # 如果没有找到 username 为 'data' 的管理员，查找任意一个管理员
    if not admin_user:
        admin_user_query = select(User).where(User.role == UserRole.ADMIN).limit(1)
        admin_user_result = await db.execute(admin_user_query)
        admin_user = admin_user_result.scalar_one_or_none()

    return admin_user


def resolve_upstream_date_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    *,
    early_morning_dual_day: bool = False,
) -> Tuple[str, str]:
    """
    解析上游 API 拉数日期范围。

    early_morning_dual_day: 0–2 点拉「昨日+今日」，否则仅今日（Huguang 等逻辑）。
    """
    if start_date:
        if end_date:
            return start_date, end_date
        return start_date, start_date

    app_now = datetime.now(APP_TIMEZONE)
    today_str = app_now.strftime("%Y-%m-%d")
    if early_morning_dual_day and 0 <= app_now.hour <= 2:
        yesterday_str = (app_now - timedelta(days=1)).strftime("%Y-%m-%d")
        return yesterday_str, today_str
    return today_str, today_str


def upstream_credential_missing(*values: Optional[str]) -> bool:
    """任一上游凭证为空则视为未配置。"""
    return any(v is None or not str(v).strip() for v in values)


def task_supports_manual_date_range(task_name: Optional[str]) -> bool:
    """手动触发时是否支持 start_date / end_date（上游 API 拉数类任务）。"""
    if not task_name:
        return False
    return str(task_name).endswith("API获取数据")
