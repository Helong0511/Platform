"""
查询工具模块
提供常用的查询优化函数，避免在列上使用函数导致索引失效
"""
from datetime import date, datetime
from sqlalchemy import Column, and_, or_, text, func, literal_column, case
from typing import Optional
from sqlalchemy.sql import Select


def date_range_condition(
    column: Column,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> Optional[any]:
    """
    生成日期范围查询条件（优化版本）
    避免在列上使用函数，提升索引使用率
    
    Args:
        column: 日期列（DATETIME 类型）
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
        # 将 date 转换为 datetime 的开始时间（00:00:00）
        start_datetime = datetime.combine(start_date, datetime.min.time())
        conditions.append(column >= start_datetime)
    
    if end_date:
        # 将 date 转换为 datetime 的结束时间（23:59:59.999999）
        end_datetime = datetime.combine(end_date, datetime.max.time())
        conditions.append(column <= end_datetime)
    
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
        ad_data_date: AdData.date 列（DATETIME 类型）
        assignment_start: ProductAssignment.start_date 列（DATE 类型）
        assignment_end: ProductAssignment.end_date 列（DATE 类型，可为 NULL）
    
    Returns:
        SQLAlchemy JOIN 条件表达式
    
    Note:
        MySQL 会自动将 DATE 转换为 DATETIME（时间部分为 00:00:00）进行比较
        为了包含整天的数据，结束日期需要加 1 天
    
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
        # 开始日期：ad_data.date >= start_date 的 00:00:00
        ad_data_date >= assignment_start,
        # 结束日期条件：end_date IS NULL OR ad_data_date < end_date + 1 DAY
        or_(
            # 如果 end_date 为 NULL，表示当前有效
            assignment_end.is_(None),
            # 如果 end_date 不为 NULL，使用 DATE_ADD 确保包含整天的数据
            # 直接内联表达式，与 ad_data.py 中的写法完全一致
            ad_data_date < func.date_add(assignment_end, text("INTERVAL 1 DAY"))
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
    from calendar import monthrange
    
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
    try:
        from sqlalchemy import select, func
        from app.models.models import ProductAssignment
        
        test_query = select(func.count(ProductAssignment.id))
        test_result = await db.execute(test_query)
        assignment_count = test_result.scalar() or 0
        return assignment_count > 0
    except Exception:
        # 如果查询失败（例如表不存在），返回 False，使用旧的查询方式
        return False

