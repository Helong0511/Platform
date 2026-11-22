# Postback 转发日志 URL 凭据脱敏审计（2026-11-22）

## 问题

转发日志 API 原先通过 `urlsplit(url).netloc` 生成脱敏 URL。URL 的 netloc 可能包含
`username:password@` userinfo，因此即使删除路径和查询参数，仍可能把下游 Basic Auth
用户名、密码或令牌返回给管理端调用方。

## 修复

- 新增统一 URL 脱敏函数，仅返回 HTTP/HTTPS 协议、主机名和端口。
- 不返回 URL userinfo、路径、查询参数或片段。
- IPv6 主机名使用方括号格式。
- 非 HTTP(S)、缺少主机、非法端口或解析失败时返回固定脱敏文本。
- 不读取、不输出任何仓库或生产环境中的真实凭据。

## 回归验证

`tests/test_postback_forward_log_url_redaction.py` 覆盖：
- 带用户名/密码的下游 URL；
- URL 查询参数和片段；
- IPv6 与端口；
- 非法端口、非法 URL、空值。

## 范围与限制

本修复保护转发日志 API 的 URL 展示字段，不代表已经轮换历史泄露的下游凭据。
若真实凭据曾通过日志、API 或仓库暴露，仍须按凭据管理流程独立评估并轮换。
