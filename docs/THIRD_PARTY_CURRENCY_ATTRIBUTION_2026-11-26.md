# 第三方 Purchase 币种校验与来源归因（2026-11-26）

## 业务规则

1. 所有 Purchase 发送入口必须使用 ISO 4217 当前有效结算货币代码。
2. 输入币种先去除首尾空格并转为大写。
3. 币种缺失、NULL 或空白时，统一兜底为 USD，并标记 `system_fallback_usd`。
4. 非空但不属于当前有效 ISO 4217 结算货币的值必须拒绝；不得把拼写错误、撤销代码、测试代码、无货币代码、贵金属代码、基金单位静默改成 USD。
5. 金额不因币种兜底而换算，金额数值保持不变。
6. 来源必须可审计，来源信息不包含原始回调全文或 PII。

## 来源枚举

| 来源 | 说明 |
|---|---|
| `upstream_field:<field>` | 上游回调原始币种字段，例如 currency_code |
| `cloak_config:<phase>:<id>` | 斗篷配置来源，phase 为 click/load/postback |
| `system_fallback_usd` | 上游与配置均缺失，系统按业务规则兜底 USD |
| `manual_override` | 管理员手动修改币种 |
| `caller_supplied` | 直接调用方提供币种但未给出更细来源 |
| `legacy_unknown` | 历史非空币种无法仅凭旧日志证明来源，等待证据归因 |

## 实施范围

- ISO 4217 校验集中在 `app/core/third_party_currency.py`，币种数据由锁定版本的 pycountry 提供。
- 通用 Postback normalizer 和 BFT handler 识别 `currency`、`currency_code`、`currencyCode`，并记录实际命中的字段名。
- 斗篷 click/load/postback 三阶段配置默认 USD；ORM、Schema、运行时映射和测试上报统一处理。
- Outbox 在入队时冻结币种及来源；Worker 重试沿用已持久化的币种和来源，不因配置变更重新推断。
- 直接发送、管理员编辑和测试发送均走同一 ISO 校验逻辑。
- `third_party_report_logs.currency_source` 持久化来源，API 和管理端详情/列表可查看。

## 历史数据处理

迁移只执行以下变更：

- 斗篷三阶段配置中 NULL/空白币种设置为 USD，并把数据库默认值设置为 USD。
- 历史 Purchase 日志中缺失币种的行设置为 USD，来源为 `system_fallback_usd`。
- 历史 Purchase 日志中已有非空币种的行来源标记为 `legacy_unknown`。迁移不猜测其来源，不修改已有币种和任何金额。
- 历史非空币种仍须由后续只读审计识别无效/撤销代码，并结合 Postback 原始数据、历史配置快照、报表参数及审计记录还原来源；无证据的行继续保持 `legacy_unknown`，不能伪造来源。

## 上线前必须执行的只读核验

1. 备份数据库并在生产结构副本执行迁移演练。
2. 对 Purchase 日志按 `currency, currency_source` 分组计数，核对 USD 回填数量与历史未知来源数量。
3. 从 Postback 原始 JSON 和斗篷配置快照核对每条 `legacy_unknown` 的真实来源；输出可追踪的明细，不修改金额。
4. 使用应用层 ISO 校验器对历史所有非空币种执行扫描，分别列出有效、撤销、无效和特殊用途代码。
5. 检查新建、编辑、直接发送、Outbox Worker、人工重试和管理端测试发送都保存正确的来源。
6. 仅在审计结果、迁移副本、MySQL 集成测试和当前 PR Head CI 全部通过后，才允许讨论发布。

## 关键限制

本迁移尚未执行于生产库。代码合并不等于生产数据已经归因或完成回填。PR 保持 Draft，未获明确授权前不合并、不部署、不执行生产迁移。
