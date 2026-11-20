"""命令回复失败时的统一日志（识别拉黑等常见 Forbidden）。"""
import logging

logger = logging.getLogger(__name__)


def log_command_reply_failure(command: str, chat_id, exc: BaseException) -> None:
    """按错误类型打清晰日志，避免「命令无反应」时难以排查。"""
    msg = str(exc).lower()
    if "blocked by the user" in msg or "bot was blocked" in msg:
        logger.error(
            "[命令处理器] /%s 回复失败：用户已拉黑该 Bot；error_type=%s",
            command,
            type(exc).__name__,
        )
        return
    if "chat not found" in msg:
        logger.error(
            "[命令处理器] /%s 回复失败：Chat not found；error_type=%s",
            command,
            type(exc).__name__,
        )
        return
    if "can't parse entities" in msg or "can't find end of the entity" in msg:
        logger.error(
            "[命令处理器] /%s 回复失败：parse_mode 实体解析错误；error_type=%s",
            command,
            type(exc).__name__,
        )
        return
    logger.error(
        "[命令处理器] /%s 回复失败；error_type=%s",
        command,
        type(exc).__name__,
    )
