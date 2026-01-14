<<<<<<< HEAD
"""
批量操作工具模块
提供高效的批量插入/更新功能，使用 MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.mysql import insert
from sqlalchemy import func, Float, case, update
from typing import List, Dict, Any
import logging
from app.core.utils import get_app_now_naive
from app.models.models import AdData

logger = logging.getLogger(__name__)


async def batch_upsert_ad_data(
    data_list: List[Dict[str, Any]],
    db: AsyncSession,
    batch_size: int = 1000
) -> tuple[int, int]:
    """
    批量插入/更新广告数据
    使用 MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE 语法
    
    Args:
        data_list: 要插入/更新的数据列表，每个元素是一个字典
        db: 数据库会话
        batch_size: 每批处理的数据量，默认 1000
    
    Returns:
        tuple[int, int]: (插入数量, 更新数量)
    
    Example:
        data_list = [
            {
                "date": datetime(2024, 1, 1),
                "product_id": 1,
                "request_count": 1000,
                "match_count": 800,
                ...
            },
            ...
        ]
        inserted, updated = await batch_upsert_ad_data(data_list, db)
    """
    if not data_list:
        return 0, 0
    
    inserted_count = 0
    updated_count = 0
    
    # 分批处理
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i + batch_size]
        
        try:
            # 使用 INSERT ... ON DUPLICATE KEY UPDATE
            # 如果 (date, product_id) 已存在，则更新；否则插入
            stmt = insert(AdData).values(batch)
            
            stmt = stmt.on_duplicate_key_update(
                request_count=stmt.inserted.request_count,
                match_count=stmt.inserted.match_count,
                display_count=stmt.inserted.display_count,
                click_count=stmt.inserted.click_count,
                # 更新比率字段（如果数据中包含，否则使用计算值）
                coverage_rate=case(
                    (stmt.inserted.coverage_rate.isnot(None), stmt.inserted.coverage_rate),
                    (stmt.inserted.request_count > 0, func.cast(stmt.inserted.match_count, Float) * 100.0 / func.cast(stmt.inserted.request_count, Float)),
                    else_=0.0
                ),
                display_rate=case(
                    (stmt.inserted.display_rate.isnot(None), stmt.inserted.display_rate),
                    (stmt.inserted.match_count > 0, func.cast(stmt.inserted.display_count, Float) * 100.0 / func.cast(stmt.inserted.match_count, Float)),
                    else_=0.0
                ),
                click_rate=case(
                    (stmt.inserted.click_rate.isnot(None), stmt.inserted.click_rate),
                    (stmt.inserted.display_count > 0, func.cast(stmt.inserted.click_count, Float) * 100.0 / func.cast(stmt.inserted.display_count, Float)),
                    else_=0.0
                ),
                ecpm_before_deduct=stmt.inserted.ecpm_before_deduct,
                ecpm_after_deduct=stmt.inserted.ecpm_after_deduct,
                revenue_before_deduct=stmt.inserted.revenue_before_deduct,
                revenue_after_deduct=stmt.inserted.revenue_after_deduct,
                updated_at=get_app_now_naive()  # 使用北京时间
            )
            
            result = await db.execute(stmt)
            
            # MySQL 返回受影响的行数
            # 注意：ON DUPLICATE KEY UPDATE 时，affected_rows = 1（插入）或 2（更新）
            # 但无法准确区分插入和更新，所以这里使用估算
            # 实际可以通过比较 before/after 的记录数来估算
            affected_rows = result.rowcount
            
            # 估算：假设一半是插入，一半是更新（不准确，但可以用于日志）
            # 更准确的方法是在执行前查询已存在的记录数
            estimated_inserted = affected_rows // 2
            estimated_updated = affected_rows - estimated_inserted
            
            inserted_count += estimated_inserted
            updated_count += estimated_updated
            
            logger.debug(f"批量处理 {len(batch)} 条数据，受影响行数: {affected_rows}")
            
        except Exception as e:
            logger.error(f"批量插入/更新失败（批次 {i//batch_size + 1}）: {e}", exc_info=True)
            raise
    
    return inserted_count, updated_count


async def batch_insert_ad_data(
    data_list: List[Dict[str, Any]],
    db: AsyncSession,
    batch_size: int = 1000,
    ignore_duplicates: bool = True
) -> int:
    """
    批量插入广告数据（仅插入，不更新）
    
    Args:
        data_list: 要插入的数据列表
        db: 数据库会话
        batch_size: 每批处理的数据量
        ignore_duplicates: 是否忽略重复键错误（使用 INSERT IGNORE）
    
    Returns:
        int: 成功插入的数量
    """
    if not data_list:
        return 0
    
    
    inserted_count = 0
    
    # 分批处理
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i + batch_size]
        
        try:
            if ignore_duplicates:
                # 使用 INSERT IGNORE（忽略重复键错误）
                stmt = insert(AdData).values(batch)
                stmt = stmt.prefix_with("IGNORE")
            else:
                # 普通插入（重复键会报错）
                stmt = insert(AdData).values(batch)
            
            result = await db.execute(stmt)
            inserted_count += result.rowcount
            
            logger.debug(f"批量插入 {len(batch)} 条数据，成功: {result.rowcount}")
            
        except Exception as e:
            logger.error(f"批量插入失败（批次 {i//batch_size + 1}）: {e}", exc_info=True)
            if not ignore_duplicates:
                raise
    
    return inserted_count


async def batch_update_ad_data(
    data_list: List[Dict[str, Any]],
    db: AsyncSession,
    batch_size: int = 1000
) -> int:
    """
    批量更新广告数据
    
    Args:
        data_list: 要更新的数据列表，必须包含 id 字段
        db: 数据库会话
        batch_size: 每批处理的数据量
    
    Returns:
        int: 成功更新的数量
    """
    if not data_list:
        return 0
    
    
    updated_count = 0
    
    # 分批处理
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i + batch_size]
        
        try:
            for item in batch:
                data_id = item.pop('id')  # 移除 id，用于 WHERE 条件
                stmt = update(AdData).where(AdData.id == data_id).values(**item)
                result = await db.execute(stmt)
                updated_count += result.rowcount
            
            logger.debug(f"批量更新 {len(batch)} 条数据")
            
        except Exception as e:
            logger.error(f"批量更新失败（批次 {i//batch_size + 1}）: {e}", exc_info=True)
            raise
    
    return updated_count

=======
"""
批量操作工具模块
提供高效的批量插入/更新功能，使用 MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.mysql import insert
from sqlalchemy import func, Float, case, update
from typing import List, Dict, Any
import logging
from app.core.utils import get_app_now_naive
from app.models.models import AdData

