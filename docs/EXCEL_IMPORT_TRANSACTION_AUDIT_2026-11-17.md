# Excel 导入事务一致性专项审计（2026-11-17）

## 范围与证据

本次只检查广告数据 Excel 导入路径，不代表全系统事务审计完成。

- `app/api_v1/excel/router.py`：`POST /import/ad-data` 使用 `Depends(require_admin)`，该入口仅管理员可调用。
- `app/api_v1/excel/ad_data_import/handler.py`：逐行调用 `process_row_data`；处理完后 `flush`，函数正常返回后由 `get_db` 自动 `commit`。
- `app/core/database.py`：`get_db` 在 yield 正常结束时提交事务。
- `app/api_v1/excel/ad_data_import/row_processor.py`：先调用 `find_or_create_product`，后解析和验证请求数、匹配数、展示数、点击数、收益等数值字段；任何异常在函数内部捕获，仅增加 `failed_rows` 并继续处理。
- `app/api_v1/excel/ad_data_import/product_resolver.py`：新建 Product 后调用 `initialize_product_assignment`；该调用异常被捕获并仅记录 warning，随后仍将 Product 放入映射并返回成功。
- `app/core/product_assignment.py`：初始化分配记录时，若 `validate_product_assignments` 返回 errors，只记录 error，不抛异常。
- `tests/test_product_name_unique.py`：产品名称全局唯一，并明确测试目标 Client 无匹配时回退到全局同名产品；不能未经业务确认改为 Client 局部唯一或禁止回退。

## 发现

### EXCEL-TXN-001：无效行可能留下新建产品（数据完整性，待修复）

当前处理顺序是：

1. 先按名称查找/创建 Product。
2. 再解析 Excel 数值字段并验证非负约束。
3. 如果数值格式错误或校验失败，`process_row_data` 内部捕获异常并返回。
4. 导入 handler 仍正常结束；`get_db` 因请求正常返回而提交整个 Session。

因此，若该行触发新建 Product，随后数值解析失败，Product 仍可能被提交，而该行被统计为失败。该行没有对应 AdData，可能留下无数据产品。此结论由当前调用顺序和事务提交路径直接支持。

**建议修复：**
- 先解析并验证所有不依赖 Product 的输入字段，再执行 Product 查找/创建。
- 对“本行新建 Product + ProductAssignment + AdData 写入”使用行级 savepoint；行失败回滚该行的数据库副作用。
- 不要对整个导入 Session 做每行 commit；保留批次级原子提交策略，除非产品明确要求部分成功持久化。
- 回滚后同步修正内存中的 `product_map`、`product_name_map`、`existing_records` 和统计计数，避免映射缓存引用已回滚对象。

### EXCEL-TXN-002：ProductAssignment 初始化失败被吞掉（数据完整性，待修复）

`find_or_create_product` 在新 Product 创建后调用 `initialize_product_assignment`，但捕获所有异常后继续返回 Product。初始化函数本身也会在分配校验结果包含 errors 时只记录日志，不抛异常。

这会使调用方无法区分“产品及其归属历史完整创建”和“产品创建成功但分配历史缺失/不合法”。由于系统存在 ProductAssignment 归属历史和当前 `Product.client_id` 同步逻辑，这种状态可能造成后续归属解析、历史归属审计或数据范围判断不一致。当前证据支持完整性风险，但尚未证明该状态必然造成跨租户数据泄漏。

**建议修复：**
- 明确 Product 与初始 ProductAssignment 是否为同一业务原子操作；若是，assignment 初始化或验证失败必须向上传播。
- 在同一个 savepoint 内创建 Product 和初始 ProductAssignment；失败时一并回滚。
- 对历史上已有无分配记录的产品提供只读检测/报告，不在本次导入路径中静默自动修复历史数据。
- 在确认所有调用方的事务约定后，再决定是否调整 `initialize_product_assignment` 的通用异常行为，避免影响其它产品创建/修复流程。

## 暂不修改的业务规则

- 保留产品名称全局唯一约束 `uq_products_name`。
- 保留现有同名产品匹配策略，包括目标 Client 无匹配时的全局回退；如需变更必须先由业务确认产品共享语义和历史数据迁移策略。
- 保留 Excel 导入仅管理员可用的路由权限。
- 不对整批导入改成逐行 commit；这会改变当前事务语义并可能留下部分批次数据。

## 必须补充的回归测试

1. 新产品行的数值字段无效：导入返回该行失败，数据库中不存在该行新建的 Product。
2. 新产品的 ProductAssignment 创建抛出异常：Product 与 Assignment 均不落库。
3. ProductAssignment 校验返回 errors：导入必须失败关闭，不得把不完整产品放入映射。
4. 同一 Excel 后续行引用前一行刚创建的产品：正常成功，避免缓存回滚/映射回滚造成错误。
5. 行级失败后下一行成功：失败行不污染 Session，后续行可继续处理。
6. 并发导入同名产品：仍遵守全局唯一约束和既有唯一键竞争处理。
7. 更新既有 AdData 的行失败：确认 ORM 对象修改和相关告警记录不会在失败行后被意外提交。

