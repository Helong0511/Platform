# Telegram 轮询停止、重启与进程锁审计（2026-11-22）

## 已确认的高风险问题

### 1. Application.stop 不会停止 Updater

PTB 22.8 官方明确说明 `Application.stop()` 不会停止 `Updater`。旧实现从管理线程向 Application 调用 `app.stop()`，随后就把状态重置为 stopped；但 `run_polling()` 仍可能继续运行，继续拉取 Updates。

### 2. 旧线程未退出仍启动新线程

旧 `restart_bot_thread()` 在 join 超时后仅写 warning，却继续释放锁、清理共享状态并启动新线程。这会允许两个 polling consumer 同时使用一个 Bot Token，触发 409 Conflict，或让实际运行状态与共享状态不一致。

### 3. 事件循环线程归属错误

旧代码尝试读取 PTB 私有 `app._loop` / `updater._loop`，再直接从管理线程调用 `stop_running()`。PTB 的停止方法必须在运行事件循环中执行；直接跨线程调用不安全。

### 4. 文件锁删除竞态与过期误判

- 锁文件时间戳只在启动时写入，没有续期；运行超过一小时会被误判过期。
- `release_bot_lock()` 先解锁/关闭再 unlink；另一进程可能在 unlink 前后获得旧 inode，第三个进程又创建新 inode，形成双锁窗口。
- 旧实现 `open(path, 'w')` 会在拿到 OS 锁前先截断文件。
- 旧释放逻辑总是删除默认锁路径，忽略调用方传入的自定义锁路径。
- 没有 fcntl/msvcrt 时退化为普通文件存在性检查，不具备可靠互斥保证。

## 修复

- 保存 TelegramBot 专用事件循环引用；管理线程通过 `loop.call_soon_threadsafe(application.stop_running)` 发出停止请求。
- 409 错误处理器在其自身事件循环中调用 `stop_running()`，让 PTB `run_polling()` 执行 Updater.stop、Application.stop 和 shutdown 的完整流程。
- 不再在 stop 请求后立即清理 Application 状态；由轮询线程 finally 在真正退出后统一清理。
- restart 必须 join 成功；超时就 fail closed，不释放旧锁、不清状态、不启动新实例。
- 文件锁使用 OS `flock` 或 `msvcrt.locking` 作为唯一互斥判据；打开文件时不截断，写元数据在获得锁后进行。
- 释放时只解锁并关闭句柄，不删除锁文件，保持 inode 稳定；锁文件 PID/时间戳仅用于诊断。
- 不支持 OS 文件锁的平台 fail closed，不再退化为普通文件存在性判断。

## 回归测试

- 管理线程停止时通过事件循环线程安全调度 `stop_running`。
- 旧线程 join 超时后不释放锁、不启动新线程。
- 锁文件释放后保留并可重新获取。
- 活跃 PID 的旧时间戳不会导致锁过期。
- 不支持 OS 锁时拒绝启动。

## 部署边界

该文件锁适用于同一主机/共享 OS 锁语义可靠的部署，不等价于跨主机分布式锁。若同一 Bot Token 要在多台主机上运行，必须改用 Redis 等具备租约、owner token、TTL 与 fencing 的分布式锁，并保持单一 polling consumer。
