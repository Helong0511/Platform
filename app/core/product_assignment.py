"""
产品分配历史管理工具函数
用于记录和管理产品在不同时间段的客户归属
"""
from collections import defaultdict
from typing import Any, Optional, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, exists, text
from datetime import date, datetime, timezone, timedelta
from app.models.models import Product, ProductAssignment, Client, AdData
from app.core.query_utils import invalidate_assignment_table_cache
import logging

logger = logging.getLogger(__name__)


async def create_product_assignment(
    db: AsyncSession,
    product_id: int,
    client_id: int,
    start_date: date | None = None,
    end_date: date | None = None
) -> ProductAssignment:
    """
    创建产品分配记录
    
    Args:
        db: 数据库会话
        product_id: 产品ID
        client_id: 客户ID
        start_date: 分配开始日期（如果为None，使用当前日期）
        end_date: 分配结束日期（如果为None，表示当前有效）
    
    Returns:
        ProductAssignment: 创建的分配记录
    """
    if start_date is None:
        start_date = date.today()
    
    # 检查是否存在重叠的分配记录（确保没有重复占用时间）
    # 重叠条件：两个日期范围有交集
    # 范围A: [start_date, end_date or date.max]
    # 范围B: [assignment.start_date, assignment.end_date or date.max]
    # 重叠：A.start <= B.end AND A.end >= B.start
    overlap_query = select(ProductAssignment).where(
        and_(
            ProductAssignment.product_id == product_id,
            # 新记录的结束日期（或最大日期）>= 现有记录的开始日期
            (end_date if end_date else date.max) >= ProductAssignment.start_date,
            # 新记录的开始日期 <= 现有记录的结束日期（或最大日期）
            start_date <= (ProductAssignment.end_date if ProductAssignment.end_date is not None else date.max)
        )
    )
    overlap_result = await db.execute(overlap_query)
    overlapping_assignments = overlap_result.scalars().all()
    
    # 检查是否有重叠的记录
    if overlapping_assignments:
        overlap_info = ", ".join([
            f"记录ID {a.id} (客户ID: {a.client_id}, {a.start_date} 至 {a.end_date or '当前有效'})"
            for a in overlapping_assignments
        ])
        raise ValueError(
            f"日期重叠错误：新分配记录（开始日期: {start_date}, 结束日期: {end_date or '当前有效'}）"
            f"与现有记录重叠：{overlap_info}，请确保日期不重复占用"
        )
    
    assignment = ProductAssignment(
        product_id=product_id,
        client_id=client_id,
        start_date=start_date,
        end_date=end_date
    )
    db.add(assignment)
    await db.flush()
    invalidate_assignment_table_cache()

    # 验证分配记录的完整性（捕获验证过程中的异常，避免影响创建）
    try:
        validation_result = await validate_product_assignments(db, product_id)
        if validation_result["errors"]:
            # 验证失败：删除刚创建的分配记录，而不是回滚整个事务
            # 这样可以避免影响其他已创建的对象（如产品）
            await db.delete(assignment)
            await db.flush()  # 确保删除操作生效
            error_msg = "; ".join(validation_result["errors"])
            raise ValueError(
                f"创建分配记录后验证失败：{error_msg}。"
                f"请检查产品 {product_id} 的分配记录是否存在重叠、空窗期或不连贯的问题。"
            )
        
        if validation_result["warnings"]:
            for warning in validation_result["warnings"]:
                logger.warning(warning)
    except ValueError:
        # 重新抛出ValueError（验证失败），让调用者处理
        raise
    except Exception as e:
        # 如果验证过程本身出错，记录错误但不影响创建
        logger.error(f"验证产品 {product_id} 分配记录时出错: {str(e)}", exc_info=True)
        # 不抛出异常，允许创建继续
    
    return assignment


