"""Postback 通知配置与信息辅助"""
import json
import logging
from typing import Any, Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.models import (
    PostbackConversion, Client, Product, User,
    ClientNotificationConfig, ProductNotificationConfig,
)

logger = logging.getLogger(__name__)


def should_notify(
    conversion: PostbackConversion,
    product_config: Optional[ProductNotificationConfig],
    client_config: Optional[ClientNotificationConfig]
) -> tuple[bool, str]:
    """
    判断是否需要发送通知

    Args:
        conversion: 转化记录
        product_config: 产品通知配置
        client_config: 客户通知配置

    Returns:
        (是否需要通知, 通知类型)
    """
    # 优先使用客户配置，如果没有则使用产品配置（与 notify_conversion 中的优先级保持一致）
    config = client_config if client_config else product_config

    # 如果没有配置，默认发送通知（向后兼容）
    if not config:
        return True, 'conversion'

    # 检查是否启用通知
    if not config.notification_enabled:
        return False, 'conversion'

    # 检查是否通知转化事件
    if not config.notify_on_conversion:
        # 如果配置了高价值通知，检查是否满足条件
        if config.notify_on_high_value and conversion.payout:
            threshold = config.high_value_threshold or 0
            if conversion.payout >= threshold:
                return True, 'high_value'
        return False, 'conversion'

    # 检查高价值转化通知
    if config.notify_on_high_value and conversion.payout:
        threshold = config.high_value_threshold or 0
        if conversion.payout >= threshold:
            return True, 'high_value'

    # 普通转化通知
    return True, 'conversion'

def get_notification_channels(
    config: Optional[Any]
) -> List[str]:
    """
    获取通知渠道列表

    Args:
        config: 通知配置对象

    Returns:
        通知渠道列表
    """
    if not config or not config.notify_channels:
        # 默认使用 Telegram（向后兼容）
        return ['telegram']

    try:
        channels = json.loads(config.notify_channels)
        if isinstance(channels, list):
            return channels
        return ['telegram']
    except (json.JSONDecodeError, TypeError):
        return ['telegram']

async def get_client_info(
    client: Optional[Client],
    db: AsyncSession
) -> tuple[str, Optional[str]]:
    """
    获取客户信息

    Args:
        client: 客户对象
        db: 数据库会话

    Returns:
        (客户名称, 用户全名)
    """
    if not client:
        return "未知客户", None

    client_name = client.company_name or f"客户_{client.id}"
    user_full_name = None

    if client.user_id:
        result = await db.execute(
            select(User).where(User.id == client.user_id)
        )
        user = result.scalars().first()
        if user:
            user_full_name = user.full_name or user.username

    return client_name, user_full_name

def get_product_name(product: Optional[Product]) -> str:
    """获取产品名称"""
    if not product:
        return "未知产品"
    return product.name or f"产品_{product.id}"

def detect_notification_channel(address: str) -> str:
    """
    检测通知地址类型

    Args:
        address: 通知地址

    Returns:
        通知渠道类型：telegram, email, webhook
    """
    address = address.strip()

    # 如果以 http:// 或 https:// 开头，是 Webhook URL
    if address.startswith('http://') or address.startswith('https://'):
        return 'webhook'

    # 如果包含 @，可能是邮箱地址
    if '@' in address:
        return 'email'

    # 默认作为 Telegram Chat ID 处理
    return 'telegram'
