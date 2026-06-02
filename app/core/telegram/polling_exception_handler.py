"""
Telegram Bot 轮询异常处理器

在 pyTelegramBotAPI 轮询线程内拦截临时网络错误，避免 ERROR 堆栈刷屏，
并在 409 冲突时主动停止轮询。
"""
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Telegram API 临时性 HTTP 错误码
_TRANSIENT_API_ERROR_CODES = frozenset({502, 503, 504})

# 字符串匹配用的临时网络错误关键词
_TRANSIENT_NETWORK_KEYWORDS = (
    "502",
    "503",
    "504",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "timeout",
    "timed out",
    "connection",
    "network",
    "urllib3",
    "requests",
    "remotedisconnected",
    "connectionreset",
    "connection aborted",
    "connection reset",
)


def is_telegram_conflict_error(error_msg: str) -> bool:
    """是否为多实例轮询冲突（409）。"""
    return (
        "409" in error_msg
        or "Conflict" in error_msg
        or "terminated by other getUpdates" in error_msg
    )


def is_transient_telegram_network_error(exception: BaseException) -> bool:
    """判断是否为可自动恢复的临时网络/API 错误。"""
    error_msg = str(exception)

    if is_telegram_conflict_error(error_msg):
        return False

    error_code = getattr(exception, "error_code", None)
    if error_code in _TRANSIENT_API_ERROR_CODES:
        return True

    msg_lower = error_msg.lower()
    return any(keyword in msg_lower for keyword in _TRANSIENT_NETWORK_KEYWORDS)


class TelegramPollingExceptionHandler:
    """轮询异常处理器，供 TeleBot(exception_handler=...) 使用。"""

    def __init__(self, on_conflict: Optional[Callable[[BaseException], None]] = None):
        self.on_conflict = on_conflict
        self.conflict_detected = False

    def handle(self, exception: BaseException) -> bool:
        """
        处理轮询异常。

        Returns:
            True 表示已处理，库内不再打 ERROR / 不再向外抛出；
            False 表示未处理，交由库默认逻辑。
        """
        error_msg = str(exception)

        if is_telegram_conflict_error(error_msg):
            self.conflict_detected = True
            logger.error("检测到 Telegram 轮询冲突（409），停止当前实例：%s", error_msg)
            if self.on_conflict:
                try:
                    self.on_conflict(exception)
                except Exception as callback_err:
                    logger.warning("409 冲突回调执行失败：%s", callback_err)
            return True

        if is_transient_telegram_network_error(exception):
            logger.warning("Telegram 轮询临时网络错误，将自动重试：%s", error_msg)
            return True

        return False