async def close_active_assignment(
    db: AsyncSession,
    product_id: int,
    end_date: date
) -> bool:
    """
    关闭产品的当前有效分配记录（设置end_date）
    
    Args:
        db: 数据库会话
        product_id: 产品ID
        end_date: 结束日期（通常是产品转移的日期）
    
    Returns:
        bool: 是否成功关闭了分配记录
    """
    # 查找当前有效的分配记录（end_date为NULL）
    query = select(ProductAssignment).where(
        and_(
            ProductAssignment.product_id == product_id,
            ProductAssignment.end_date.is_(None)
        )
    )
    result = await db.execute(query)
    active_assignment = result.scalars().first()
    
    if active_assignment:
        active_assignment.end_date = end_date
        await db.flush()
        logger.info(
            f"已关闭产品 {product_id} 的分配记录 {active_assignment.id}，"
            f"结束日期: {end_date}"
        )
        return True
    else:
        logger.warning(f"产品 {product_id} 没有找到有效的分配记录")
        return False


async def transfer_product_assignment(
    db: AsyncSession,
    product_id: int,
    old_client_id: int,
    new_client_id: int,
    transfer_date: date | None = None,
    old_client_end_date: date | None = None
) -> tuple[ProductAssignment, bool]:
    """
    转移产品分配（关闭旧分配，创建新分配）
    
    Args:
        db: 数据库会话
        product_id: 产品ID
        old_client_id: 原客户ID
        new_client_id: 新客户ID
        transfer_date: 新客户开始拥有该产品的日期（如果为None，使用当前日期）
        old_client_end_date: 旧客户拥有该产品的结束日期（可选，如果为None，自动计算为transfer_date的前一天）
        注意：如果提供了old_client_end_date，新记录的start_date为old_client_end_date + 1天
        这样可以确保日期连续覆盖，避免日期间隙
    
    Returns:
        tuple[ProductAssignment, bool]: (新分配记录, 是否成功关闭了旧记录)
    """
    
    # 确定旧客户的结束日期和新客户的开始日期
    # 优先级：如果提供了 old_client_end_date，使用它；否则使用 transfer_date 计算
    if old_client_end_date is not None:
        # 使用用户指定的旧客户结束日期
        old_end_date = old_client_end_date
        # 新客户开始日期 = 旧客户结束日期 + 1天（确保日期连续，无空窗期）
        new_start_date = old_end_date + timedelta(days=1)
        
        # 如果同时提供了 transfer_date，验证它们是否一致（允许1天的差异）
        if transfer_date is not None:
            if abs((transfer_date - new_start_date).days) > 0:
                logger.warning(
                    f"transfer_date ({transfer_date}) 与计算的新开始日期 ({new_start_date}) 不一致，"
                    f"将使用计算值以确保日期连续"
                )
    else:
        # 如果没有指定旧客户结束日期，使用默认逻辑
        if transfer_date is None:
            transfer_date = date.today()
        # 计算旧记录的结束日期（转移日期前一天，确保日期连续覆盖）
        old_end_date = transfer_date - timedelta(days=1)
        new_start_date = transfer_date
    
    # 验证日期逻辑：确保旧客户结束日期 < 新客户开始日期（必须严格小于，不能等于）
    if old_end_date >= new_start_date:
        raise ValueError(
            f"日期逻辑错误：旧客户结束日期（{old_end_date}）必须小于新客户开始日期（{new_start_date}），"
            f"当前差值：{(new_start_date - old_end_date).days}天"
        )
    
    # 验证日期连续性：新客户开始日期必须是旧客户结束日期 + 1天
    expected_new_start = old_end_date + timedelta(days=1)
    if new_start_date != expected_new_start:
        raise ValueError(
            f"日期连续性错误：新客户开始日期（{new_start_date}）必须是旧客户结束日期（{old_end_date}）+ 1天，"
            f"期望值：{expected_new_start}，当前差值：{(new_start_date - old_end_date).days}天"
        )
    
    # 检查是否存在与新记录重叠的其他分配记录（确保没有重复占用时间）
    # 注意：这里只检查其他客户的记录，当前客户的记录会被关闭，所以不算重叠
    # 重叠条件：两个日期范围有交集
    # 范围A: [new_start_date, None (即date.max)]
    # 范围B: [assignment.start_date, assignment.end_date or date.max]
    # 重叠：A.start <= B.end AND A.end >= B.start
    overlap_check_query = select(ProductAssignment).where(
        and_(
            ProductAssignment.product_id == product_id,
            # 排除即将被关闭的当前有效记录（old_client_id的记录）
            or_(
                ProductAssignment.client_id != old_client_id,
                ProductAssignment.end_date.isnot(None)  # 只检查已有结束日期的记录
            ),
            # 检查日期范围是否重叠
            # 新记录的结束日期（date.max）>= 现有记录的开始日期
            date.max >= ProductAssignment.start_date,
            # 新记录的开始日期 <= 现有记录的结束日期（或date.max）
            new_start_date <= (ProductAssignment.end_date if ProductAssignment.end_date is not None else date.max)
        )
    )
    overlap_check_result = await db.execute(overlap_check_query)
    overlapping_assignments = overlap_check_result.scalars().all()
    
    # 如果有重叠记录，报错
    if overlapping_assignments:
        overlap_info = ", ".join([
            f"记录ID {a.id} (客户ID: {a.client_id}, {a.start_date} 至 {a.end_date or '当前有效'})"
            for a in overlapping_assignments
        ])
        raise ValueError(
            f"日期重叠错误：新分配记录（开始日期: {new_start_date}）与现有记录重叠：{overlap_info}，"
            f"请确保日期不重复占用"
        )
    
    # 优化：检查是否存在一个当前有效的记录，其开始日期与新客户开始日期相同
    # 如果存在，直接更新该记录的client_id，而不是关闭+创建
    existing_active_query = select(ProductAssignment).where(
        and_(
            ProductAssignment.product_id == product_id,
            ProductAssignment.client_id == old_client_id,
            ProductAssignment.start_date == new_start_date,
            ProductAssignment.end_date.is_(None)
        )
    )
    existing_active_result = await db.execute(existing_active_query)
    existing_active_assignment = existing_active_result.scalars().first()
    
    if existing_active_assignment:
        # 在更新之前，检查新客户ID是否已经有重叠的记录
        # 由于只是更新client_id，日期范围不变，所以只需要检查新客户ID是否已经有相同日期范围的记录
        new_client_overlap_query = select(ProductAssignment).where(
            and_(
                ProductAssignment.product_id == product_id,
                ProductAssignment.client_id == new_client_id,
                ProductAssignment.start_date == new_start_date,
                ProductAssignment.end_date.is_(None)
            )
        )
        new_client_overlap_result = await db.execute(new_client_overlap_query)
        new_client_overlap = new_client_overlap_result.scalars().first()
        
        if new_client_overlap:
            # 新客户ID已经有相同日期范围的记录，这是数据错误，应该报错
            raise ValueError(
                f"数据错误：新客户ID {new_client_id} 已经有一个相同日期范围的分配记录 "
                f"(记录ID: {new_client_overlap.id}, 开始日期: {new_start_date})，"
                f"无法转移产品 {product_id}。请先清理重复记录。"
            )
        else:
            # 直接更新现有记录的client_id
            existing_active_assignment.client_id = new_client_id
            await db.flush()
            logger.info(
                f"产品 {product_id} 已从客户 {old_client_id} 转移到客户 {new_client_id}，"
                f"直接更新了分配记录 {existing_active_assignment.id} 的客户ID"
            )
            new_assignment = existing_active_assignment
            closed = False  # 没有关闭记录，只是更新了
    else:
        # 关闭当前有效的分配记录（设置end_date为旧客户结束日期）
        closed = await close_active_assignment(db, product_id, old_end_date)
        
        # 再次检查重叠（在关闭旧记录后）
        # 创建新的分配记录（start_date为新客户开始日期）
        # create_product_assignment 函数内部也会检查重叠
        new_assignment = await create_product_assignment(
            db=db,
            product_id=product_id,
            client_id=new_client_id,
            start_date=new_start_date,
            end_date=None  # 当前有效
        )
    
    # 验证转移后的分配记录完整性（捕获验证过程中的异常）
    try:
        validation_result = await validate_product_assignments(db, product_id)
        if validation_result["errors"]:
            # 回滚操作
            await db.rollback()
            error_msg = "; ".join(validation_result["errors"])
            raise ValueError(
                f"产品转移后验证失败：{error_msg}。"
                f"请检查产品 {product_id} 的分配记录是否存在重叠、空窗期或不连贯的问题。"
            )
        
        if validation_result["warnings"]:
            for warning in validation_result["warnings"]:
                logger.warning(warning)
    except ValueError:
        # 重新抛出ValueError（验证失败），让调用者处理
        raise
    except Exception as e:
        # 如果验证过程本身出错，记录错误但不影响转移
        logger.error(f"验证产品 {product_id} 分配记录时出错: {str(e)}", exc_info=True)
        # 不抛出异常，允许转移继续
    
    logger.info(
        f"产品 {product_id} 已从客户 {old_client_id} 转移到客户 {new_client_id}，"
        f"旧客户结束日期: {old_end_date}，新客户开始日期: {new_start_date}"
    )
    
    return new_assignment, closed


