# Postback 批量自动审批 SAVEPOINT 审计记录（2026-11-22）

## 范围

- 服务：`app/services/cpl/postback_pending_service.py`
- 方法：`PostbackPendingService.auto_approve_pending_by_ip`
- 关联问题：GitHub Issue #147
- 修复 PR：GitHub PR #148

## 原问题

批量审批在一个 AsyncSession 外层事务中循环处理多条待审批记录。每条记录可能创建正式转化、更新 pending 状态并写入审批审计。原实现捕获单条异常后继续循环，但没有建立 SAVEPOINT，也没有显式回滚当前记录。

数据库 flush 失败（例如唯一约束冲突）可能使当前事务进入需要回滚状态。捕获异常后继续使用同一事务不安全；若后续操作触发外层回滚，先前累计的成功计数和 ID 也可能与数据库实际提交结果不一致。

## 修复方案

1. 仍使用 `SELECT ... FOR UPDATE` 锁定目标 IP 下的 pending 记录。
2. 每条记录在 `async with db.begin_nested()` 内执行：
   - 查询正式转化是否已存在；
   - 不存在时创建正式转化并更新 pending 状态；
   - 写入审批审计；
   - 在 SAVEPOINT 内 flush，确保约束错误在保存点范围内暴露。
3. SAVEPOINT 正常释放后才增加 approved/skipped 计数。
4. 单条异常在 SAVEPOINT 回滚后计入 failed；如果 AsyncSession 外层事务已不 active，则升级为整批失败，不继续执行。
5. 整批失败时执行外层 rollback，并清零 approved_count、skipped_count 和 approved_ids。
6. 不在服务层 commit，保留现有请求事务边界。

## 事务语义

- 单条业务/约束错误：回滚当前 SAVEPOINT，其它记录可以继续。
- 外层事务失效或批次级错误：回滚整个批次，所有成功计数清零。
- 成功计数表示本方法内 SAVEPOINT 成功释放的记录数；最终持久化仍取决于调用方外层事务提交成功。
- 审批审计与对应业务变更位于同一 SAVEPOINT，避免单条业务状态与审计记录分离。

## 测试

新增 `tests/test_postback_bulk_auto_approval_savepoints.py`：

- 中间记录 flush 失败时，仅回滚该记录，前后记录可继续处理。
- 外层事务失效时，执行整批回滚，清空成功计数和 ID。

CI 还需验证现有后端测试、安全测试、依赖兼容测试和前端构建。应补充真实 MySQL/InnoDB SAVEPOINT + 唯一约束集成验证，不能仅凭 mock 测试宣称数据库行为已完全验收。

## 需要继续确认的边界

- API 请求事务提交失败时，调用方必须将请求视为失败；本方法返回的计数不是独立 commit 确认。
- 生产 MySQL 表必须使用支持事务和 SAVEPOINT 的 InnoDB。
- 仍需覆盖唯一约束冲突、Click 归因查询失败、审批审计插入失败和外层 commit 失败。
- 不得把所有 IntegrityError 一律视为重复转化；只有重新查询并确认同一幂等键已存在时，才可转为 already_exists。
