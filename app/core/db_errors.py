"""
数据库连接类异常判断。

用于调度器、维护窗口等场景：区分「库不可达」与真实业务/锁错误，避免误报 ERROR。
"""
from __future__ import annotations

import errno


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

    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return is_database_unreachable_error(cause)

    return False