async def get_client_id_for_date(
    db: AsyncSession,
    product_id: int,
    target_date: date
) -> int | None:
    """
    获取产品在指定日期的客户ID
    
    Args:
        db: 数据库会话
        product_id: 产品ID
        target_date: 目标日期
    
    Returns:
        int | None: 客户ID，如果找不到则返回None
    """
    query = select(ProductAssignment).where(
        and_(
            ProductAssignment.product_id == product_id,
            ProductAssignment.start_date <= target_date,
            or_(
                ProductAssignment.end_date.is_(None),
                ProductAssignment.end_date >= target_date  # 使用 >= 确保日期连续覆盖，避免空窗期
            )
        )
    ).order_by(ProductAssignment.start_date.desc())
    
    result = await db.execute(query)
    assignment = result.scalars().first()
    
    if assignment:
        return assignment.client_id
    return None


async def validate_product_assignments(
    db: AsyncSession,
    product_id: int
) -> dict[str, list[str]]:
    """
    验证产品分配记录的逻辑完整性
    
    检查以下问题：
    1. 重叠：两个客户不能同时拥有产品
    2. 空窗期：日期必须连续覆盖，不能有间隙
    3. 不连贯：日期必须按顺序排列
    
    Args:
        db: 数据库会话
        product_id: 产品ID
    
    Returns:
        dict: 包含错误信息的字典，格式为 {"errors": [错误列表], "warnings": [警告列表]}
    """
    errors = []
    warnings = []
    
    try:
        # 获取该产品的所有分配记录，按开始日期排序
        query = select(ProductAssignment).where(
            ProductAssignment.product_id == product_id
        ).order_by(ProductAssignment.start_date.asc())
        
        result = await db.execute(query)
        assignments = result.scalars().all()
        
        if not assignments:
            warnings.append(f"产品 {product_id} 没有任何分配记录")
            return {"errors": errors, "warnings": warnings}
    except Exception as e:
        # 如果查询失败，返回错误
        errors.append(f"查询产品 {product_id} 的分配记录时出错: {str(e)}")
        return {"errors": errors, "warnings": warnings}
    
    # 优化：先排序，然后使用扫描线算法检查重叠和间隙
    # 将复杂度从 O(n²) 降低到 O(n log n)
    sorted_assignments = sorted(assignments, key=lambda a: (a.start_date, a.id))
    
    # 检查1：重叠检查（优化版本）
    # 使用扫描线算法：对于每个记录，检查它与后续记录是否重叠
    # 由于已排序，如果当前记录的结束日期 < 下一个记录的开始日期，则后续记录都不会重叠
    for i, assignment1 in enumerate(sorted_assignments):
        range1_end = assignment1.end_date if assignment1.end_date else date.max
        
        # 只检查后续记录（避免重复检查）
        for j in range(i + 1, len(sorted_assignments)):
            assignment2 = sorted_assignments[j]
            
            # 如果当前记录的结束日期 < 下一个记录的开始日期，后续记录都不会重叠
            if range1_end < assignment2.start_date:
                break
            
            # 计算第二个记录的有效日期范围
            range2_end = assignment2.end_date if assignment2.end_date else date.max
            
            # 检查是否重叠：A.start <= B.end AND A.end >= B.start
            if range1_end >= assignment2.start_date:
                errors.append(
                    f"日期重叠：记录ID {assignment1.id} (客户ID: {assignment1.client_id}, "
                    f"{assignment1.start_date} 至 {assignment1.end_date or '当前有效'}) "
                    f"与记录ID {assignment2.id} (客户ID: {assignment2.client_id}, "
                    f"{assignment2.start_date} 至 {assignment2.end_date or '当前有效'}) 重叠"
                )
    
    # 检查2和3：空窗期和不连贯检查
    
    for i in range(len(sorted_assignments) - 1):
        current = sorted_assignments[i]
        next_assignment = sorted_assignments[i + 1]
        
        # 当前记录的结束日期
        current_end = current.end_date if current.end_date else date.max
        
        # 检查是否有间隙
        if current_end != date.max:
            # 如果当前记录有结束日期，下一个记录的开始日期应该是当前结束日期 + 1天
            expected_next_start = current_end + timedelta(days=1)
            if next_assignment.start_date != expected_next_start:
                if next_assignment.start_date < expected_next_start:
                    errors.append(
                        f"日期重叠：记录ID {current.id} (结束日期: {current.end_date}) "
                        f"与记录ID {next_assignment.id} (开始日期: {next_assignment.start_date}) 重叠"
                    )
                else:
                    # 有空窗期
                    gap_days = (next_assignment.start_date - expected_next_start).days
                    errors.append(
                        f"空窗期：记录ID {current.id} (结束日期: {current.end_date}) "
                        f"与记录ID {next_assignment.id} (开始日期: {next_assignment.start_date}) "
                        f"之间存在 {gap_days} 天的空窗期"
                    )
        else:
            # 当前记录是当前有效的（end_date为NULL）
            # 如果下一个记录也有end_date为NULL（也是当前有效的），这是错误（应该只有一个当前有效的记录）
            if next_assignment.end_date is None:
                errors.append(
                    f"逻辑错误：记录ID {current.id} 和记录ID {next_assignment.id} 都是当前有效的（end_date为NULL），"
                    f"应该只有一个当前有效的记录"
                )
            # 如果下一个记录有end_date（是历史记录），检查是否重叠
            elif next_assignment.end_date is not None:
                # 如果下一个记录的开始日期在当前日期之前或等于当前日期，且结束日期在当前日期之后或等于当前日期，说明有重叠
                if (next_assignment.start_date <= date.today() and 
                    next_assignment.end_date >= date.today()):
                    errors.append(
                        f"日期重叠：记录ID {current.id} 是当前有效的（end_date为NULL），"
                        f"与记录ID {next_assignment.id} ({next_assignment.start_date} 至 {next_assignment.end_date}) 重叠"
                    )
                # 如果下一个记录已经完全结束（end_date < 今天），这是正常的，不会重叠
                # 如果下一个记录在未来开始（start_date > 今天），这也是正常的，不会重叠
    
    # 检查是否有多个当前有效的记录
    active_assignments = [a for a in assignments if a.end_date is None]
    if len(active_assignments) > 1:
        active_ids = [a.id for a in active_assignments]
        errors.append(
            f"逻辑错误：产品 {product_id} 有 {len(active_assignments)} 个当前有效的分配记录 "
            f"(记录ID: {active_ids})，应该只有一个"
        )
    
    # 检查日期顺序
    for i in range(len(sorted_assignments) - 1):
        current = sorted_assignments[i]
        next_assignment = sorted_assignments[i + 1]
        
        if current.start_date > next_assignment.start_date:
            errors.append(
                f"日期顺序错误：记录ID {current.id} (开始日期: {current.start_date}) "
                f"应该早于记录ID {next_assignment.id} (开始日期: {next_assignment.start_date})"
            )
    
    return {"errors": errors, "warnings": warnings}


