"""
点击记录归档任务
定期归档旧点击记录到归档表，减少主表数据量，提升查询性能
"""
import logging
from datetime import timedelta

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.scheduler_module.task_utils import (
    log_task_start,
    log_task_result,
    log_task_error,
    format_result_summary,
)

logger = logging.getLogger(__name__)

# 任务执行结果存储
_task_results: dict[str, str] = {}


def get_task_result(task_name: str) -> str | None:
    """获取任务执行结果"""
    return _task_results.get(task_name)


def set_task_result(task_name: str, result: str) -> None:
    """设置任务执行结果"""
    _task_results[task_name] = result


async def archive_old_clicks(days: int = 90) -> dict:
    """
    归档指定天数之前的点击记录
    
    Args:
        days: 归档多少天之前的数据，默认 90 天（3个月）
    
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
        - 归档表结构与主表完全一致
    """
    TASK_NAME = "点击记录归档"

    # 记录任务开始
    log_task_start(TASK_NAME, f"归档 {days} 天前的点击记录")

    async with AsyncSessionLocal() as db:
        try:
            # 计算归档日期阈值（使用应用时区）
            now = get_app_now_naive()
            archive_date = now - timedelta(days=days)
            archive_date_str = archive_date.strftime('%Y-%m-%d %H:%M:%S')

            # 检查归档表是否存在
            check_table_sql = text("""
                                   SELECT COUNT(*) as count
                                   FROM information_schema.tables
                                   WHERE table_schema = DATABASE()
                                     AND table_name = 'clicks_archive'
                                   """)
            result = await db.execute(check_table_sql)
            table_exists = result.scalar() > 0

            if not table_exists:
                # 创建归档表
                logger.info("归档表不存在，正在创建...")
                create_table_sql = text("""
                                        CREATE TABLE `clicks_archive`
                                        (
                                            `id` int NOT NULL AUTO_INCREMENT COMMENT '点击记录ID',
                                            `click_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '点击ID（系统生成，唯一标识）',
                                            `offer_id` int NULL DEFAULT NULL COMMENT '关联的Offer ID',
                                            `publisher_id` int NULL DEFAULT NULL COMMENT '关联的渠道ID',
                                            `advertiser_id` int NULL DEFAULT NULL COMMENT '关联的广告主ID',
                                            `short_link_id` int NULL DEFAULT NULL COMMENT '关联的短链接ID',
                                            `click_time` datetime NOT NULL COMMENT '点击时间',
                                            `ip` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '点击IP地址',
                                            `device` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备信息',
                                            `country` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '国家',
                                            `user_agent` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'User Agent',
                                            `referer` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '来源页面',
                                            `conversion_id` int NULL DEFAULT NULL COMMENT '关联的转化ID（如果已转化）',
                                            `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                                            `os` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '操作系统名称',
                                            `os_version` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '操作系统版本',
                                            `browser` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '浏览器名称',
                                            `browser_version` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '浏览器版本',
                                            `accept_language` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '接受的语言',
                                            `accept_encoding` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '接受的编码',
                                            `is_bot` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否为机器人/爬虫',
                                            `device_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备类型（mobile/tablet/desktop）',
                                            `device_brand` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备品牌',
                                            `device_model` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '设备型号',
                                            `url_params` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'URL参数（JSON格式）',
                                            `all_headers` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '所有请求头（JSON格式）',
                                            PRIMARY KEY (`id`) USING BTREE,
                                            INDEX `idx_click_id`(`click_id` ASC) USING BTREE,
                                            INDEX `idx_offer_id`(`offer_id` ASC) USING BTREE,
                                            INDEX `idx_publisher_id`(`publisher_id` ASC) USING BTREE,
                                            INDEX `idx_advertiser_id`(`advertiser_id` ASC) USING BTREE,
                                            INDEX `idx_short_link_id`(`short_link_id` ASC) USING BTREE,
                                            INDEX `idx_click_time`(`click_time` ASC) USING BTREE,
                                            INDEX `idx_conversion_id`(`conversion_id` ASC) USING BTREE,
                                            INDEX `idx_clicks_time_offer_publisher`(`click_time` ASC, `offer_id` ASC, `publisher_id` ASC) USING BTREE
                                        ) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '点击记录归档表';
                                        """)
                await db.execute(create_table_sql)
                await db.commit()
                logger.info("归档表创建成功")

            # 统计要归档的数据量
            count_sql = text("""
                             SELECT COUNT(*) as count
                             FROM `clicks`
                             WHERE `click_time` < :archive_date
                             """)
            count_result = await db.execute(count_sql, {"archive_date": archive_date})
            total_count = count_result.scalar() or 0

            if total_count == 0:
                logger.info("没有需要归档的数据")
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
            # 使用 INSERT IGNORE 避免重复归档
            archive_sql = text("""
                               INSERT IGNORE INTO `clicks_archive` 
                               (`id`, `click_id`, `offer_id`, `publisher_id`, `advertiser_id`, 
                                `short_link_id`, `click_time`, `ip`, `device`, `country`, 
                                `user_agent`, `referer`, `conversion_id`, `created_at`,
                                `os`, `os_version`, `browser`, `browser_version`, 
                                `accept_language`, `accept_encoding`, `is_bot`,
                                `device_type`, `device_brand`, `device_model`, 
                                `url_params`, `all_headers`)
                               SELECT `id`, `click_id`, `offer_id`, `publisher_id`, `advertiser_id`, 
                                      `short_link_id`, `click_time`, `ip`, `device`, `country`, 
                                      `user_agent`, `referer`, `conversion_id`, `created_at`,
                                      `os`, `os_version`, `browser`, `browser_version`, 
                                      `accept_language`, `accept_encoding`, `is_bot`,
                                      `device_type`, `device_brand`, `device_model`, 
                                      `url_params`, `all_headers`
                               FROM `clicks`
                               WHERE `click_time` < :archive_date
                               """)

            archive_result = await db.execute(archive_sql, {"archive_date": archive_date})
            archived_count = archive_result.rowcount

            if archived_count == 0 and total_count > 0:
                logger.warning(f"没有新数据被归档，可能数据已经归档过（日期 < {archive_date_str}）")

            logger.info(f"已归档 {archived_count} 条数据到归档表")

            # 步骤2：删除主表数据
            delete_sql = text("""
                              DELETE
                              FROM `clicks`
                              WHERE `click_time` < :archive_date
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
