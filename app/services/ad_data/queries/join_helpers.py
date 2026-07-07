"""
广告数据查询共用 JOIN 辅助函数。

功能说明：
- 统一 Product / Client / ProductAssignment / CountryInfo 关联路径
- 供 list、detail、filter、batch_delete 等 query 模块复用
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import load_only

from app.core.query_utils import (
    join_country_info as join_country_info_util,
    product_assignment_join_condition,
)
from app.models.models import AdData, Client, Product, ProductAssignment

CLIENT_LOAD_ONLY = load_only(
    Client.id,
    Client.user_id,
    Client.company_name,
    Client.contact_person,
    Client.phone,
    Client.address,
    Client.is_active,
    Client.created_at,
    Client.updated_at,
)


def join_country_info_for_ad_data(query):
    """为广告数据查询左关联 CountryInfo。"""
    return join_country_info_util(query, AdData.country_code)


def join_product_and_client(query, use_assignment_table: bool):
    """
    从已含 AdData 的查询出发，关联 Product 与 Client。

    Args:
        query: SQLAlchemy 查询（FROM 含 AdData）
        use_assignment_table: 是否走 ProductAssignment 历史表路径
    """
    query = query.join(Product, AdData.product_id == Product.id)
    if use_assignment_table:
        query = query.join(
            ProductAssignment,
            and_(
                ProductAssignment.product_id == Product.id,
                product_assignment_join_condition(
                    AdData.date,
                    ProductAssignment.start_date,
                    ProductAssignment.end_date,
                ),
            ),
        )
        query = query.join(Client, ProductAssignment.client_id == Client.id)
    else:
        query = query.join(Client, Product.client_id == Client.id)
    return query


def join_ad_data_and_client_from_product(query, use_assignment_table: bool):
    """
    从已含 Product 的查询出发，关联 AdData 与 Client。

    分配历史表模式：Product → AdData → ProductAssignment → Client
    旧模式：Product → Client → AdData
    """
    if use_assignment_table:
        query = query.join(AdData, AdData.product_id == Product.id)
        query = query.join(
            ProductAssignment,
            and_(
                ProductAssignment.product_id == Product.id,
                product_assignment_join_condition(
                    AdData.date,
                    ProductAssignment.start_date,
                    ProductAssignment.end_date,
                ),
            ),
        )
        query = query.join(Client, ProductAssignment.client_id == Client.id)
    else:
        query = query.join(Client, Product.client_id == Client.id)
        query = query.join(AdData, AdData.product_id == Product.id)
    return query


def join_tb_search_and_client_from_product(query, use_assignment_table: bool):
    """
    从已含 Product 的查询出发，关联 TB 搜索数据与 Client。

    分配历史模式：Product → TBSearchData → ProductAssignment → Client
    旧模式：Product → Client → TBSearchData
    """
    from app.models.models import TBSearchData

    if use_assignment_table:
        query = query.join(TBSearchData, TBSearchData.product_id == Product.id)
        query = query.join(
            ProductAssignment,
            and_(
                ProductAssignment.product_id == Product.id,
                product_assignment_join_condition(
                    TBSearchData.date,
                    ProductAssignment.start_date,
                    ProductAssignment.end_date,
                ),
            ),
        )
        query = query.join(Client, ProductAssignment.client_id == Client.id)
    else:
        query = query.join(Client, Product.client_id == Client.id)
        query = query.join(TBSearchData, TBSearchData.product_id == Product.id)
    return query


def build_products_with_data_base_query():
    """有数据产品筛选项：SELECT DISTINCT id, name, client_id。"""
    return select(func.distinct(Product.id), Product.name, Product.client_id).where(
        Product.is_active == True
    )


def merge_product_option_rows(*row_sets) -> List[Dict[str, Any]]:
    """合并多路产品查询结果（分配历史 + 当前归属），按 id 去重。"""
    merged: Dict[int, Dict[str, Any]] = {}
    for rows in row_sets:
        for product_id, product_name, product_client_id in rows:
            if product_id is None:
                continue
            merged[int(product_id)] = {
                "id": int(product_id),
                "name": product_name or "未知产品",
                "client_id": product_client_id,
            }
    return list(merged.values())


def merge_product_options_with_ownership(
    assignment_rows,
    current_rows=None,
    *,
    scope_client_ids: Optional[List[int]] = None,
    has_dual_path: bool = False,
) -> List[Dict[str, Any]]:
    """
    合并产品筛选项并标注归属类型。

    ownership_type:
    - current: 当前名下产品（Product.client_id）
    - historical: 所选日期范围内按分配历史归属、但当前已不在名下
    - both: 同时满足当前名下与分配历史匹配
    """
    assignment_rows = assignment_rows or []
    current_rows = current_rows or []

    assignment_ids: set[int] = set()
    current_ids: set[int] = set()
    row_meta: Dict[int, tuple] = {}

    for product_id, product_name, product_client_id in assignment_rows:
        if product_id is None:
            continue
        pid = int(product_id)
        assignment_ids.add(pid)
        row_meta[pid] = (product_name, product_client_id)

    for product_id, product_name, product_client_id in current_rows:
        if product_id is None:
            continue
        pid = int(product_id)
        current_ids.add(pid)
        if pid not in row_meta:
            row_meta[pid] = (product_name, product_client_id)

    scope_set = set(scope_client_ids) if scope_client_ids else None
    result: List[Dict[str, Any]] = []

    for pid in assignment_ids | current_ids:
        product_name, product_client_id = row_meta[pid]
        ownership = _resolve_product_ownership_type(
            in_assignment=pid in assignment_ids,
            in_current=pid in current_ids,
            product_client_id=product_client_id,
            scope_client_ids=scope_set,
            has_dual_path=has_dual_path,
        )
        item: Dict[str, Any] = {
            "id": pid,
            "name": product_name or "未知产品",
            "client_id": product_client_id,
        }
        if ownership:
            item["ownership_type"] = ownership
        result.append(item)

    return result


def _resolve_product_ownership_type(
    *,
    in_assignment: bool,
    in_current: bool,
    product_client_id: Any,
    scope_client_ids: Optional[set[int]],
    has_dual_path: bool,
) -> Optional[str]:
    if has_dual_path:
        if in_assignment and in_current:
            return "both"
        if in_current:
            return "current"
        if in_assignment:
            return "historical"
        return None

    if not scope_client_ids:
        return None

    owner_id = int(product_client_id) if product_client_id is not None else None
    if owner_id is not None and owner_id in scope_client_ids:
        return "current"
    if in_assignment:
        return "historical"
    return None
