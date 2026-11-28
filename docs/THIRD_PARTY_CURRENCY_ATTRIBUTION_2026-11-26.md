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
- 斗篷 click/load/postback 三阶段配置默认 USD，并分别持久化 `*_currency_source`；新建时未显式配置标记 `system_fallback_usd`，管理员显式设置标记 `manual_override`，历史已有值暂标记 `legacy_unknown`。ORM、Schema、运行时映射和测试上报统一处理。
- Outbox 在入队时冻结币种及来源；Worker 重试沿用已持久化的币种和来源，不因配置变更重新推断。
- 直接发送、管理员编辑和测试发送均走同一 ISO 校验逻辑。
- `postback_conversions` 与 `pending_postback_conversions` 都持久化 payout 的 `currency` 和 `currency_source`；待审批通过时原样复制来源，通用适配器/BFT 的字段归因不会丢失。
- `conversion_deduction_logs` 保存扣量前/扣量后金额对应的币种和来源；历史日志存在 `conversion_id` 时可从正式转化记录恢复币种，否则保留 USD fallback。
- 三阶段斗篷配置分别持久化币种来源，click/load 的直接发送和 Postback Outbox 不再根据“有无配置行”猜测来源。
- `third_party_report_logs.currency_source` 持久化第三方上报币种来源，API 和管理端详情/列表可查看。

## ISO 4217 权威数据来源与结算代码范围

- ISO 4217 的官方维护机构为 SIX Financial Information。上线前应对照 SIX 的 Current Currency & Funds（List One）、Current Funds（List Two）和 Historical（List Three），不能仅用三位大写字母正则判断代码有效。
- 官方资料入口：https://www.six-group.com/en/products-services/financial-information/market-reference-data/data-standards.html
- 本项目锁定 pycountry 数据集作为运行时校验来源，并以 SIX 当前清单核验新增/撤销代码；基金单位、贵金属、测试代码、无货币代码不作为 Purchase/PO 结算货币。当前测试覆盖 XCG 当前代码及 BGN、ANG 等历史代码。
- ISO minor unit 与数据库精度是两个不同问题：币种代码有效，不代表当前金额列精度足以表达该币种。

## Offer PO 币种

- `offers.payout_currency` 和 `payout_currency_source` 已加入 ORM、Schema、建库基线及迁移 `20261127_offer_payout_currency`；未配置时 USD，来源 `system_fallback_usd`，显式配置来源 `manual_config`。
- 当前业务模型约定 Offer 上游 PO 与其默认/渠道下游 PO 使用同一币种。Postback 显式币种必须与 Offer 币种一致；回调未带币种时继承 Offer 币种。若业务允许同一 Offer 的上游与各渠道使用不同币种，必须进一步拆分为 Offer 上游币种、Offer 默认下游币种和每个 PublisherAssignment 独立币种，不能沿用当前单币种模型。
- Offer 已有正式转化或扣量财务凭证后禁止直接变更币种；新转化入账、待审批转正式入账与 Offer 币种修改共用 Offer 行锁，防止并发竞态。
- 斗篷 Postback Purchase 若使用动态上游 payout，继承上游币种；只有固定金额才使用斗篷配置币种，未配置时 USD 兜底。管理员显式配置币种与动态 payout 不一致时 fail-closed，不做无汇率换算。
- 下游 GET/POST 转发在发送前再次校验 ISO 4217，非法历史币种不会发往渠道。
- 转化总览按币种生成 `currency_summaries`；多币种结果的全局金额字段返回 NULL，不再跨币种 SUM。管理端明细、按币种汇总和 CSV 导出均保留币种。

## 其他收入数据的币种缺口（尚未修复，发布阻断）

- `ad_data` / `ad_data_archive` 的收入、eCPM、CPC 字段没有 currency/source；导入分组键与统计汇总也不区分币种。
- Google Ad Manager API 的 reportCurrency 未显式设置时默认使用 Network currency；项目当前只把 Network currency 打印到日志，没有把它持久化到 AdData。多 GAM Network 可能因此混币种汇总。
- `tb_search_data` 的 revenue/RPM 同样没有币种字段。
- 修复必须贯穿上游 API/Excel 导入、分组键、唯一键、主表/归档表、统计、导出和前端展示；缺失币种才按 USD 兜底并记录来源。不能只给历史金额加 USD 标签。

