# Telegram 旧版待审批通知 IP 脱敏审计

日期：2026-11-22

## 发现

项目已有 `ConversionNotificationTemplate.format_pending_approval`，会将 IPv4
显示为前三段网段摘要、IPv6 显示为 /64 网段，并隐藏非法输入。但
`TelegramNotificationService.build_pending_conversion_message` 旧入口直接将
`pending_conversion.request_ip` 拼入消息，未复用该掩码规则。

这会导致同一待审批事件在不同通知模板中的隐私保护不一致。

## 修复

旧入口统一调用 `_mask_ip_for_telegram`：
- IPv4 仅显示前三段，最后一段掩码；
- IPv6 仅显示 /64 网络前缀；
- 非法输入固定显示隐藏标记；
- 不改数据库中来源 IP 的存储和审批核验逻辑。

## 回归测试

直接调用旧入口，覆盖 IPv4、IPv6 和非法 IP，确保完整地址及恶意输入不出现在通知文本中。

## 范围

本次只修复 Telegram 待审批消息的展示层，不更改待审批记录的保留期限。终态 PII 清理仍受现有配置和业务审批约束。
