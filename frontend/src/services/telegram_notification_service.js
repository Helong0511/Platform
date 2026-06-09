/**
 * Telegram 通知服务（前端）
 * @file services/telegram_notification_service.js
 *
 * 构建各类通知的测试消息预览文本，供配置页发送测试通知使用。
 */

export class TelegramNotificationService {
  /**
   * 构建测试消息
   * @param {string} messageType - 消息类型（conversion, forward_failure, system_error）
   * @returns {string} 测试消息
   */
  static buildTestMessage(messageType = 'conversion') {
    if (messageType === 'conversion') {
      return `📊 Postback 转化通知（管理员）

转化ID: TEST_CONVERSION_ID
平台: TEST_PLATFORM
事件: purchase

💰 金额信息
• 原始金额 (PO): $10.00
• 扣后金额 (PO(扣)): $8.50

👤 客户信息
• 客户: 测试客户
• 产品: 测试产品

📤 渠道信息
• 渠道ID: 1
• 渠道名称: 测试渠道

⏰ 时间: 2026-01-12 15:00:00`;
    } else if (messageType === 'forward_failure') {
      return `❌ Postback 转发失败告警

转化ID: TEST_CONVERSION_ID
平台: TEST_PLATFORM

📤 渠道信息
• 渠道ID: 1
• 渠道名称: 测试渠道
• Postback URL: https://example.com/postback

❌ 错误信息
HTTP 400: Bad Request

📋 点击参数
{"click_id": "1230180"}

⏰ 时间: 2026-01-12 15:00:00`;
    } else if (messageType === 'system_error') {
      return `⚠️ 系统异常告警

类型: 错误
描述: 测试系统异常

📍 位置
• 模块: test_module
• 函数: test_function
• 行号: 100

⏰ 时间: 2026-01-12 15:00:00`;
    } else {
      return `🔔 Telegram 通知测试

这是一条测试消息。`;
    }
  }
}
