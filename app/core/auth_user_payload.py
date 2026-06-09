"""
登录/刷新令牌响应中的 user 载荷构建。

位于认证层（app/core），将 User/Client 模型字段序列化为前端 LoginResponse.user，
客户角色附带 API 密钥等信息，供对接文档页直接展示。
"""
from __future__ import annotations

from typing import Any

from app.models.models import Client, User, UserRole


def build_auth_user_payload(
        user: User,
        *,
        api_enabled: bool = False,
        has_publisher: bool = False,
        client: Client | None = None,
) -> dict[str, Any]:
    """
    构建写入 LoginResponse.user 的字典。

    客户角色且存在 Client 记录时附带 client（含 API 密钥），
    供前端 API 对接文档页展示，无需额外请求 /users/me。
    """
    role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    payload: dict[str, Any] = {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "role": role,
        "api_enabled": api_enabled,
        "has_publisher": has_publisher,
    }
    if client is not None:
        payload["client"] = {
            "id": client.id,
            "key": client.key,
            "company_name": client.company_name,
            "api_enabled": bool(client.api_enabled) if client.api_enabled is not None else False,
            "password_change_enabled": (
                bool(client.password_change_enabled)
                if client.password_change_enabled is not None
                else False
            ),
            "has_publisher": has_publisher,
        }
    return payload
