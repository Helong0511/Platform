# Postback GET 查询参数重复问题审计（2026-11-22）

## 结论

渠道级与产品级 Postback 的 GET 请求此前可能重复发送同一组查询参数。

## 根因

`UrlBuilder.build_postback_url()` 同时返回：
- 已经包含合并查询参数的 `final_url`
- 同一组参数字典 `params`

两个转发入口将 `final_url` 和 `params` 一起传给 `HttpClient.send_request()`。HTTPX 会将 URL 自带的查询参数与显式 `params` 合并，因此同名参数可能出现两份。对依赖单值参数的下游系统，这可能造成解析差异、归因错误或验签失败。

HTTPX 官方文档明确说明查询参数会合并：
- https://www.python-httpx.org/advanced/clients/

## 修复

- GET 请求只发送已经构建完成的 `final_url`，不再额外传入 `params`。
- 原始参数字典仍用于脱敏字段数量日志，不记录参数值。
- 渠道级与产品级转发采用相同处理。
- 新增回归测试，检查原有 URL 查询参数、conversion_id、click_id、clickid、offer_id 均只出现一次。

## 验收边界

PR CI 通过后，可确认代码级回归测试与现有自动化检查通过；仍需使用真实下游沙箱验证各渠道的参数解析、签名规则和响应成功判定。不得用生产真实转化数据进行测试。
