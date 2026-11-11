# 前端依赖安全审计记录（2026-11-11）

## 审计范围与边界

- 审计对象：`frontend/package.json`、`frontend/package-lock.json`。
- 审计方式：CI 临时工作区执行 `npm audit --json` 和 `npm audit --omit=dev --json`。
- 不访问生产服务器、生产数据库、Redis、缓存或真实第三方接口。
- 本轮不处理凭据安全专项。特别是 `follow-redirects` 的跨域敏感请求头告警，暂时保留版本 `1.16.0`，不主动升级。

## 已处理的非凭据依赖风险

根据 npm audit 返回的可用兼容修复版本：

| 依赖 | 原版本 | 修复版本 | 说明 |
|---|---:|---:|---|
| `vue` | 3.5.22 | 3.5.45 | 修复 Vue / server-renderer 高危 XSS 公告 |
| `vite` | 7.3.6 | 7.3.8 | 修复 Vite 开发服务器及相关工具公告 |
| `axios` | 1.18.1 | 1.21.1 | 修复多项非凭据类原型污染、DoS、SSRF 等公告；没有改动应用认证/凭据处理逻辑 |
| `source-map-js` | 1.2.1 | 1.2.2 | 修复 source-map 解析 DoS |
| `brace-expansion` | 1.1.18 | 1.1.21 | 修复嵌套展开导致的 CPU / 栈耗尽 |
| `js-yaml` | 4.3.1 | 4.3.2 | 修复 merge key 处理 CPU 风险 |
| `postcss-selector-parser` | 6.1.4 | 6.1.6 | 修复选择器解析复杂度 DoS |

使用 npm lockfile-only 安装和审计修复在 CI 工作区重新生成锁文件；`follow-redirects` 通过 override 固定为 `1.16.0`，避免本轮修改凭据安全专项。

## 剩余告警

修复后，CI npm audit 报告：

- 全部依赖：2 项 High。
- 生产依赖：2 项 High。
- 两项均来自 `follow-redirects@1.16.0`，涉及跨域敏感请求头转发与凭据暴露，属于本轮明确排除的凭据安全范围。
- `axios` 的剩余 audit 记录是由该 `follow-redirects` 子依赖引起，不是 Axios 自身其他公告仍未修复。

## 尚未完成的依赖维护

以下项目目前仍会产生弃用提示，但不属于本次 npm audit 剩余的两个漏洞：

- `eslint@8.57.0` 已停止支持。
- `glob@7.2.3`、`rimraf@3.0.2`、`inflight@1.0.6` 仍由旧 ESLint 依赖链引入。
- `@humanwhocodes/config-array` 与 `@humanwhocodes/object-schema` 已弃用。

不能只强制覆盖这些传递依赖。下一步需要将 ESLint 迁移到 flat config，并核验 `eslint-plugin-vue` 的兼容性，再重新生成 lockfile 和运行完整前端测试。

## 验证记录

CI #621（提交 `fa904c4d1e503cf5c47f9acc4ee16cf2276ff49e`）：

- 后端：230 passed、1 skipped。
- 前端：Lint、Build、Playwright E2E 通过。
- 浏览器 E2E 使用 Mock API 和隔离前端服务。
- CI 中使用的 MySQL / Redis 均为临时服务。

锁文件由 CI 生成并作为工件上传；受限的自动提交步骤将在后续 CI 完整通过后，把同一份已验证锁文件写回修复分支。锁文件提交并在不再临时重生成的情况下再次通过 CI 前，不得将 PR 标记为可合并。
