# Agent 强制须知（本仓库）

本文件对所有在本仓库工作的 Agent **强制生效，不可跳过、不可选择性忽略**。

## 必须遵守的项目规则

每次任务开始前，视为已完整加载并执行以下规则（均在 `.cursor/rules/`，且均为 `alwaysApply: true`）：

| 规则 | 要求 |
|------|------|
| `simplified-chinese.mdc` | 思考、对话、提示、说明一律简体中文 |
| `version-changelog.mdc` | 修问题 / 改行为必须写入 `平台版本迭代报告.md` 的 5.1 |
| `sync-related-changes.mdc` | 改一处必须排查并同步所有关联处 |
| `sync-platform-sql.mdc` | 新增/变更表或表结构必须同步 `sql/platform.sql` |
| `local-db-upgrade-sql.mdc` | 测库只连本地 Windows；改表结构必须出升迁 SQL 并本地验证 |
| `production-env.mdc` | 本地/生产环境与凭据；**未经当次明确同意禁止连接或操作生产** |
| `client-no-deduct-label.mdc` | 客户登录后可见信息**禁止**出现「扣减后」等扣减字样 |
| `client-api-ad-data.mdc` | 客户 API（`/client_data`）`data_type` / `dimension` 口径（day/all、默认 country、全量须显式 all） |
| `ad-data-dimension.mdc` | 广告数据 Excel/上游入库维度与日汇总互斥（country 优先） |
| `upstream-api-integration.mdc` | **每次**上游 API 拉数须检查：字段映射、类型/单位/小数、逻辑、容错跳过、tests |
| `project-conventions.mdc` | 测试目录、Aya/FlyMobi/ZhiSuo 显式 report_type、标准维度范围、生产环境摘要 |

若规则文件存在但上下文中未带上，Agent **仍须按上表执行**；不得以「未加载规则」为由省略。

## 硬性检查（交付前）

完成涉及修复或行为变更的任务时，交付前自检：

1. 回复是否为简体中文？
2. 关联的前后端 / 配置 / 测试是否已同步或已说明不同步原因？
3. 是否已追加 `平台版本迭代报告.md` → 5.1？
4. 若新增/变更了表或表结构，是否已同步 `sql/platform.sql`，并已出升迁 SQL、在本地 Windows 库验证？
5. 是否误连/误操作生产（须有当次明确同意），或在可提交文件中泄露密码？
6. 客户可见文案/API/导出是否仍含「扣减后」「减扣后」「(扣)」等字样（须无）？
7. 若涉及上游 API 拉数对接：是否已按 `upstream-api-integration.mdc` 逐项检查并补 tests？

任一项未满足则不得视为任务完成。

**生产**：未获用户当次明确同意（如「同意连接生产」），禁止 SSH/连生产库/改生产配置或部署。仅说「修复」不算同意。

## 环境摘要（无密钥）

- 本地测试：Windows 11 + Redis + MySQL 8.0
- 生产服务器：Ubuntu 22.04.5（SSH/库账号见 `.cursor/rules/production-env.mdc`，勿写入本文件或 Git）
