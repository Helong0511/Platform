"""
数据库连接类异常判断。

用于调度器、维护窗口等场景：区分「库不可达」与真实业务/锁错误，避免误报 ERROR。
"""
from __future__ import annotations

import asyncio
import errno
import logging
from collections.abc import Awaitable, Callable
from typing import Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def get_mysql_errno(exc: BaseException | None) -> Optional[int]:
    """从 SQLAlchemy / PyMySQL 异常链中提取 MySQL 错误码。"""
    if exc is None:
        return None
    args = getattr(exc, "args", ())
    if args:
        try:
            return int(args[0])
        except (TypeError, ValueError):
            pass
    orig = getattr(exc, "orig", None)
    if orig is not None and orig is not exc:
        code = get_mysql_errno(orig)
        if code is not None:
            return code
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return get_mysql_errno(cause)
    return None


def is_table_definition_changed_error(exc: BaseException) -> bool:
    """
    MySQL 1412：事务期间表定义被 ALTER / 迁移改过。

    典型场景：刚执行 schema 迁移、连接池里仍有半截事务；应 rollback 后重试。
    """
    if get_mysql_errno(exc) == 1412:
        return True
    return "table definition has changed" in str(exc).lower()


async def run_with_mysql_schema_retry(
    session,
    operation: Callable[[], Awaitable[T]],
    *,
    retries: int = 2,
    label: str = "db_query",
) -> T:
    """
    执行异步库操作；遇 MySQL 1412 则 rollback 后短暂重试。

    Args:
        session: AsyncSession（用于 rollback）
        operation: 无参异步可调用，返回查询结果
        retries: 额外重试次数（默认共最多 3 次）
        label: 日志标签
    """
    last_exc: BaseException | None = None
    attempts = max(0, int(retries)) + 1
    for attempt in range(attempts):
        try:
            return await operation()
        except Exception as exc:
            last_exc = exc
            if not is_table_definition_changed_error(exc) or attempt >= attempts - 1:
                raise
            logger.warning(
                "%s 遇 MySQL 1412（表定义已变更），rollback 后重试 %s/%s: %s",
                label,
                attempt + 1,
                attempts - 1,
                exc,
            )
            try:
                from app.core.query_utils import invalidate_assignment_table_cache

                invalidate_assignment_table_cache()
            except Exception:
                pass
            try:
                await session.rollback()
            except Exception as rb_err:
                logger.debug("%s rollback 失败（可忽略）: %s", label, rb_err)
            await asyncio.sleep(0.05 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def is_database_unreachable_error(exc: BaseException) -> bool:
    """
    判断异常是否表示 MySQL/数据库暂时不可达（关停、维护、拒绝连接）。

    典型场景：部署脚本停 MySQL、连接池中的陈旧连接、网络瞬断。
    """
    if exc is None:
        return False

    if isinstance(exc, ConnectionRefusedError):
        return True

    if isinstance(exc, OSError) and getattr(exc, "errno", None) in (
        errno.ECONNREFUSED,
        errno.EHOSTUNREACH,
        errno.ENETUNREACH,
    ):
        return True

    orig = getattr(exc, "orig", None)
    if orig is not None and orig is not exc:
        if is_database_unreachable_error(orig):
            return True

    message = str(exc).lower()
    unreachable_markers = (
        "can't connect to mysql",
        "cannot connect to mysql",
        "connection refused",
        "lost connection to mysql",
        "server has gone away",
        "name or service not known",
        "temporary failure in name resolution",
    )
    if any(marker in message for marker in unreachable_markers):
        return True

    # SQLAlchemy / PyMySQL OperationalError 2003 = 无法连接
    code = getattr(exc, "args", ())
    if code and str(code[0]) == "2003":
        return True
    if orig is not None:
        orig_args = getattr(orig, "args", ())
        if orig_args and str(orig_args[0]) == "2003":
            return True

    return False


def is_duplicate_entry_error(exc: BaseException) -> bool:
    """判断是否为 MySQL 唯一键冲突（1062 Duplicate entry）。"""
    if exc is None:
        return False

    message = str(exc)
    if "1062" in message or "Duplicate entry" in message:
        return True

    orig = getattr(exc, "orig", None)
    if orig is not None and orig is not exc:
        return is_duplicate_entry_error(orig)

    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return is_duplicate_entry_error(cause)

    return False
