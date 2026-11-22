# Telegram 审批回调有界 Worker 与背压审计（2026-11-22）

## 范围

- 工作池：`app/core/telegram/approval_worker.py`
- 回调入口：`app/core/telegram/callback_handlers/postback_approval.py`
- 生命周期：`app/bootstrap/lifespan.py`
- 关联 Issue：#145

## 风险

原实现每个合法管理员回调都直接创建一个 daemon thread。回调突增或数据库变慢时，线程和同步 Session 数量随请求增长，可能耗尽进程资源和数据库连接池。

## 设计

使用进程内有界 `ThreadPoolExecutor`，限制：

- Worker：最多 4 个。
- 排队：最多 12 个。
- 在途任务总数：最多 16 个（活跃 + 排队）。

相同 `pending_id` 在本进程已有任务时不重复入队。该去重只用于节省资源；业务正确性仍由数据库行锁、状态检查和正式转化唯一约束保障。

提交结果：

- `submitted`：任务成功入队，再向管理员答复“正在处理”。
- `duplicate`：不创建第二个任务，提示记录正在处理。
- `full` / `shutting_down`：不入队，立即提示“审批队列繁忙，请稍后重试”，不改变业务状态。

## 可观测性

记录任务排队等待时间、执行耗时、活跃 worker、在途任务、队列深度、完成数、未处理异常数和拒绝数。状态查询函数 `get_approval_worker_status()` 返回不含用户敏感数据的计数。

## 优雅关闭

持有 Telegram polling 文件锁的 API worker 在停止 PTB Application 前：
1. 停止接受新审批任务；
2. 最多等待 8 秒排空在途任务；
3. 超时后取消尚未开始的排队 Future；
4. 记录仍在执行的任务数量；
5. 再停止 Telegram polling 和释放锁。

未开始的队列任务没有改变数据库 pending 状态，进程重启后仍可从待审批列表恢复。正在执行的任务不支持强制杀线程；它们依赖 DB/HTTP 超时自然结束。若超过 drain 时间，必须关注关闭日志中的 remaining 数量。此内存队列不是持久任务队列，不能承诺进程崩溃后自动恢复任务。

## 测试

- 并发提交达到 16 个在途任务后，第 17 个任务必须被拒绝。
- 相同 pending_id 不得重复入队。
- 活跃 worker 不得超过 4。
- shutdown 状态拒绝新任务。
- Telegram 回调入口对重复、队列满、关闭中分别返回明确提示。
- 需要 CI 通过后才能合并。

## 后续风险

- 多进程环境依赖 Telegram polling 单实例锁确保只有一个进程消费回调；若未来改成 webhook 或多实例消费，必须增加跨进程任务租约/数据库任务队列。
- 如需崩溃后自动重试，应升级为数据库 outbox/持久任务队列，并实现任务 lease、超时回收、幂等执行和审计，而不是单纯增加线程数。
