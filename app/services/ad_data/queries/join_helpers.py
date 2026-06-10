"""
广告数据查询共用 JOIN 辅助函数。

功能说明：
- 统一 Product / Client / ProductAssignment / CountryInfo 关联路径
- 供 list、detail、filter、batch_delete 等 query 模块复用
"""
from sqlalchemy import and_
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