def _assignment_covers_ad_data_date_condition():
    """与详情报表 join_product_and_client 一致的分配日期匹配条件。"""
    return and_(
        ProductAssignment.product_id == AdData.product_id,
        AdData.date >= ProductAssignment.start_date,
        or_(
            ProductAssignment.end_date.is_(None),
            AdData.date <= ProductAssignment.end_date,
        ),
    )


async def find_ad_data_assignment_gaps(
    db: AsyncSession,
    *,
    start_date: date,
    end_date: date,
    product_ids: Optional[Sequence[int]] = None,
    limit: int = 15,
) -> tuple[list[dict[str, Any]], int]:
    """
    查找 ad_data 在指定日期范围内无产品分配覆盖的记录（按产品+日期聚合）。

    Returns:
        (gap 列表, orphan 总行数)
    """
    has_assignment = exists(
        select(1)
        .select_from(ProductAssignment)
        .where(_assignment_covers_ad_data_date_condition())
    )

    filters = [
        AdData.date >= start_date,
        AdData.date <= end_date,
        ~has_assignment,
    ]
    if product_ids:
        filters.append(AdData.product_id.in_(list(product_ids)))

    count_query = select(func.count(AdData.id)).select_from(AdData).where(*filters)
    total_orphan = int((await db.execute(count_query)).scalar() or 0)
    if total_orphan == 0:
        return [], 0

    detail_query = (
        select(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            AdData.date.label("data_date"),
            func.count(AdData.id).label("row_count"),
        )
        .join(Product, AdData.product_id == Product.id)
        .where(*filters)
        .group_by(Product.id, Product.name, AdData.date)
        .order_by(AdData.date.desc(), func.count(AdData.id).desc())
        .limit(limit)
    )
    rows = (await db.execute(detail_query)).all()
    gaps = [
        {
            "product_id": r.product_id,
            "product_name": r.product_name,
            "data_date": r.data_date.isoformat() if hasattr(r.data_date, "isoformat") else str(r.data_date),
            "row_count": int(r.row_count),
        }
        for r in rows
    ]
    return gaps, total_orphan


