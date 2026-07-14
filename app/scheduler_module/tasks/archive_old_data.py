"""
广告数据归档定时任务。

功能说明：
- 将早于阈值的 ad_data 行迁移至归档表（或按月分表），缩减主表体积
- 提升列表与报表查询性能

在系统中的位置：
- 由调度器按 ARCHIVE_DATA_TASK_NAME 触发

注意事项：
1. 归档与业务查询的时间边界须与报表默认范围对齐
2. 失败时保留主表数据，事务回滚后 set_task_result 记录原因
"""
import logging
from calendar import monthrange
from datetime import datetime, date

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.scheduler_module.task_names import ARCHIVE_DATA_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.scheduler_module.task_utils import (
    log_task_start,
    log_task_result,
    log_task_error,
    format_result_summary,
)

logger = logging.getLogger(__name__)


async def archive_old_ad_data(months: int = 6) -> dict:
    """
    归档指定月数之前的数据
    
    Args:
        months: 归档多少个月之前的数据，默认 6 个月
    
    Returns:
        dict: 归档结果统计
        {
            "archived_count": 归档的数据条数,
            "deleted_count": 从主表删除的数据条数,
            "archive_date": 归档日期阈值
        }
    
    Note:
        - 先插入到归档表，再删除主表数据
        - 归档表使用 InnoDB 引擎（支持外键和索引）
        - 如果归档表不存在，会自动创建
        - 归档表结构与主表完全一致，包括 country_code 字段
    """
    TASK_NAME = ARCHIVE_DATA_TASK_NAME

    # 记录任务开始
    log_task_start(TASK_NAME, f"归档 {months} 个月前的数据")

    async with AsyncSessionLocal() as db:
        try:
            # 计算归档日期阈值（精确计算月份，考虑不同月份的天数差异，使用应用时区）
            today = get_app_now_naive()
            target_year = today.year
            target_month = today.month - months
            # 处理跨年情况
            while target_month <= 0:
                target_month += 12
                target_year -= 1
            # 获取目标月份的最后一天，确保日期有效
            _, last_day = monthrange(target_year, target_month)
            # 使用目标月份的第一天作为归档阈值（小于这个日期的数据将被归档）
            archive_date = date(target_year, target_month, 1)
            archive_date_str = archive_date.strftime('%Y-%m-%d')

            # 检查归档表是否存在
            check_table_sql = text("""
                                   SELECT COUNT(*) as count
                                   FROM information_schema.tables
                                   WHERE table_schema = DATABASE()
                                     AND table_name = 'ad_data_archive'
                                   """)
            result = await db.execute(check_table_sql)
            table_exists = result.scalar() > 0

            if not table_exists:
                logger.error(
                    "归档表 ad_data_archive 不存在，请先执行 sql/platform.sql 或 migrate_schema_20260711.sql 创建"
                )
                raise RuntimeError("ad_data_archive 表不存在")
            else:
                # 表已存在，检查是否需要修复约束（如果之前创建失败导致约束名称冲突）
                logger.debug("归档表已存在，检查约束...")
                try:
                    # 检查是否有冲突的约束名称
                    check_constraints_sql = text("""
                        SELECT CONSTRAINT_NAME 
                        FROM information_schema.TABLE_CONSTRAINTS 
                        WHERE TABLE_SCHEMA = DATABASE() 
                          AND TABLE_NAME = 'ad_data_archive'
                          AND CONSTRAINT_TYPE = 'FOREIGN KEY'
                          AND (CONSTRAINT_NAME = 'fk_ad_data_product' 
                               OR CONSTRAINT_NAME = 'fk_ad_data_country_code')
                    """)
                    constraints_result = await db.execute(check_constraints_sql)
                    conflicting_constraints = [row[0] for row in constraints_result.all()]

                    if conflicting_constraints:
                        logger.warning(f"发现冲突的外键约束: {conflicting_constraints}，尝试修复...")
                        # 删除冲突的约束
                        for constraint_name in conflicting_constraints:
                            try:
                                drop_sql = text(f"ALTER TABLE `ad_data_archive` DROP FOREIGN KEY `{constraint_name}`")
                                await db.execute(drop_sql)
                                logger.info(f"已删除冲突的外键约束: {constraint_name}")
                            except Exception as e:
                                logger.warning(f"删除约束失败: {constraint_name}, {e}")

                        # 重新添加正确命名的约束
                        if 'fk_ad_data_product' in conflicting_constraints:
                            add_fk_product_sql = text("""
                                ALTER TABLE `ad_data_archive` 
                                ADD CONSTRAINT `fk_ad_data_archive_product` 
                                FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) 
                                ON DELETE CASCADE ON UPDATE RESTRICT
                            """)
                            await db.execute(add_fk_product_sql)
                            logger.info("已添加正确命名的外键约束: fk_ad_data_archive_product")

                        if 'fk_ad_data_country_code' in conflicting_constraints:
                            add_fk_country_sql = text("""
                                ALTER TABLE `ad_data_archive` 
                                ADD CONSTRAINT `fk_ad_data_archive_country_code` 
                                FOREIGN KEY (`country_code`) REFERENCES `countries` (`alpha_2_code`) 
                                ON DELETE SET NULL ON UPDATE CASCADE
                            """)
                            await db.execute(add_fk_country_sql)
                            logger.info("已添加正确命名的外键约束: fk_ad_data_archive_country_code")

                        await db.commit()
                        logger.info("约束修复完成")
                except Exception as e:
                    logger.debug(f"检查/修复约束时出错: {e}")
                    await db.rollback()

            # 统计要归档的数据量
            count_sql = text("""
                             SELECT COUNT(*) as count
                             FROM `ad_data`
                             WHERE `date` < :archive_date
                             """)
            count_result = await db.execute(count_sql, {"archive_date": archive_date})
            total_count = count_result.scalar() or 0

            if total_count == 0:
                logger.info("没有需要归档的数据")
                # 记录任务结果
                result_message = "执行成功: 没有需要归档的数据"
                log_task_result(TASK_NAME, "没有需要归档的数据", level="warning")
                set_task_result(TASK_NAME, result_message)
                return {
                    "archived_count": 0,
                    "deleted_count": 0,
                    "archive_date": archive_date_str,
                    "message": "没有需要归档的数据"
                }

            logger.info(f"发现 {total_count} 条需要归档的数据")

            # 步骤1：插入到归档表（字段与主表 ad_data 对齐）
            archive_sql = text("""
                               INSERT IGNORE INTO `ad_data_archive`
                (`id`, `date`, `country_code`, `product_id`, `ad_unit`,
                 `request_count`, `match_count`, `coverage_rate`, `display_count`, `display_rate`,
                 `click_count`, `click_rate`, `viewability_rate`, `cpc`, `pageviews`,
                 `ecpm_before_deduct`, `ecpm_after_deduct`, `revenue_before_deduct`, `revenue_after_deduct`,
                 `data_source`, `upstream_account`, `report_type`, `created_at`, `updated_at`, `is_deducted`)
                               SELECT `id`, `date`, `country_code`, `product_id`, `ad_unit`,
                                      `request_count`, `match_count`, `coverage_rate`, `display_count`, `display_rate`,
                                      `click_count`, `click_rate`, `viewability_rate`, `cpc`, `pageviews`,
                                      `ecpm_before_deduct`, `ecpm_after_deduct`, `revenue_before_deduct`, `revenue_after_deduct`,
                                      `data_source`, `upstream_account`, `report_type`, `created_at`, `updated_at`, `is_deducted`
                               FROM `ad_data`
                               WHERE `date` < :archive_date
                               """)

            archive_result = await db.execute(archive_sql, {"archive_date": archive_date})
            archived_count = archive_result.rowcount

            # 如果归档数量为0，可能是数据已经归档过，记录警告但不报错
            if archived_count == 0 and total_count > 0:
                logger.warning(f"没有新数据被归档，可能数据已经归档过（日期 < {archive_date_str}）")

            logger.info(f"已归档 {archived_count} 条数据到归档表")

            # 步骤2：删除主表数据
            delete_sql = text("""
                              DELETE
                              FROM `ad_data`
                              WHERE `date` < :archive_date
                              """)

            delete_result = await db.execute(delete_sql, {"archive_date": archive_date})
            deleted_count = delete_result.rowcount

            # 提交事务
            await db.commit()

            # 格式化结果摘要
            result_summary = format_result_summary(
                archived=archived_count,
                deleted=deleted_count
            )

            # 记录任务结果
            log_task_result(TASK_NAME, result_summary, level="warning")

            # 保存执行结果
            result_message = f"执行成功: 归档 {archived_count} 条数据, 删除 {deleted_count} 条数据"
            set_task_result(TASK_NAME, result_message)

            logger.info(f"归档完成：归档 {archived_count} 条，删除 {deleted_count} 条")

            return {
                "archived_count": archived_count,
                "deleted_count": deleted_count,
                "archive_date": archive_date_str,
                "message": f"成功归档 {archived_count} 条数据"
            }

        except Exception as e:
            await db.rollback()
            error_msg = str(e)
            log_task_error(TASK_NAME, error_msg, exc_info=True)
            set_task_result(TASK_NAME, f"执行失败: {error_msg}")
            raise

# 注意：archive_old_sessions 函数已被废弃
# 请使用 app.scheduler_module.tasks.cleanup_expired_sessions.cleanup_expired_sessions
# 该函数功能更完整，包含标记非活跃会话的功能
