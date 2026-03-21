"""
Postback 处理器注册表
注册各平台的 postback 处理器
"""
import logging
from app.core.postback.handlers import register_handler
from app.core.postback.bft_handler import BftPostbackHandler

logger = logging.getLogger(__name__)


def register_postback_handlers() -> None:
    """
    注册所有 postback 处理器
    """
    # 注册 BFT 平台处理器
    bft_handler = BftPostbackHandler()
    register_handler(bft_handler)
    logger.info("已注册 BFT 平台 postback 处理器")