def format_assignment_gap_telegram_message(
    *,
    notify_title: str,
    gaps: list[dict[str, Any]],
    total_orphan: int,
) -> str:
    """格式化产品分配空窗 Telegram 告警正文。"""
    lines = [
        "⚠️ 产品分配覆盖异常",
        "",
        f"来源: {notify_title}",
        f"无有效分配、详情报表不可见的广告数据: {total_orphan} 条",
        "",
        "明细（产品 × 日期）:",
    ]
    for item in gaps:
        lines.append(
            f"• {item['product_name']} | {item['data_date']} | {item['row_count']} 条"
        )
    listed = sum(g["row_count"] for g in gaps)
    if total_orphan > listed:
        lines.append(f"• … 其余 {total_orphan - listed} 条未列出")
    lines.append("")
    lines.append("请在「产品管理 → 分配历史」检查空窗日期并补全归属。")
    return "\n".join(lines)


async def initialize_product_assignment(
    db: AsyncSession,
    product_id: int,
    client_id: int,
    start_date: date | None = None
) -> ProductAssignment:
    """
    初始化产品的分配记录（用于新创建的产品）
    
    Args:
        db: 数据库会话
        product_id: 产品ID
        client_id: 客户ID
        start_date: 开始日期（如果为None，使用当前日期）
    
    Returns:
        ProductAssignment: 创建的分配记录
    """
    if start_date is None:
        start_date = date.today()
    
    # 检查是否已存在分配记录
    query = select(ProductAssignment).where(
        ProductAssignment.product_id == product_id
    )
    result = await db.execute(query)
    existing = result.scalars().first()
    
    if existing:
        logger.warning(f"产品 {product_id} 已存在分配记录，跳过初始化")
        return existing
    
    assignment = await create_product_assignment(
        db=db,
        product_id=product_id,
        client_id=client_id,
        start_date=start_date,
        end_date=None
    )
    
    # 验证分配记录的完整性
    validation_result = await validate_product_assignments(db, product_id)
    if validation_result["errors"]:
        logger.error(f"产品 {product_id} 分配记录验证失败: {validation_result['errors']}")
        # 不抛出异常，因为这是初始化操作，可能是在修复数据
    
    return assignment


