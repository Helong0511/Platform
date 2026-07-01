"""
异步 SQLAlchemy ORM 安全访问工具。

在 AsyncSession 下，未预加载的关系属性会触发同步懒加载并导致 MissingGreenlet。
本模块提供「仅访问已加载关系」的辅助函数，供 API 序列化与服务层复用。
"""
from __future__ import annotations

from typing import Any, Optional, TypeVar

from sqlalchemy import inspect as sa_inspect

T = TypeVar("T")


def is_relationship_loaded(instance: object, relation_name: str) -> bool:
    """判断 ORM 关系是否已加载（未在 unloaded 集合中）。"""
    state = sa_inspect(instance, raiseerr=False)
    if state is None:
        # 非 ORM 实例（如单测 mock）：有该属性则允许读取
        return hasattr(instance, relation_name)
    return relation_name not in state.unloaded


def get_loaded_relationship(
    instance: object,
    relation_name: str,
    default: Optional[T] = None,
) -> Optional[T]:
    """仅当关系已预加载时返回属性值，否则返回 default，避免异步懒加载。"""
    if not is_relationship_loaded(instance, relation_name):
        return default
    return getattr(instance, relation_name, default)


def get_first_loaded_collection_item(
    instance: object,
    relation_name: str,
    default: Optional[T] = None,
) -> Optional[T]:
    """读取已加载的一对多集合的首项（如 User.clients[0]）。"""
    collection = get_loaded_relationship(instance, relation_name, default=None)
    if not collection:
        return default
    try:
        return collection[0]
    except (IndexError, KeyError, TypeError):
        return default


def resolve_client_user_full_name(client: object) -> Optional[str]:
    """从已加载的 Client.user 取全名，未加载时返回 None。"""
    user = get_loaded_relationship(client, "user")
    if user is None:
        return None
    full_name = getattr(user, "full_name", None)
    return str(full_name).strip() if full_name else None


def resolve_publisher_client_name(publisher: object) -> Optional[str]:
    """从已加载的 Publisher.client（及 client.user）解析展示用客户名。"""
    client = get_loaded_relationship(publisher, "client")
    if client is None:
        return None
    user_name = resolve_client_user_full_name(client)
    if user_name:
        return user_name
    company_name = getattr(client, "company_name", None)
    return str(company_name).strip() if company_name else None
