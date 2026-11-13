# Migration Runner 操作说明（2026-11-13）

## 1. 当前功能

仓库提供以下命令：

```bash
python -m app.db.migrations validate
python -m app.db.migrations status
python -m app.db.migrations apply
```

- `validate`：离线校验 manifest、文件 SHA-256 和 SQL 分句，不连接数据库。
- `status`：只读查询 `platform_schema_migrations`，不创建表、不执行 DDL。
- `apply`：通过专用 MySQL 迁移账号执行待应用的增量 migration。

## 2. 运行前提

1. MySQL 版本至少 8.0.16。
2. 连接字符集为 utf8mb4。
3. `MIGRATION_DATABASE_URL` 必须显式设置为 `mysql+aiomysql` DSN。
4. 迁移账号用户名必须不同于应用运行账号；CLI 会从应用设置读取 `SQLALCHEMY_DATABASE_URI` 并拒绝相同用户名。
5. 目标数据库的基础表结构必须已经由受控 provisioning 流程准备好。Runner 只执行 `app/db/migrations/manifest.py` 登记的增量 migration，不会导入 `sql/platform.sql`。

示例仅展示变量形式，不要把真实密码提交到仓库或写入命令历史：

```bash
export MIGRATION_DATABASE_URL='mysql+aiomysql://<migration_user>:<password>@<db-host>:3306/platform?charset=utf8mb4'
python -m app.db.migrations validate
python -m app.db.migrations status
python -m app.db.migrations apply
```

## 3. 执行语义

- Runner 使用单个物理 MySQL connection，从 `GET_LOCK` 到 `RELEASE_LOCK` 不切换连接。
- 每个 revision 在执行 SQL 前先写入 `running`。
- 所有语句按顺序执行；每条语句结果集会被消费并关闭。
- 全部成功后写入 `applied`。
- 明确失败写入 `failed`；连接中断时可能保留 `running`。
- MySQL DDL 会隐式提交，不能假设整份 migration 可以事务回滚。
- 出现 `running` 或 `failed` 时，Runner 会停止，不会自动重跑；先检查 schema 实际状态、DDL 已完成边界和 checksum，再制定单独 forward-fix。
- `status` 返回非零阻断码时，不得忽略后启动部署。

## 4. 基线文件安全边界

`sql/platform.sql` 是完整 schema 快照，含 `DROP TABLE IF EXISTS`、硬编码数据库选择及客户端 DELIMITER / routine 定义。它不是增量 migration，也不是 Runner 的输入。

- 只允许在全新或可丢弃数据库上使用经过审核的初始化流程。
- 绝不能把它用于已有数据库升级。
- 不要把“ORM 表名覆盖测试通过”误认为所有列、索引、外键、CHECK 和字符集都已完成物理结构核验。

## 5. 当前尚未达到生产使用条件

- API/Scheduler lifespan 仍调用 `create_database()` 与 `Base.metadata.create_all()`。
- 应用尚未接入只读 schema revision gate。
- Runner 尚未成为 systemd 部署的唯一 schema 变更入口。
- 新库基线导入、旧库升级、备份恢复、worker pause/resume 和失败人工恢复演练仍未完成。

因此：当前命令和 CI 仅证明隔离测试环境中的 Runner 行为；不能据此在生产执行，也不能据此宣称上线就绪。
