"""
数据归档任务
定期归档旧数据到归档表，减少主表数据量，提升查询性能
"""
import logging
from calendar import monthrange
from datetime import datetime, timedelta
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.scheduler_module.task_names import ARCHIVE_DATA_TASK_NAME
from app.scheduler_module.task_utils import (
    log_task_start,
    log_task_result,
    log_task_error,
    format_result_summary,
)

logger = logging.getLogger(__name__)

# 任务执行结果存储（用于保存到last_error字段）
_task_results: dict[str, str] = {}


def get_task_result(task_name: str) -> str | None:
    """获取任务执行结果"""
    return _task_results.get(task_name)


def set_task_result(task_name: str, result: str) -> None:
    """设置任务执行结果"""
    _task_results[task_name] = result


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
            from app.core.utils import get_app_now_naive
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
            archive_date = datetime(target_year, target_month, 1)
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
                # 创建归档表
                # 注意：ARCHIVE 引擎只支持一个索引，所以不能使用 CREATE TABLE ... LIKE
                # 需要手动创建表结构，只保留主键索引
                logger.info("归档表不存在，正在创建...")
                # 创建归档表，结构与主表完全一致
                # 注意：country_code 字段类型与主表保持一致（varchar(2)）
                create_table_sql = text("""
                    CREATE TABLE `ad_data_archive` (
                        `id` int NOT NULL AUTO_INCREMENT COMMENT '广告数据ID',
                        `date` datetime NOT NULL COMMENT '数据日期',
                        `country_code` varchar(2) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '国家代码（ISO 3166-1 二字母代码）',
                        `product_id` int NOT NULL COMMENT '产品ID',
                        `request_count` int NOT NULL DEFAULT 0 COMMENT '请求数',
                        `match_count` int NOT NULL DEFAULT 0 COMMENT '匹配数',
                        `display_count` int NOT NULL DEFAULT 0 COMMENT '展示数',
                        `click_count` int NOT NULL DEFAULT 0 COMMENT '点击数',
                        `ecpm_before_deduct` float NOT NULL DEFAULT 0 COMMENT 'eCPM未减扣',
                        `ecpm_after_deduct` float NOT NULL DEFAULT 0 COMMENT 'eCPM已减扣',
                        `revenue_before_deduct` float NOT NULL DEFAULT 0 COMMENT '收益未减扣',
                        `revenue_after_deduct` float NOT NULL DEFAULT 0 COMMENT '收益已减扣',
                        `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
                        `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
                        PRIMARY KEY (`id`) USING BTREE,
                        UNIQUE INDEX `uq_ad_data_date_product_country`(`date` ASC, `product_id` ASC, `country_code` ASC) USING BTREE,
                        INDEX `idx_ad_data_date`(`date` ASC) USING BTREE,
                        INDEX `idx_ad_data_product`(`product_id` ASC) USING BTREE,
                        INDEX `idx_ad_data_date_product`(`date` ASC, `product_id` ASC) USING BTREE,
                        INDEX `idx_ad_data_country_code`(`country_code` ASC) USING BTREE,
                        CONSTRAINT `fk_ad_data_country_code` FOREIGN KEY (`country_code`) REFERENCES `countries` (`alpha_2_code`) ON DELETE SET NULL ON UPDATE CASCADE,
                        CONSTRAINT `fk_ad_data_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
                    ) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '广告数据归档表';
                """)
                await db.execute(create_table_sql)
                await db.commit()
                logger.info("归档表创建成功")
            
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
            
            # 步骤1：插入到归档表
            # 使用 INSERT IGNORE 避免重复归档（如果数据已经归档过，忽略错误继续执行）
            # 明确指定列名，包括 country_code 字段，排除生成列（coverage_rate, display_rate, click_rate）
            archive_sql = text("""
                INSERT IGNORE INTO `ad_data_archive` 
                (`id`, `date`, `country_code`, `product_id`, `request_count`, `match_count`, 
                 `display_count`, `click_count`, `ecpm_before_deduct`, `ecpm_after_deduct`, 
                 `revenue_before_deduct`, `revenue_after_deduct`, `created_at`, `updated_at`)
                SELECT `id`, `date`, `country_code`, `product_id`, `request_count`, `match_count`, 
                       `display_count`, `click_count`, `ecpm_before_deduct`, `ecpm_after_deduct`, 
                       `revenue_before_deduct`, `revenue_after_deduct`, `created_at`, `updated_at`
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
                DELETE FROM `ad_data` 
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

