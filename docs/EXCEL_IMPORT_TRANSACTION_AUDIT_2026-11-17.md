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
