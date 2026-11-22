"""Postback 管理端 PII 读取审计共用入口。"""
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_user_action, commit_audit_log
from app.models.models import User


async def audit_postback_pii_read(
    *,
    db: AsyncSession,
    current_user: User,
    request: Request,
    resource_name: str,
    details: dict[str, Any],
) -> None:
    """记录管理员读取 Postback 敏感数据；审计提交失败时拒绝返回查询结果。"""
    await log_user_action(
        db=db,
        action_type="API_ACCESS",
        user=current_user,
        resource_type="POSTBACK_PII_ACCESS",
        resource_name=resource_name,
        request_method=request.method,
        request_path=request.url.path,
        status_code=200,
        success=True,
        details=details,
        strict=True,
    )
    await commit_audit_log(db)