## 当前状态

- 本文记录的是已定位问题和修复设计，不代表代码已修复。
- 尚未新增上述回归测试，也尚未修改导入事务实现。
- 必须先完成测试和实现，再运行最新 HEAD 的完整 Backend / Frontend CI。
- PR #1 继续保持 Draft/Open；不合并、不部署。

## 2026-11-18 复核：逐行 SAVEPOINT 已落地，专项 MySQL 验收仍需补齐

> 本节优先于上文“待修复”状态。上文保留为发现问题时的历史证据，不代表当前 HEAD 仍保持原实现。

### 当前代码状态（PR #1 HEAD `7672f708ad6be6c50605b3d82eeba33b15d16a9c`）

- `app/api_v1/excel/ad_data_import/row_processor.py` 在每行开始时调用 `db.begin_nested()`，以 SAVEPOINT 包围该行产品解析、Product / ProductAssignment 创建、AdData 新增或更新。
- 行成功时提交 SAVEPOINT；行失败时回滚当前 SAVEPOINT，并恢复 `product_map`、`product_name_map`、`existing_records` 与统计结果快照，避免失败行缓存污染后续行。
- `app/api_v1/excel/ad_data_import/product_resolver.py` 在新 Product 初始化 ProductAssignment 后重新调用 `validate_product_assignments()`；校验返回 errors 时抛出异常，交由行级 SAVEPOINT 回滚。
- `initialize_product_assignment()` 内部仍保留“校验错误只记录日志”的历史行为；Excel 路径通过 resolver 的第二次校验 fail-closed。不能据此推断所有其它调用该 helper 的业务路径也已经 fail-closed。
- `create_product_assignment()` 对验证产生的 ValueError 会重新抛出；非 ValueError 的验证异常会被记录后继续，因此必须保留调用方独立校验和数据库约束，不能只依赖 helper 内部验证。

### 当前测试证据与限制

- 新增 `tests/test_excel_import_row_transaction.py` 覆盖数值字段失败时回滚当前行及缓存，以及 Product 已插入后归属初始化失败时回滚并计为失败行。
- 该专项测试使用 fake DB / fake SAVEPOINT，并通过 mock 替代 `find_or_create_product()`；它没有实际运行 SQLAlchemy AsyncSession、MySQL SAVEPOINT、Product / ProductAssignment 外键与唯一约束，也没有验证同一批次“成功行 → 失败行 → 后续成功行”的真实提交隔离。
- Run #1982（HEAD `7672f708ad6be6c50605b3d82eeba33b15d16a9c`）Backend 732 passed、1 skipped、1 warning；这是全套 CI 证据，不等于上述缺失的 Excel 专项 MySQL 故障矩阵已覆盖。

### 剩余验收要求

1. 增加仅运行于 GitHub Actions loopback 临时 MySQL 的集成测试，使用真实 AsyncSession 和 SAVEPOINT。
2. 覆盖 Product 插入后 ProductAssignment 创建失败、Assignment 校验失败、AdData 新增失败、既有 AdData 更新失败等中途故障；逐项查询数据库确认失败行没有残留副作用。
3. 覆盖同批次前一行成功、当前行失败、后一行成功，验证前后成功行均可保留，失败行不污染缓存与 ORM Session。
4. 对共享的 `initialize_product_assignment()` 调用点做全仓扫描，逐个确认“校验失败 / 查询异常”是否必须向上传播；不要仅为 Excel 修复而改变其它业务路径语义。
5. 集成测试通过后，再将本报告中的 EXCEL-TXN-001 / EXCEL-TXN-002 状态更新为“代码修复 + 真实数据库验收完成”；在此之前不得标记专项验收关闭。

## 2026-11-18 补充：真实 MySQL SAVEPOINT 回归测试

- 新增 `tests/test_excel_import_mysql_integration.py`，通过 GitHub Actions 的 loopback 临时 MySQL 服务创建随机隔离数据库。
- 测试使用真实 SQLAlchemy `AsyncSession` 与 MySQL SAVEPOINT；模拟产品解析阶段先 INSERT 一条副作用记录，再让数值字段校验失败。
- 断言失败行的 SAVEPOINT 回滚后，外层事务仍可提交，数据库中不存在该行 INSERT，产品映射缓存恢复，失败统计正确。
- 测试只允许 `GITHUB_ACTIONS=true`、`UNIT_TEST=1`、loopback 主机、数据库名 `platform_ci` 和显式破坏性测试开关同时满足；不读取生产数据库配置。
- 本测试目前已提交到专项 PR 分支；**必须等待该分支最新 HEAD 的 Full Audit CI 真正执行此测试并通过后，才可将真实 MySQL SAVEPOINT 验收标记为通过**。
- 此用例只覆盖“产品创建后数值校验失败”这一条真实 MySQL 回滚路径；ProductAssignment 外键/唯一约束失败、AdData 新增失败、既有 AdData 更新失败，以及同批次成功-失败-成功交错仍需补充专项覆盖。
