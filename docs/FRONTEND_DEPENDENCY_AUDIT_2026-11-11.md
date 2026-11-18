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
| `eslint` | 8.57.0 | 10.14.0 | 迁移到当前支持版本及 flat config |
| `eslint-plugin-vue` | 9.28.0 | 10.11.1 | 支持 ESLint 10 / Vue 3 flat config |
| `minimatch` | 10.2.6 | 11.0.5 | 修复 GHSA-g3hv-75wg-m249；按 ESLint 上游已合并的兼容更新覆盖其受限依赖范围 |

使用 npm lockfile-only 安装和审计修复在 CI 工作区重新生成锁文件；`follow-redirects` 通过 override 固定为 `1.16.0`，避免本轮修改凭据安全专项。

## 剩余告警

修复后，CI npm audit 报告：

- 全部依赖：2 项 High、0 Moderate。
- 生产依赖：2 项 High、0 Moderate。
- 两项均来自 `follow-redirects@1.16.0`，涉及跨域敏感请求头转发与凭据暴露，属于本轮明确排除的凭据安全范围。
- `axios` 的剩余 audit 记录是由该 `follow-redirects` 子依赖引起，不是 Axios 自身其他公告仍未修复。

## 依赖维护结果与剩余工作

ESLint 10 迁移已完成并通过 CI lint/build/E2E：

- `eslint@10.14.0`、`eslint-plugin-vue@10.11.1`、`@stylistic/eslint-plugin@5.10.0`、`@eslint/js@10.0.1`、`globals@17.14.0`。
- 删除旧 `.eslintrc.cjs`，改用 `eslint.config.js`。
- 旧依赖链 `glob@7`、`rimraf@3`、`inflight`、`@humanwhocodes/config-array`、`@humanwhocodes/object-schema` 已从 lockfile 消失。
- 新增 `minimatch@11.0.5` override。ESLint 上游已合并 #21492，将 minimatch 提升到 11.0.1+；本项目所用 ESLint / config-array 仅使用 v11 保留的 `Minimatch` 构造和 `match` API。参考：https://github.com/eslint/eslint/issues/21463

剩余两项 High 都来自 `follow-redirects@1.16.0`，与凭据敏感头转发有关，按本轮范围明确保留，不通过忽略审计或降低审计级别隐藏。

## 验证记录

CI #634（提交 `d99b25703295a3bafe3ab29fb210508b62ff182a`）：

- 后端：230 passed、1 skipped。
- 前端：ESLint 10 flat config 的 Lint、Build、Playwright E2E 通过。
- npm audit：2 High、0 Moderate；均为明确排除的 `follow-redirects` 凭据安全告警。
- 浏览器 E2E 使用 Mock API 和隔离前端服务。
- CI 中使用的 MySQL / Redis 均为临时服务。

CI 在后端和前端检查全部通过后，将生成的 lockfile 自动提交到修复分支。仍需由后续 CI 在不再临时重生成的情况下直接执行 `npm ci`，确认仓库提交的 lockfile 本身可复现。