logger = logging.getLogger(__name__)


async def batch_upsert_ad_data(
    data_list: List[Dict[str, Any]],
    db: AsyncSession,
    batch_size: int = 1000
) -> tuple[int, int]:
    """
    批量插入/更新广告数据
    使用 MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE 语法
    
    Args:
        data_list: 要插入/更新的数据列表，每个元素是一个字典
        db: 数据库会话
        batch_size: 每批处理的数据量，默认 1000
    
    Returns:
        tuple[int, int]: (插入数量, 更新数量)
    
    Example:
        data_list = [
            {
                "date": datetime(2024, 1, 1),
                "product_id": 1,
                "request_count": 1000,
                "match_count": 800,
                ...
            },
            ...
        ]
        inserted, updated = await batch_upsert_ad_data(data_list, db)
    """
    if not data_list:
        return 0, 0
    
    inserted_count = 0
    updated_count = 0
    
    # 分批处理
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i + batch_size]
        
        try:
            # 使用 INSERT ... ON DUPLICATE KEY UPDATE
            # 如果 (date, product_id) 已存在，则更新；否则插入
            stmt = insert(AdData).values(batch)
            
            stmt = stmt.on_duplicate_key_update(
                request_count=stmt.inserted.request_count,
                match_count=stmt.inserted.match_count,
                display_count=stmt.inserted.display_count,
                click_count=stmt.inserted.click_count,
                # 更新比率字段（如果数据中包含，否则使用计算值）
                coverage_rate=case(
                    (stmt.inserted.coverage_rate.isnot(None), stmt.inserted.coverage_rate),
                    (stmt.inserted.request_count > 0, func.cast(stmt.inserted.match_count, Float) * 100.0 / func.cast(stmt.inserted.request_count, Float)),
                    else_=0.0
                ),
                display_rate=case(
                    (stmt.inserted.display_rate.isnot(None), stmt.inserted.display_rate),
                    (stmt.inserted.match_count > 0, func.cast(stmt.inserted.display_count, Float) * 100.0 / func.cast(stmt.inserted.match_count, Float)),
                    else_=0.0
                ),
                click_rate=case(
                    (stmt.inserted.click_rate.isnot(None), stmt.inserted.click_rate),
                    (stmt.inserted.display_count > 0, func.cast(stmt.inserted.click_count, Float) * 100.0 / func.cast(stmt.inserted.display_count, Float)),
                    else_=0.0
                ),
                ecpm_before_deduct=stmt.inserted.ecpm_before_deduct,
                ecpm_after_deduct=stmt.inserted.ecpm_after_deduct,
                revenue_before_deduct=stmt.inserted.revenue_before_deduct,
                revenue_after_deduct=stmt.inserted.revenue_after_deduct,
                updated_at=get_app_now_naive()  # 使用北京时间
            )
            
            result = await db.execute(stmt)
            
            # MySQL 返回受影响的行数
            # 注意：ON DUPLICATE KEY UPDATE 时，affected_rows = 1（插入）或 2（更新）
            # 但无法准确区分插入和更新，所以这里使用估算
            # 实际可以通过比较 before/after 的记录数来估算
            affected_rows = result.rowcount
            
            # 估算：假设一半是插入，一半是更新（不准确，但可以用于日志）
            # 更准确的方法是在执行前查询已存在的记录数
            estimated_inserted = affected_rows // 2
            estimated_updated = affected_rows - estimated_inserted
            
            inserted_count += estimated_inserted
            updated_count += estimated_updated
            
            logger.debug(f"批量处理 {len(batch)} 条数据，受影响行数: {affected_rows}")
            
        except Exception as e:
            logger.error(f"批量插入/更新失败（批次 {i//batch_size + 1}）: {e}", exc_info=True)
            raise
    
    return inserted_count, updated_count


