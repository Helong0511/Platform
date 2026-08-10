"""Postback 通知消息构建"""
from typing import Optional, List

from app.models.models import PostbackConversion


def build_notification_message(
    conversion: PostbackConversion,
    client_name: str,
    product_name: str,
    user_full_name: Optional[str] = None,
    notification_type: str = 'conversion'
) -> str:
    """
    构建通知消息（符合文档模板格式）

    Args:
        conversion: 转化记录
        client_name: 客户名称
        product_name: 产品名称
        user_full_name: 用户全名（可选）
        notification_type: 通知类型

    Returns:
        通知消息文本
    """
    # 根据通知类型选择不同的标题
    if notification_type == 'high_value':
        msg = "💰 高价值转化通知\n\n"
    else:
        msg = "🔔 Postback 转化通知\n\n"

    # 客户信息（符合文档模板）
    if user_full_name:
        msg += f"客户：{user_full_name}\n"
    msg += f"产品：{product_name}\n"
    msg += f"平台：{conversion.platform.upper()}\n"
    msg += f"转化ID：{conversion.conversion_id}\n"

    if conversion.event_name:
        msg += f"事件：{conversion.event_name}\n"

    if conversion.event_value is not None:
        msg += f"价值：${conversion.event_value:.2f}\n"

    if conversion.payout is not None:
        msg += f"结算收益：${conversion.payout:.2f}\n"

    # 时间信息
    if conversion.created_at:
        time_str = conversion.created_at.strftime("%Y-%m-%d %H:%M:%S")
        msg += f"时间：{time_str}\n"

    return msg

def build_batch_notification_message(
    conversions: List[PostbackConversion],
    client_name: str,
    product_name: str,
    user_full_name: Optional[str] = None
) -> str:
    """
    构建批量通知消息

    Args:
        conversions: 转化记录列表
        client_name: 客户名称
        product_name: 产品名称
        user_full_name: 用户全名（可选）

    Returns:
        通知消息文本
    """
    # 基础信息
    msg = "📊 Postback 转化汇总通知\n\n"

    # 客户和产品信息
    if user_full_name:
        msg += f"客户：{user_full_name}\n"
    msg += f"产品：{product_name}\n\n"

    # 统计信息
    total_count = len(conversions)
    total_payout = sum(c.payout or 0 for c in conversions)
    total_value = sum(c.event_value or 0 for c in conversions)

    msg += f"转化数量：{total_count} 条\n"
    msg += f"总价值：${total_value:.2f}\n"
    msg += f"结算总收益：${total_payout:.2f}\n\n"

    # 按平台统计
    platform_stats = {}
    for conv in conversions:
        platform = conv.platform
        if platform not in platform_stats:
            platform_stats[platform] = {
                'count': 0,
                'payout': 0,
                'value': 0
            }
        platform_stats[platform]['count'] += 1
        platform_stats[platform]['payout'] += conv.payout or 0
        platform_stats[platform]['value'] += conv.event_value or 0

    if platform_stats:
        msg += "平台统计：\n"
        for platform, stats in platform_stats.items():
            msg += f"  • {platform.upper()}: {stats['count']} 条"
            msg += f", 结算收益: ${stats['payout']:.2f}\n"

    # 时间范围
    if conversions:
        first_time = conversions[0].created_at
        last_time = conversions[-1].created_at
        if first_time and last_time:
            msg += f"\n时间范围：{first_time.strftime('%Y-%m-%d %H:%M')} "
            msg += f"至 {last_time.strftime('%Y-%m-%d %H:%M')}\n"

    return msg
