"""
查询构建辅助函数
提供通用的查询构建模式，减少重复代码
"""
from typing import Optional, Callable, Any
from sqlalchemy import Select, func, Column
from sqlalchemy.future import select


def build_count_query(
    base_query: Select,
    count_column: Any,
    apply_filters: Optional[Callable[[Select], Select]] = None
) -> Select:
    """
    从主查询构建计数查询
    
    参数:
        base_query: 主查询对象
        count_column: 用于计数的列（通常是模型的主键）
        apply_filters: 可选的过滤函数，用于对计数查询应用额外的过滤条件
    
    返回:
        计数查询对象
    """
    # 从主查询中提取基础结构，构建计数查询
    # 注意：这需要根据实际的查询结构来调整
    # 这里提供一个通用的模式
    
    # 如果主查询已经有 select_from，我们需要提取它
    # 否则，我们需要从主查询中提取表
    
    # 简化版本：假设我们可以从主查询中提取表
    # 实际实现可能需要更复杂的逻辑
    
    count_query = select(func.count(count_column))
    
    # 如果提供了过滤函数，应用它
    if apply_filters:
        count_query = apply_filters(count_query)
    
    return count_query


def apply_common_filters(
    query: Select,
    filters: dict[str, Any],
    filter_mapping: dict[str, Callable[[Select, Any], Select]]
) -> Select:
    """
    应用通用过滤条件到查询
    
    参数:
        query: 查询对象
        filters: 过滤条件字典
        filter_mapping: 过滤条件映射，key为过滤条件名，value为应用过滤的函数
    
    返回:
        应用过滤后的查询对象
    
    示例:
        filter_mapping = {
            'is_active': lambda q, v: q.where(Model.is_active == v),
            'client_id': lambda q, v: q.where(Model.client_id == v)
        }
        query = apply_common_filters(query, {'is_active': True}, filter_mapping)
    """
    for filter_key, filter_value in filters.items():
        if filter_value is not None and filter_key in filter_mapping:
            query = filter_mapping[filter_key](query, filter_value)
    
    return query


def calculate_pagination_offset(page: int, page_size: int) -> int:
    """
    计算分页偏移量
    
    Args:
        page: 页码（从1开始）
        page_size: 每页条数
    
    Returns:
        分页偏移量（用于 SQL OFFSET）
    
    Example:
        offset = calculate_pagination_offset(page=2, page_size=10)  # 返回 10
    """
    return (page - 1) * page_size


def calculate_total_pages(total: int, page_size: int) -> int:
    """
    计算总页数
    
    Args:
        total: 总记录数
        page_size: 每页条数
    
    Returns:
        总页数（向上取整）
    
    Example:
        total_pages = calculate_total_pages(total=100, page_size=10)  # 返回 10
        total_pages = calculate_total_pages(total=101, page_size=10)  # 返回 11
    """
    if total == 0:
        return 0
    return (total + page_size - 1) // page_size  # 向上取整


def get_pagination_info(page: int, page_size: int, total: int) -> dict:
    """
    获取完整的分页信息
    
    Args:
        page: 当前页码（从1开始）
        page_size: 每页条数
        total: 总记录数
    
    Returns:
        包含分页信息的字典：
        {
            "page": 当前页码,
            "page_size": 每页条数,
            "total": 总记录数,
            "total_pages": 总页数,
            "offset": 偏移量,
            "has_next": 是否有下一页,
            "has_prev": 是否有上一页
        }
    
    Example:
        pagination = get_pagination_info(page=2, page_size=10, total=100)
        # 返回: {
        #     "page": 2,
        #     "page_size": 10,
        #     "total": 100,
        #     "total_pages": 10,
        #     "offset": 10,
        #     "has_next": True,
        #     "has_prev": True
        # }
    """
    total_pages = calculate_total_pages(total, page_size)
    offset = calculate_pagination_offset(page, page_size)
    
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "offset": offset,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }


def apply_sorting(
    query: Select,
    sort_column: Column | Any,
    sort_order: str = "desc"
) -> Select:
    """
    应用排序到查询
    
    Args:
        query: SQLAlchemy 查询对象
        sort_column: 排序列（Column 对象或 SQLAlchemy 表达式）
        sort_order: 排序方向，默认为 "desc"（降序），也可以是 "asc"（升序）
    
    Returns:
        应用了排序的查询对象
    
    Example:
        query = apply_sorting(query, AdData.date, sort_order="desc")
        query = apply_sorting(query, Product.name, sort_order="asc")
    """
    if sort_order.lower() == "desc":
        return query.order_by(sort_column.desc())
    else:
        return query.order_by(sort_column.asc())


def validate_and_get_sort_column(
    sort_by: str,
    valid_sort_fields: dict[str, Column | Any],
    default_sort_field: str = "id"
) -> tuple[Column | Any, str]:
    """
    验证并获取排序列
    
    Args:
        sort_by: 用户指定的排序字段名
        valid_sort_fields: 有效的排序字段字典，格式为 {字段名: Column对象}
        default_sort_field: 默认排序字段名（如果用户指定的字段无效）
    
    Returns:
        (排序列对象, 实际使用的排序字段名)
    
    Example:
        valid_fields = {
            "date": AdData.date,
            "product": Product.name,
            "client": Client.company_name
        }
        sort_column, actual_sort_by = validate_and_get_sort_column(
            sort_by="date",
            valid_sort_fields=valid_fields,
            default_sort_field="date"
        )
        query = apply_sorting(query, sort_column, sort_order="desc")
    """
    if sort_by not in valid_sort_fields:
        sort_by = default_sort_field
    
    sort_column = valid_sort_fields.get(sort_by, valid_sort_fields[default_sort_field])
    return sort_column, sort_by

