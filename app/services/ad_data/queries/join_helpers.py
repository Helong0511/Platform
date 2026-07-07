"""
广告数据查询共用 JOIN 辅助函数。

功能说明：
- 统一 Product / Client / ProductAssignment / CountryInfo 关联路径
- 供 list、detail、filter、batch_delete 等 query 模块复用
"""
from typing import Any, Dict, List

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
