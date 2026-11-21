"""Postback 待确认记录的并发锁定查询。"""
from sqlalchemy import select


def build_pending_for_update_statement(model, pending_id: int, status: str | None = "pending"):
    """按主键锁定待确认记录；status=None 时也读取已处理记录用于审计分类。

    MySQL InnoDB 会在当前事务结束前持有 FOR UPDATE 行锁，避免并发审批/
    拒绝对同一条记录执行互相覆盖的状态变更。不存在的记录仍返回空结果。
    """
    statement = select(model).where(model.id == pending_id)
    if status is not None:
        statement = statement.where(model.status == status)
    return statement.with_for_update()