## 金额精度缺口（尚未修复，发布阻断）

当前 Offer PO 和扣量日志仍有 DECIMAL(...,2) 字段，而部分 Postback 金额已使用 DECIMAL(...,4)。KWD/BHD/JOD 等三位小数币种会在两位小数字段中丢失精度。MySQL 8.0 改变列数据类型需要评估 COPY 型 DDL 或采用影子列扩展/收缩迁移；未完成前不能宣称所有 ISO 4217 币种金额均可准确结算。
官方 DDL 参考：https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl-operations.html

## 历史数据处理

数据库迁移只执行元数据 DDL 和斗篷配置空值兜底，不在迁移中对 Postback 大表执行无界 UPDATE。迁移后必须先运行分批归因脚本：

```bash
# 默认只读预演，不写入
MIGRATION_DATABASE_URL='mysql+asyncmy://独立迁移账号:密码@主机:3306/数据库' python -m scripts.backfill_currency_attribution

# 审核 dry-run 输出后，显式启用分批写入
MIGRATION_DATABASE_URL='mysql+asyncmy://独立迁移账号:密码@主机:3306/数据库' python -m scripts.backfill_currency_attribution --apply --batch-size 500
```

脚本每批按主键扫描并提交，重跑时跳过已归因来源；输出各表币种/来源分组、ISO 无效数量及最多 200 条样例，不打印 DSN、原始 payload 或 PII。默认 dry-run；只有传入 `--apply` 才会写入。必须使用独立 `MIGRATION_DATABASE_URL`，不会回退到应用 DSN。

脚本处理后：

- 斗篷三阶段配置中 NULL/空白币种设置为 USD，并把数据库默认值设置为 USD。
- 历史正式/待审批 Postback 转化从原始 JSON 的 `currency` / `currency_code` / `currencyCode`（含 `_payload` 包装）还原币种和字段来源；确实缺失时设置 USD，来源为 `system_fallback_usd`。非空无效币种保留原值并列入异常清单，不会静默替换。
- 历史第三方 Purchase 日志中缺失币种的行设置为 USD，来源为 `system_fallback_usd`。
- 历史 Purchase 日志中已有非空币种的行来源标记为 `legacy_unknown`。迁移不猜测其来源，不修改已有币种和任何金额。
- 历史非空币种仍须由后续只读审计识别无效/撤销代码，并结合 Postback 原始数据、历史配置快照、报表参数及审计记录还原来源；无证据的行继续保持 `legacy_unknown`，不能伪造来源。

## 上线前必须执行的只读核验

1. 备份数据库并在生产结构副本执行迁移演练。
2. 对正式 Postback、待审批 Postback、扣量日志和第三方 Purchase 日志分别按 `currency, currency_source` 分组计数，核对 USD 回填数量与历史未知来源数量。
3. Postback 金额统计必须按 `platform + currency` 分组，禁止把不同币种的 payout 直接相加；管理端显示每条记录和统计分组的实际币种。
4. 从 Postback 原始 JSON 和斗篷配置快照核对每条 `legacy_unknown` 的真实来源；输出可追踪的明细，不修改金额。
5. 使用应用层 ISO 校验器对历史所有非空币种执行扫描，分别列出有效、撤销、无效和特殊用途代码。
6. 检查新建、编辑、直接发送、Outbox Worker、人工重试和管理端测试发送都保存正确的来源。
7. 仅在审计结果、迁移副本、MySQL 集成测试和当前 PR Head CI 全部通过后，才允许讨论发布。

## 关键限制

本迁移尚未执行于生产库。代码合并不等于生产数据已经归因或完成回填。PR 保持 Draft，未获明确授权前不合并、不部署、不执行生产迁移。
