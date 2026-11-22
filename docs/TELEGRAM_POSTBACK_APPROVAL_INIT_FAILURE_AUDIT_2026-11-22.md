# Telegram Postback 审批初始化失败与最终反馈审计（2026-11-22）

## 范围

- 文件：`app/core/telegram/callback_handlers/postback_approval.py`
- 函数：`process_pending_conversion`、`handle_postback_approval`
- 关联 Issue：#144
- 修复 PR：待创建

## 原问题

后台线程启动后，在主事务异常处理边界之外读取配置、导入模块、创建发送 Bot、获取同步 Session 工厂。上述步骤任一抛异常，都可能让线程在“正在处理”答复后直接退出，管理员收不到最终状态。

另一个状态边界是业务数据库 commit 已成功，但 commit 后的 refresh/通知阶段再失败。若统一报“处理失败”，会让管理员误以为审批未执行，从而重复操作。

## 修复

1. 将配置读取、依赖导入、Bot 创建、Session 工厂初始化统一纳入最外层异常边界。
2. Bot 初始化失败时，使用回调处理器原 PTB Bot 作为应急发送通道；应急发送通过原 PTB asyncio 事件循环 `run_coroutine_threadsafe` 回投，避免跨线程/跨事件循环直接使用 PTB HTTP 客户端。
3. 记录 `business_committed` 状态。数据库 commit 前失败，提示“处理失败，请稍后重试”；commit 后发生 refresh/通知等错误，提示“审批已完成，但消息更新失败，请刷新记录状态”。
4. 日志仅记录 pending ID、commit 状态和异常类型，不输出异常正文、Token 或完整聊天 ID。
5. 新增测试覆盖 Bot 初始化失败、Session 工厂初始化失败、commit 成功后 refresh 失败。

## 事务与反馈原则

- 最终提示必须服从数据库事实，不能把已提交审批误报为失败。
- Telegram 消息编辑失败不回滚已经提交的业务状态。
- 应急 Bot 只能在 PTB 原事件循环中使用，禁止把其 HTTP 客户端跨线程直接交给发送线程。
- 若 Bot 和 PTB 事件循环都不可用，系统只能记录安全错误日志；无法保证 Telegram 远程回调必然送达。

## 验收

- CI 必须通过。
- 需要验证 get_send_bot 异常、Session 工厂异常、DB commit 失败、DB commit 成功后 refresh 失败。
- 后续仍需处理审批任务无界 daemon thread（Issue #145）和 polling 恢复监督（Issue #132）。
