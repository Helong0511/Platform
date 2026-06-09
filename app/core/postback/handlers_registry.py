"""
Postback 平台处理器注册入口。

职责：应用启动时向 ``handlers`` 注册表挂载各上游（如 BFT）的解析实现。

在系统中的位置：由 ``postback.__init__`` 导入时自动执行 ``register_postback_handlers()``。
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
