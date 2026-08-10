"""
广告数据查询共用 JOIN 辅助函数。

功能说明：
- 统一 Product / Client / ProductAssignment / CountryInfo 关联路径
- 供 list、detail、filter、batch_delete 等 query 模块复用
- 分配历史模式：按日期最多匹配一条分配（min id），空窗回退 Product.client_id
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import aliased, load_only

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


def best_product_assignment_id_subquery(
    date_column,
    product_id_column=None,
) -> ColumnElement:
    """
    标量子查询：为 (product, date) 选取一条匹配的分配记录（id 最小）。

    避免分配区间重叠时 JOIN 放大导致 SUM/COUNT 重复累加。
    """
    pa = aliased(ProductAssignment)
    product_col = product_id_column if product_id_column is not None else Product.id
    return (
        select(pa.id)
        .where(
            pa.product_id == product_col,
            product_assignment_join_condition(date_column, pa.start_date, pa.end_date),
        )
        .order_by(pa.id.asc())
        .limit(1)
        .correlate_except(pa)
        .scalar_subquery()
    )


def resolved_client_id_expr():
    """分配命中用分配客户，空窗回退产品当前归属。"""
    return func.coalesce(ProductAssignment.client_id, Product.client_id)


def outerjoin_best_product_assignment(
    query,
    date_column,
    product_id_column=None,
):
    """
    外连接最多一条匹配的 ProductAssignment（空窗时 assignment 为 NULL）。

    ON 条件必须显式包含 product_id + 日期区间，否则 SQLAlchemy 会告警
    product_assignments 与 ad_data 之间存在笛卡尔积。
    """
    product_col = product_id_column if product_id_column is not None else Product.id
    best_id = best_product_assignment_id_subquery(date_column, product_col)
    return query.outerjoin(
        ProductAssignment,
        and_(
            ProductAssignment.product_id == product_col,
            product_assignment_join_condition(
                date_column,
                ProductAssignment.start_date,
                ProductAssignment.end_date,
            ),
            ProductAssignment.id == best_id,
        ),
    )


def join_resolved_client(query):
    """按解析后的 client_id 内连接 Client（空窗回退 Product.client_id）。"""
    return query.join(Client, Client.id == resolved_client_id_expr())


def join_product_and_client(query, use_assignment_table: bool):
    """
    从已含 AdData 的查询出发，关联 Product 与 Client。

    Args:
        query: SQLAlchemy 查询（FROM 含 AdData）
        use_assignment_table: 是否走 ProductAssignment 历史表路径
    """
    query = query.join(Product, AdData.product_id == Product.id)
    if use_assignment_table:
        query = outerjoin_best_product_assignment(query, AdData.date)
        query = join_resolved_client(query)
    else:
        query = query.join(Client, Product.client_id == Client.id)
    return query


def join_ad_data_and_client_from_product(query, use_assignment_table: bool):
    """
    从已含 Product 的查询出发，关联 AdData 与 Client。

    分配历史表模式：Product → AdData → ProductAssignment(可选) → Client(COALESCE)
    旧模式：Product → Client → AdData
    """
    if use_assignment_table:
        query = query.join(AdData, AdData.product_id == Product.id)
        query = outerjoin_best_product_assignment(query, AdData.date)
        query = join_resolved_client(query)
    else:
        query = query.join(Client, Product.client_id == Client.id)
        query = query.join(AdData, AdData.product_id == Product.id)
    return query


def join_tb_search_and_client_from_product(query, use_assignment_table: bool):
    """
    从已含 Product 的查询出发，关联 TB 搜索数据与 Client。

    分配历史模式：Product → TBSearchData → ProductAssignment(可选) → Client(COALESCE)
    旧模式：Product → Client → TBSearchData
    """
    from app.models.models import TBSearchData

    if use_assignment_table:
        query = query.join(TBSearchData, TBSearchData.product_id == Product.id)
        query = outerjoin_best_product_assignment(query, TBSearchData.date)
        query = join_resolved_client(query)
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
