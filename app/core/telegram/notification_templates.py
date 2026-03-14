"""
Telegram 通知模板模块

提供各类通知的模板和格式化功能
"""
from typing import Optional, Dict, Any
from datetime import datetime


class ConversionNotificationTemplate:
    """转化通知模板"""
    
    @staticmethod
    def format_conversion(
        platform: str,
        conversion_id: str,
        event_name: str,
        payout: float,
        product_name: str = '',
        advertiser_name: str = '',
        publisher_name: str = ''
    ) -> str:
        """
        格式化转化通知
        
        Args:
            platform: 平台名称
            conversion_id: 转化 ID
            event_name: 事件名称
            payout: 金额
            product_name: 产品名称
            advertiser_name: 广告主名称
            publisher_name: 渠道名称
        
        Returns:
            str: 格式化后的通知消息
        """
        lines = [
            "💰 <b>新转化通知</b>",
            "",
            f"平台：{platform}",
            f"转化 ID: {conversion_id}",
            f"事件：{event_name}",
            f"金额：${payout:.4f}",
        ]
        
        if product_name:
            lines.append(f"产品：{product_name}")
        if advertiser_name:
            lines.append(f"广告主：{advertiser_name}")
        if publisher_name:
            lines.append(f"渠道：{publisher_name}")
        
        return '\n'.join(lines)
    
    @staticmethod
    def format_pending_approval(
        platform: str,
        conversion_id: str,
        payout: float,
        ip: str,
        pending_id: int
    ) -> tuple[str, list]:
        """
        格式化待审批转化通知（带按钮）
        
        Args:
            platform: 平台名称
            conversion_id: 转化 ID
            payout: 金额
            ip: IP 地址
            pending_id: 待确认记录 ID
        
        Returns:
            tuple: (消息文本，按钮列表)
        """
        message = (
            f"⚠️ <b>待确认转化</b>\n\n"
            f"平台：{platform}\n"
            f"转化 ID: {conversion_id}\n"
            f"金额：${payout:.4f}\n"
            f"IP: {ip}\n\n"
            f"请确认是否批准此转化："
        )
        
        buttons = [
            [
                {'text': '✅ 批准', 'callback_data': f'postback_approve_{pending_id}'},
                {'text': '❌ 拒绝', 'callback_data': f'postback_reject_{pending_id}'}
            ]
        ]
        
        return message, buttons


class SystemNotificationTemplate:
    """系统通知模板"""
    
    @staticmethod
    def format_forward_failure(
        platform: str,
        conversion_id: str,
        publisher_name: str,
        error_message: str
    ) -> str:
        """
        格式化转发失败通知
        
        Args:
            platform: 平台名称
            conversion_id: 转化 ID
            publisher_name: 渠道名称
            error_message: 错误信息
        
        Returns:
            str: 格式化后的通知消息
        """
        return (
            f"❌ <b>Postback 转发失败</b>\n\n"
            f"平台：{platform}\n"
            f"转化 ID: {conversion_id}\n"
            f"渠道：{publisher_name}\n"
            f"错误：{error_message}"
        )
    
    @staticmethod
    def format_system_error(
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        格式化系统错误通知
        
        Args:
            error_type: 错误类型
            error_message: 错误信息
            context: 上下文信息
        
        Returns:
            str: 格式化后的通知消息
        """
        lines = [
            "🚨 <b>系统错误</b>",
            "",
            f"类型：{error_type}",
            f"错误：{error_message[:200]}",  # 限制长度
        ]
        
        if context:
            lines.append("")
            lines.append("上下文:")
            for key, value in context.items():
                lines.append(f"  {key}: {value}")
        
        return '\n'.join(lines)


class StatisticsNotificationTemplate:
    """统计通知模板"""
    
    @staticmethod
    def format_hourly_stats(
        total_conversions: int,
        total_payout: float,
        total_clicks: int,
        period: str
    ) -> str:
        """
        格式化小时统计
        
        Args:
            total_conversions: 总转化数
            total_payout: 总金额
            total_clicks: 总点击数
            period: 时间段
        
        Returns:
            str: 格式化后的通知消息
        """
        return (
            f"📊 <b>小时统计报告</b>\n\n"
            f"时间段：{period}\n"
            f"转化数：{total_conversions}\n"
            f"总金额：${total_payout:.2f}\n"
            f"点击数：{total_clicks}\n"
            f"转化率：{(total_conversions/total_clicks*100) if total_clicks > 0 else 0:.2f}%"
        )
    
    @staticmethod
    def format_daily_stats(
        total_conversions: int,
        total_payout: float,
        total_clicks: int,
        date: str
    ) -> str:
        """
        格式化每日统计
        
        Args:
            total_conversions: 总转化数
            total_payout: 总金额
            total_clicks: 总点击数
            date: 日期
        
        Returns:
            str: 格式化后的通知消息
        """
        return (
            f"📊 <b>每日统计报告</b>\n\n"
            f"日期：{date}\n"
            f"转化数：{total_conversions}\n"
            f"总金额：${total_payout:.2f}\n"
            f"点击数：{total_clicks}\n"
            f"转化率：{(total_conversions/total_clicks*100) if total_clicks > 0 else 0:.2f}%"
        )