async def cleanup_invalid_assignments(
    db: AsyncSession,
    product_id: int | None = None
) -> dict[str, Any]:
    """
    清理无效的产品分配记录
    
    清理规则：
    1. 删除日期逻辑错误的记录（start_date > end_date）
    2. 删除重复的记录（同一产品、同一客户、同一天的多条记录，保留end_date为NULL的记录）
    3. 保留正确的记录（end_date为NULL的当前有效记录）
    
    Args:
        db: 数据库会话
        product_id: 产品ID（如果为None，清理所有产品）
    
    Returns:
        dict: 清理结果，包含删除的记录数量和详细信息
    """
    
    deleted_count = 0
    deleted_records = []
    errors = []
    
    try:
        # 构建查询条件
        query = select(ProductAssignment)
        if product_id is not None:
            query = query.where(ProductAssignment.product_id == product_id)
        
        result = await db.execute(query)
        all_assignments = result.scalars().all()
        
        # 按产品ID分组处理
        assignments_by_product: dict[int, list[ProductAssignment]] = {}
        for assignment in all_assignments:
            if assignment.product_id not in assignments_by_product:
                assignments_by_product[assignment.product_id] = []
            assignments_by_product[assignment.product_id].append(assignment)
        
        # 处理每个产品的记录
        for pid, assignments in assignments_by_product.items():
            # 1. 删除日期逻辑错误的记录（start_date > end_date）
            invalid_date_records = [
                a for a in assignments
                if a.end_date is not None and a.start_date > a.end_date
            ]
            
            for record in invalid_date_records:
                try:
                    await db.delete(record)
                    deleted_count += 1
                    deleted_records.append({
                        "id": record.id,
                        "product_id": record.product_id,
                        "client_id": record.client_id,
                        "reason": f"日期逻辑错误：start_date ({record.start_date}) > end_date ({record.end_date})",
                        "start_date": str(record.start_date),
                        "end_date": str(record.end_date)
                    })
                    logger.info(
                        f"删除日期逻辑错误的记录 ID {record.id}："
                        f"产品 {record.product_id}，客户 {record.client_id}，"
                        f"开始日期 {record.start_date} > 结束日期 {record.end_date}"
                    )
                except Exception as e:
                    error_msg = f"删除记录 ID {record.id} 失败: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
            
            # 2. 删除重复的记录（同一产品、同一客户、同一天的多条记录）
            # 按 (product_id, client_id, start_date) 分组
            grouped_by_key: dict[tuple[int, int, date], list[ProductAssignment]] = defaultdict(list)
            
            remaining_assignments = [
                a for a in assignments
                if a.end_date is None or a.start_date <= a.end_date  # 排除已删除的日期逻辑错误记录
            ]
            
            for assignment in remaining_assignments:
                key = (assignment.product_id, assignment.client_id, assignment.start_date)
                grouped_by_key[key].append(assignment)
            
            # 对于每个分组，如果有多个记录，保留end_date为NULL的记录，删除其他记录
            for key, group in grouped_by_key.items():
                if len(group) > 1:
                    # 优先保留end_date为NULL的记录
                    active_records = [a for a in group if a.end_date is None]
                    inactive_records = [a for a in group if a.end_date is not None]
                    
                    if len(active_records) > 1:
                        # 如果有多个当前有效的记录，保留ID最大的（最新的）
                        active_records.sort(key=lambda x: x.id, reverse=True)
                        to_delete = active_records[1:]  # 删除除第一个外的所有记录
                        for record in to_delete:
                            try:
                                await db.delete(record)
                                deleted_count += 1
                                deleted_records.append({
                                    "id": record.id,
                                    "product_id": record.product_id,
                                    "client_id": record.client_id,
                                    "reason": f"重复的当前有效记录（保留ID {active_records[0].id}）",
                                    "start_date": str(record.start_date),
                                    "end_date": "NULL"
                                })
                                logger.info(
                                    f"删除重复的当前有效记录 ID {record.id}："
                                    f"产品 {record.product_id}，客户 {record.client_id}，"
                                    f"开始日期 {record.start_date}"
                                )
                            except Exception as e:
                                error_msg = f"删除记录 ID {record.id} 失败: {str(e)}"
                                errors.append(error_msg)
                                logger.error(error_msg)
                    
                    # 如果有当前有效记录，删除所有已结束的记录
                    if active_records:
                        for record in inactive_records:
                            try:
                                await db.delete(record)
                                deleted_count += 1
                                deleted_records.append({
                                    "id": record.id,
                                    "product_id": record.product_id,
                                    "client_id": record.client_id,
                                    "reason": f"与当前有效记录重复（保留ID {active_records[0].id}）",
                                    "start_date": str(record.start_date),
                                    "end_date": str(record.end_date)
                                })
                                logger.info(
                                    f"删除与当前有效记录重复的记录 ID {record.id}："
                                    f"产品 {record.product_id}，客户 {record.client_id}，"
                                    f"开始日期 {record.start_date}，结束日期 {record.end_date}"
                                )
                            except Exception as e:
                                error_msg = f"删除记录 ID {record.id} 失败: {str(e)}"
                                errors.append(error_msg)
                                logger.error(error_msg)
                    else:
                        # 如果没有当前有效记录，保留ID最大的记录，删除其他记录
                        group.sort(key=lambda x: x.id, reverse=True)
                        to_delete = group[1:]  # 删除除第一个外的所有记录
                        for record in to_delete:
                            try:
                                await db.delete(record)
                                deleted_count += 1
                                deleted_records.append({
                                    "id": record.id,
                                    "product_id": record.product_id,
                                    "client_id": record.client_id,
                                    "reason": f"重复记录（保留ID {group[0].id}）",
                                    "start_date": str(record.start_date),
                                    "end_date": str(record.end_date) if record.end_date else "NULL"
                                })
                                logger.info(
                                    f"删除重复记录 ID {record.id}："
                                    f"产品 {record.product_id}，客户 {record.client_id}，"
                                    f"开始日期 {record.start_date}"
                                )
                            except Exception as e:
                                error_msg = f"删除记录 ID {record.id} 失败: {str(e)}"
                                errors.append(error_msg)
                                logger.error(error_msg)
        
        # 提交删除操作
        await db.commit()

        if deleted_count > 0:
            invalidate_assignment_table_cache()
        
        logger.info(
            f"清理完成：删除了 {deleted_count} 条无效的产品分配记录"
            f"{f'（产品ID: {product_id}）' if product_id else '（所有产品）'}"
        )
        
        return {
            "deleted_count": deleted_count,
            "deleted_records": deleted_records,
            "errors": errors,
            "message": f"成功删除 {deleted_count} 条无效记录"
        }
        
    except Exception as e:
        await db.rollback()
        error_msg = f"清理产品分配记录时出错: {str(e)}"
        logger.error(error_msg, exc_info=True)
        errors.append(error_msg)
        return {
            "deleted_count": deleted_count,
            "deleted_records": deleted_records,
            "errors": errors,
            "message": f"清理失败: {error_msg}"
        }