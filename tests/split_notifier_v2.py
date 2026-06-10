"""按行切片拆分 notifier.py"""
import pathlib
import textwrap

SRC = pathlib.Path("app/core/postback/notifier.py")
lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
base = pathlib.Path("app/core/postback/notification")

# 删除旧目录中的损坏文件
if base.exists():
    for f in base.glob("*.py"):
        f.unlink()
else:
    base.mkdir(parents=True)


def slice_dedent(start: int, end: int) -> str:
    chunk = "".join(lines[start - 1 : end])
    return textwrap.dedent(chunk)


def rename_funcs(body: str, mapping: dict[str, str]) -> str:
    for old, new in mapping.items():
        body = body.replace(f"def {old}(", f"def {new}(")
        body = body.replace(f"PostbackNotifier.{old}", new)
    return body


RENAME = {
    "_should_notify": "should_notify",
    "_get_notification_channels": "get_notification_channels",
    "_get_client_info": "get_client_info",
    "_get_product_name": "get_product_name",
    "_detect_notification_channel": "detect_notification_channel",
    "_build_notification_message": "build_notification_message",
    "_build_batch_notification_message": "build_batch_notification_message",
    "_send_notification_async": "send_notification_async",
    "_send_to_address": "send_to_address",
    "_send_webhook_notification": "send_webhook_notification",
    "_send_to_channel": "send_to_channel",
}

config_body = rename_funcs(
    slice_dedent(296, 403) + "\n" + slice_dedent(587, 609),
    RENAME,
)
config_helpers = (
    '"""Postback 通知配置与信息辅助"""\n'
    "import json\n"
    "import logging\n"
    "from typing import Any, Optional, List\n\n"
    "from sqlalchemy.ext.asyncio import AsyncSession\n"
    "from sqlalchemy.future import select\n\n"
    "from app.models.models import (\n"
    "    PostbackConversion, Client, Product, User,\n"
    "    ClientNotificationConfig, ProductNotificationConfig,\n"
    ")\n\n"
    "logger = logging.getLogger(__name__)\n\n\n"
    + config_body
)

message_body = rename_funcs(
    slice_dedent(405, 455) + "\n" + slice_dedent(879, 950),
    RENAME,
)
message_builder = (
    '"""Postback 通知消息构建"""\n'
    "from typing import Optional, List\n\n"
    "from app.models.models import PostbackConversion\n\n\n"
    + message_body
)

sender_body = rename_funcs(
    slice_dedent(457, 585)
    + "\n"
    + slice_dedent(611, 673)
    + "\n"
    + slice_dedent(675, 728)
    + "\n"
    + slice_dedent(730, 796),
    RENAME,
)
sender = (
    '"""Postback 通知发送"""\n'
    "import asyncio\n"
    "import logging\n"
    "from datetime import datetime, timezone\n"
    "from typing import Optional\n\n"
    "import httpx\n"
    "from sqlalchemy.ext.asyncio import AsyncSession\n\n"
    "from app.core.telegram import send_telegram_message_async\n"
    "from app.core.utils import get_app_now_naive\n"
    "from app.models.models import PostbackConversion, Client, Product, PostbackNotification\n"
    "from app.core.postback.notification.config_helpers import detect_notification_channel\n\n"
    "logger = logging.getLogger(__name__)\n\n\n"
    + sender_body
)

notify_conv_body = rename_funcs(slice_dedent(34, 295), RENAME)
notify_batch_body = rename_funcs(slice_dedent(798, 877), RENAME)

notifier_new = (
    '"""\n'
    "Postback 通知服务\n"
    "负责按客户和产品发送转化通知\n"
    "支持通知配置、高价值转化通知、通知频率控制等功能\n"
    '"""\n'
    "import asyncio\n"
    "import json\n"
    "import logging\n"
    "from typing import Optional, List\n\n"
    "from sqlalchemy.ext.asyncio import AsyncSession\n"
    "from sqlalchemy.future import select\n\n"
    "from app.models.models import (\n"
    "    PostbackConversion, Client, Product,\n"
    "    ClientNotificationConfig, ProductNotificationConfig,\n"
    ")\n"
    "from app.core.redis_client import get_redis_client\n"
    "from app.services.telegram_notification_service import TelegramNotificationService\n"
    "from app.core.postback.notification.config_helpers import (\n"
    "    should_notify,\n"
    "    get_notification_channels,\n"
    "    get_client_info,\n"
    "    get_product_name,\n"
    "    detect_notification_channel,\n"
    ")\n"
    "from app.core.postback.notification.message_builder import (\n"
    "    build_notification_message,\n"
    "    build_batch_notification_message,\n"
    ")\n"
    "from app.core.postback.notification.sender import (\n"
    "    send_notification_async,\n"
    "    send_to_address,\n"
    "    send_webhook_notification,\n"
    "    send_to_channel,\n"
    ")\n\n"
    "logger = logging.getLogger(__name__)\n\n"
    "NOTIFICATION_QUEUE_MAX_SIZE = 10000\n\n\n"
    "class PostbackNotifier:\n"
    '    """Postback 通知器（向后兼容门面）"""\n\n'
    "    _should_notify = staticmethod(should_notify)\n"
    "    _get_notification_channels = staticmethod(get_notification_channels)\n"
    "    _get_client_info = staticmethod(get_client_info)\n"
    "    _get_product_name = staticmethod(get_product_name)\n"
    "    _detect_notification_channel = staticmethod(detect_notification_channel)\n"
    "    _build_notification_message = staticmethod(build_notification_message)\n"
    "    _build_batch_notification_message = staticmethod(build_batch_notification_message)\n"
    "    _send_notification_async = staticmethod(send_notification_async)\n"
    "    _send_to_address = staticmethod(send_to_address)\n"
    "    _send_webhook_notification = staticmethod(send_webhook_notification)\n"
    "    _send_to_channel = staticmethod(send_to_channel)\n\n"
    + textwrap.indent(notify_conv_body.replace("@staticmethod\n    ", ""), "    ")
    + "\n\n"
    + textwrap.indent(notify_batch_body.replace("@staticmethod\n    ", ""), "    ")
    + "\n"
)

init_py = '''"""Postback 通知子模块"""
from app.core.postback.notification.config_helpers import (
    should_notify,
    get_notification_channels,
    get_client_info,
    get_product_name,
    detect_notification_channel,
)
from app.core.postback.notification.message_builder import (
    build_notification_message,
    build_batch_notification_message,
)
from app.core.postback.notification.sender import (
    send_notification_async,
    send_to_address,
    send_webhook_notification,
    send_to_channel,
)

__all__ = [
    "should_notify",
    "get_notification_channels",
    "get_client_info",
    "get_product_name",
    "detect_notification_channel",
    "build_notification_message",
    "build_batch_notification_message",
    "send_notification_async",
    "send_to_address",
    "send_webhook_notification",
    "send_to_channel",
]
'''

(base / "config_helpers.py").write_text(config_helpers, encoding="utf-8")
(base / "message_builder.py").write_text(message_builder, encoding="utf-8")
(base / "sender.py").write_text(sender, encoding="utf-8")
(base / "__init__.py").write_text(init_py, encoding="utf-8")
SRC.write_text(notifier_new, encoding="utf-8")
print("notifier split v2 done")
