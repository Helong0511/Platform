"""
定时任务通用工具函数模块。

功能说明：
- 统一任务启动/跳过/失败日志格式；格式化结果摘要写入 last_error
- 上游拉数共用：日期区间解析、凭证缺失检测、时区转换

在系统中的位置：
- 被 scheduler 与各 tasks/*.py 广泛引用

注意事项：
1. SCHEDULED_TASK_ERROR_MAX_LEN 与 lock 模块一致，截断错误信息防 DB 溢出
2. upstream_credential_missing 返回 True 时任务应 skip 而非抛未捕获异常
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Tuple, Union

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import User, UserRole

logger = logging.getLogger(__name__)

# 与 lock.MAX_ERROR_MESSAGE_LENGTH 保持一致，供 last_error 入库
SCHEDULED_TASK_ERROR_MAX_LEN = 1000

# 应用时区配置
APP_TIMEZONE = pytz.timezone(settings.TIMEZONE)


def truncate_task_error_message(message: str, max_len: int = SCHEDULED_TASK_ERROR_MAX_LEN) -> str:
    """截断任务错误信息，避免数据库字段溢出。"""
    text = (message or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def log_scheduled_task_start(
        task_name: str,
        *,
        pid: Optional[int] = None,
        host: Optional[str] = None,
        cron_expression: Optional[str] = None,
        trigger: str = "scheduled",
) -> None:
    """记录定时任务开始执行（便于与失败日志对照）。"""
    logger.info(
        "[定时任务开始] task=%s | trigger=%s | pid=%s | host=%s | cron=%s",
        task_name,
        trigger,
        pid if pid is not None else "-",
        host or "-",
        cron_expression or "-",
    )


def log_scheduled_task_failure(
        task_name: str,
        error: Union[BaseException, str],
        *,
        duration_seconds: Optional[float] = None,
        pid: Optional[int] = None,
        host: Optional[str] = None,
        cron_expression: Optional[str] = None,
        trigger: str = "scheduled",
        exc_info: bool = True,
        extra: Optional[dict[str, Any]] = None,
) -> str:
    """
    统一记录定时任务执行失败（ERROR，写入 scheduler.log / app.log）。

    Returns:
        截断后的错误摘要，可供 last_error 入库。
    """
    if isinstance(error, BaseException):
        error_type = type(error).__name__
        error_msg = str(error) or repr(error)
    else:
        error_type = "Error"
        error_msg = str(error)

    truncated = truncate_task_error_message(error_msg)
    parts = [
        f"[定时任务失败] task={task_name}",
        f"trigger={trigger}",
        f"error_type={error_type}",
        f"message={truncated}",
    ]
    if duration_seconds is not None:
        parts.append(f"duration_sec={duration_seconds:.2f}")
    if pid is not None:
        parts.append(f"pid={pid}")
    if host:
        parts.append(f"host={host}")
    if cron_expression:
        parts.append(f"cron={cron_expression}")
    if extra:
        for key, value in extra.items():
            parts.append(f"{key}={value}")

    log_line = " | ".join(parts)
    if isinstance(error, BaseException) and exc_info:
        logger.error(log_line, exc_info=error)
    else:
        logger.error(log_line)
    return truncated


def log_scheduled_task_failure_recorded(
        task_name: str,
        result_message: Optional[str],
        *,
        error_count: int,
        success_count: Optional[int] = None,
        run_count: Optional[int] = None,
) -> None:
    """任务失败状态已写入 scheduled_tasks 表后的补充日志。"""
    logger.warning(
        "[定时任务失败已入库] task=%s | error_count=%s | success_count=%s | run_count=%s | last_error=%s",
        task_name,
        error_count,
        success_count if success_count is not None else "-",
        run_count if run_count is not None else "-",
        truncate_task_error_message(result_message or "未知错误", 500),
    )


def log_scheduled_task_skip(
        task_name: str,
        reason: str,
        *,
        detail: Optional[str] = None,
) -> None:
    """记录定时任务被跳过（未计为失败，但排查「未执行」时有用）。"""
    msg = f"[定时任务跳过] task={task_name} | reason={reason}"
    if detail:
        msg = f"{msg} | {detail}"
    logger.warning(msg)


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
    else:
        logger.info(f"{task_name} 执行完成: {result_summary}")


def log_task_error(task_name: str, error_msg: str, exc_info: bool = True) -> None:
    """
    记录任务执行错误（任务函数内调用；调度器层会再次记录时可设 exc_info=False 避免重复堆栈）。
    """
    log_scheduled_task_failure(
        task_name,
        error_msg,
        trigger="task_body",
        exc_info=exc_info,
    )


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

    规则：
    - 未传参：结束日为今日，开始日为结束日前推一天（例：今日 2026-06-26 → 2026-06-25 ~ 2026-06-26）
    - 仅传 end_date：开始日 = end_date 前推一天
    - 仅传 start_date：单日拉数（start_date, start_date）
    - 同时传入 start_date 与 end_date：按传入区间原样使用（手动补数）

    early_morning_dual_day 已废弃，保留参数仅为兼容旧调用。
    """
    _ = early_morning_dual_day

    if start_date and end_date:
        return start_date, end_date

    if start_date and not end_date:
        return start_date, start_date

    app_now = datetime.now(APP_TIMEZONE)
    today_str = app_now.strftime("%Y-%m-%d")

    end_str = end_date or today_str
    end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
    start_str = (end_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    return start_str, end_str


def upstream_credential_missing(*values: Optional[str]) -> bool:
    """任一上游凭证为空则视为未配置。"""
    return any(v is None or not str(v).strip() for v in values)


def task_supports_manual_date_range(task_name: Optional[str]) -> bool:
    """手动触发时是否支持 start_date / end_date（上游 API 拉数类任务）。"""
    if not task_name:
        return False
    return str(task_name).endswith("API获取数据")
