"""Postback 待确认记录的并发锁定查询。"""
from sqlalchemy import select


def build_pending_for_update_statement(model, pending_id: int, status: str = "pending"):
    """按主键和状态读取待确认记录，并在支持的数据库上加行锁。

    MySQL InnoDB 会在当前事务结束前持有 FOR UPDATE 行锁，避免并发批准/
    拒绝对同一条 pending 记录执行互相覆盖的状态变更。
    """
    return (
        select(model)
        .where(model.id == pending_id, model.status == status)
        .with_for_update()
    )