async def batch_insert_ad_data(
    data_list: List[Dict[str, Any]],
    db: AsyncSession,
    batch_size: int = 1000,
    ignore_duplicates: bool = True
) -> int:
    """
    批量插入广告数据（仅插入，不更新）
    
    Args:
        data_list: 要插入的数据列表
        db: 数据库会话
        batch_size: 每批处理的数据量
        ignore_duplicates: 是否忽略重复键错误（使用 INSERT IGNORE）
    
    Returns:
        int: 成功插入的数量
    """
    if not data_list:
        return 0
    
    
    inserted_count = 0
    
    # 分批处理
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i + batch_size]
        
        try:
            if ignore_duplicates:
                # 使用 INSERT IGNORE（忽略重复键错误）
                stmt = insert(AdData).values(batch)
                stmt = stmt.prefix_with("IGNORE")
            else:
                # 普通插入（重复键会报错）
                stmt = insert(AdData).values(batch)
            
            result = await db.execute(stmt)
            inserted_count += result.rowcount
            
            logger.debug(f"批量插入 {len(batch)} 条数据，成功: {result.rowcount}")
            
        except Exception as e:
            logger.error(f"批量插入失败（批次 {i//batch_size + 1}）: {e}", exc_info=True)
            if not ignore_duplicates:
                raise
    
    return inserted_count


async def batch_update_ad_data(
    data_list: List[Dict[str, Any]],
    db: AsyncSession,
    batch_size: int = 1000
) -> int:
    """
    批量更新广告数据
    
    Args:
        data_list: 要更新的数据列表，必须包含 id 字段
        db: 数据库会话
        batch_size: 每批处理的数据量
    
    Returns:
        int: 成功更新的数量
    """
    if not data_list:
        return 0
    
    
    updated_count = 0
    
    # 分批处理
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i + batch_size]
        
        try:
            for item in batch:
                data_id = item.pop('id')  # 移除 id，用于 WHERE 条件
                stmt = update(AdData).where(AdData.id == data_id).values(**item)
                result = await db.execute(stmt)
                updated_count += result.rowcount
            
            logger.debug(f"批量更新 {len(batch)} 条数据")
            
        except Exception as e:
            logger.error(f"批量更新失败（批次 {i//batch_size + 1}）: {e}", exc_info=True)
            raise
    
    return updated_count

>>>>>>> 451fe37690182f08f5b8c5e7c77a028275228449
