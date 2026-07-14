"""
SQL 查询条件优化工具。

职责：生成可走索引的日期范围、产品分配 JOIN 等条件，避免在列上套函数导致全表扫描。

在系统中的位置：``app.core.query_utils``，由报表与广告数据查询 Service 引用。
"""
import time
from calendar import monthrange
from datetime import date, datetime
from sqlalchemy import Column, and_, or_, text, func, literal_column, case, select
from sqlalchemy.future import select as future_select
from typing import Optional
from sqlalchemy.sql import Select

from app.models.models import ProductAssignment, CountryInfo


def date_range_condition(
    column: Column,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> Optional[any]:
    """
    生成日期范围查询条件（优化版本）
    避免在列上使用函数，提升索引使用率
    
    Args:
        column: 日期列（DATE 或 DATETIME 类型；AdData.date / TBSearchData.date 为 DATE）
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）
    
    Returns:
        SQLAlchemy 条件表达式，如果没有日期范围则返回 None
    
    Example:
        query = query.where(
            date_range_condition(AdData.date, start_date, end_date)
        )
    """
    conditions = []
    
    if start_date:
        conditions.append(column >= start_date)
    
    if end_date:
        conditions.append(column <= end_date)
    
    # 如果没有条件，返回 None
    if not conditions:
        return None
    # 如果只有一个条件，直接返回该条件，避免使用 and_() 可能的问题
    elif len(conditions) == 1:
        return conditions[0]
    # 如果有多个条件，使用 and_() 组合
    else:
        return and_(*conditions)


def product_assignment_join_condition(
    ad_data_date: Column,
    assignment_start: Column,
    assignment_end: Column
) -> any:
    """
    生成产品分配历史 JOIN 条件（优化版本）
    避免在 ad_data.date 上使用 func.date()，提升索引使用率
    
    Args:
        ad_data_date: AdData.date 列（DATE 类型）
        assignment_start: ProductAssignment.start_date 列（DATE 类型）
        assignment_end: ProductAssignment.end_date 列（DATE 类型，可为 NULL）
    
    Returns:
        SQLAlchemy JOIN 条件表达式
    
    Note:
        AdData.date / TBSearchData.date 为 DATE 列，直接与 start_date/end_date 比较即可。
        end_date 为 NULL 时表示分配仍有效。
    
    Example:
        query = query.join(
            ProductAssignment,
            and_(
                ProductAssignment.product_id == Product.id,
                product_assignment_join_condition(
                    AdData.date,
                    ProductAssignment.start_date,
                    ProductAssignment.end_date
                )
            )
        )
    """
    # MySQL 会自动将 DATE 转换为 DATETIME，所以可以直接比较
    # 为了包含整天的数据，结束日期需要加 1 天
    # 完全复制 ad_data.py 中的写法，直接内联所有表达式
    # 注意：在 SQLAlchemy 2.0 中，or_() 中的表达式必须都是有效的布尔表达式
    # 直接使用比较操作符，确保返回布尔表达式
    return and_(
        ad_data_date >= assignment_start,
        or_(
            assignment_end.is_(None),
            ad_data_date <= assignment_end,
        )
    )


def apply_date_range_filter(
    query: Select,
    date_column: Column,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    default_to_current_month: bool = True
) -> Select:
    """
    应用日期范围过滤（带默认值）
    
    Args:
        query: SQLAlchemy 查询对象
        date_column: 日期列
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）
        default_to_current_month: 如果未指定日期，是否默认使用当前月
    
    Returns:
        应用了日期过滤的查询对象
    
    Example:
        query = apply_date_range_filter(
            select(AdData),
            AdData.date,
            start_date,
            end_date
        )
    """
    
    # 如果指定了日期范围，使用指定的范围
    if start_date or end_date:
        condition = date_range_condition(date_column, start_date, end_date)
        # 注意：不能直接使用 if condition，因为 SQLAlchemy 表达式对象不能用于布尔判断
        if condition is not None:
            query = query.where(condition)
    elif default_to_current_month:
        # 如果没有指定日期范围，默认使用当前月
        today = date.today()
        month_start = date(today.year, today.month, 1)
        _, last_day = monthrange(today.year, today.month)
        month_end = date(today.year, today.month, last_day)
        
        condition = date_range_condition(date_column, month_start, month_end)
        # 注意：不能直接使用 if condition，因为 SQLAlchemy 表达式对象不能用于布尔判断
        if condition is not None:
            query = query.where(condition)
    
    return query


# 产品分配表开关缓存（全局布尔，变更频率极低）
_ASSIGNMENT_TABLE_CACHE: tuple[bool, float] | None = None
_ASSIGNMENT_TABLE_CACHE_TTL = 1800  # 30 分钟


def invalidate_assignment_table_cache() -> None:
    """产品分配记录增删后调用，使 check_use_assignment_table 重新探测。"""
    global _ASSIGNMENT_TABLE_CACHE
    _ASSIGNMENT_TABLE_CACHE = None


async def check_use_assignment_table(db) -> bool:
    """
    检查是否应该使用产品分配历史表
    
    如果 product_assignments 表中有数据，则使用分配历史表进行查询
    否则使用旧的查询方式（直接通过 Product.client_id）
    
    Args:
        db: 数据库会话（AsyncSession）
        
    Returns:
        bool: 如果应该使用分配历史表返回 True，否则返回 False
    """
    global _ASSIGNMENT_TABLE_CACHE
    now = time.monotonic()
    if _ASSIGNMENT_TABLE_CACHE is not None:
        cached_value, cached_at = _ASSIGNMENT_TABLE_CACHE
        if now - cached_at < _ASSIGNMENT_TABLE_CACHE_TTL:
            return cached_value

    try:
        test_query = select(func.count(ProductAssignment.id))
        test_result = await db.execute(test_query)
        assignment_count = test_result.scalar() or 0
        use_table = assignment_count > 0
        _ASSIGNMENT_TABLE_CACHE = (use_table, now)
        return use_table
    except Exception:
        # 如果查询失败（例如表不存在），返回 False，使用旧的查询方式
        return False


def join_country_info(query: Select, country_code_column: Column) -> Select:
    """
    统一处理 CountryInfo 的 JOIN，解决排序规则冲突问题
    
    临时方案：使用 COLLATE 统一排序规则
    永久方案：运行 scripts/fix_collation_issue.sql 修改表结构
    
    Args:
        query: SQLAlchemy 查询对象
        country_code_column: 国家代码列（如 AdData.country_code 或 TBSearchData.country_code）
    
    Returns:
        应用了 CountryInfo JOIN 的查询对象
    
    Example:
        query = join_country_info(query, AdData.country_code)
    """
    
    # 使用列对象的 collate() 方法统一排序规则
    # 这样可以确保 SQLAlchemy 正确处理表别名和列引用
    return query.outerjoin(
        CountryInfo,
        country_code_column.collate('utf8mb4_unicode_ci') == 
        CountryInfo.alpha_2_code.collate('utf8mb4_unicode_ci')
    )
