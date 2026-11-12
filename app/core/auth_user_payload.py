"""
登录/刷新令牌响应中的 user 载荷构建。

位于认证层（app/core），将 User/Client 模型字段序列化为前端 LoginResponse.user。
客户角色附带 client 元数据（不含明文 API 密钥），供前端判断对接能力。
"""
from __future__ import annotations

from typing import Any

from app.models.models import Client, User, UserRole


def build_auth_user_payload(
        user: User,
        *,
        api_enabled: bool = False,
        has_publisher: bool = False,
        password_change_enabled: bool = False,
        client: Client | None = None,
) -> dict[str, Any]:
    """
    构建写入 LoginResponse.user 的字典。

    客户角色且存在 Client 记录时附带 client 元数据（has_api_key 为布尔标志，非明文密钥）。
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
        "password_change_enabled": password_change_enabled,
    }
    if client is not None:
        payload["client"] = {
            "id": client.id,
            "company_name": client.company_name,
            "api_enabled": api_enabled,
            "password_change_enabled": password_change_enabled,
            "has_publisher": has_publisher,
            "has_api_key": bool(client.key),
        }
    return payload
