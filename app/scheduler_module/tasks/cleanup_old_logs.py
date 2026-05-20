"""
日志清理任务
定期清理或归档旧的用户操作日志，减少日志表数据量，提升查询性能
"""
import logging
from datetime import timedelta

from sqlalchemy import text, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.utils import get_app_now_naive
from app.models.models import UserAuditLog
from app.scheduler_module.task_names import CLEANUP_LOGS_TASK_NAME
from app.scheduler_module.task_result_store import get_task_result, set_task_result
from app.scheduler_module.task_utils import (
    log_task_start,
    log_task_result,
    log_task_error,
)

logger = logging.getLogger(__name__)


async def cleanup_old_audit_logs(
        days: int = 90,
        archive: bool = False,
        db: AsyncSession | None = None
) -> dict:
    """
    清理或归档指定天数之前的用户操作日志
    
    Args:
        days: 保留多少天的日志，默认 90 天（3个月）
        archive: 是否归档到归档表（True）还是直接删除（False），默认 False
        db: 数据库会话，如果为 None 则创建新会话
    
    Returns:
        dict: 清理结果统计
        {
            "deleted_count": 删除的日志条数,
            "archived_count": 归档的日志条数（如果启用归档）,
            "cutoff_date": 清理日期阈值,
            "message": 结果消息
        }
    
    Note:
        - 默认直接删除旧日志（不归档），因为日志数据通常不需要长期保留
        - 如果需要保留历史日志，可以设置 archive=True 并创建归档表
        - 建议保留 90-180 天的日志，超过此期限的日志通常不再需要
    """
    TASK_NAME = CLEANUP_LOGS_TASK_NAME

    # 计算清理日期阈值（使用应用时区）
    cutoff_date = get_app_now_naive() - timedelta(days=days)
    cutoff_date_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')

    # 记录任务开始
    action = "归档" if archive else "清理"
    log_task_start(TASK_NAME, f"{action} {days} 天前的日志（日期 < {cutoff_date_str}）")

    # 如果提供了数据库会话，使用它；否则创建新会话
    use_external_db = db is not None
    if not use_external_db:
        db = AsyncSessionLocal()

    try:
        # 统计要清理的日志数量
        count_sql = text("""
                         SELECT COUNT(*) as count
                         FROM `user_audit_logs`
                         WHERE `created_at` < :cutoff_date
                         """)
        count_result = await db.execute(count_sql, {"cutoff_date": cutoff_date})
        total_count = count_result.scalar() or 0

        if total_count == 0:
            logger.info("没有需要清理的日志")
            result_message = f"执行成功: 没有需要清理的日志（日期 < {cutoff_date_str}）"
            log_task_result(TASK_NAME, result_message, level="info")
            set_task_result(TASK_NAME, result_message)
            return {
                "deleted_count": 0,
                "archived_count": 0,
                "cutoff_date": cutoff_date_str,
                "message": "没有需要清理的日志"
            }

        logger.info(f"发现 {total_count} 条需要清理的日志（日期 < {cutoff_date_str}）")

        archived_count = 0
        deleted_count = 0

        if archive:
            # 归档模式：先归档到归档表，再删除
            # 检查归档表是否存在
            check_table_sql = text("""
                                   SELECT COUNT(*) as count
                                   FROM information_schema.tables
                                   WHERE table_schema = DATABASE()
                                     AND table_name = 'user_audit_logs_archive'
                                   """)
            result = await db.execute(check_table_sql)
            table_exists = result.scalar() > 0

            if not table_exists:
                # 创建归档表（结构与主表一致）
                logger.info("归档表不存在，正在创建...")
                create_table_sql = text("""
                                        CREATE TABLE `user_audit_logs_archive`
                                        (
                                            `id`             int                                                          NOT NULL AUTO_INCREMENT COMMENT '日志ID',
                                            `user_id`        int NULL COMMENT '用户ID',
                                            `username`       varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '用户名',
                                            `action_type`    varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '操作类型',
                                            `resource_type`  varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '资源类型',
                                            `resource_id`    int NULL COMMENT '资源ID',
                                            `resource_name`  varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '资源名称',
                                            `ip_address`     varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'IP地址',
                                            `user_agent`     varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '用户代理',
                                            `request_method` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'HTTP请求方法',
                                            `request_path`   varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '请求路径',
                                            `request_params` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '请求参数',
                                            `status_code`    int NULL COMMENT 'HTTP状态码',
                                            `success`        tinyint(1) NOT NULL DEFAULT 1 COMMENT '操作是否成功',
                                            `error_message`  text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '错误信息',
                                            `details`        text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '详细信息',
                                            `created_at`     datetime                                                     NOT NULL COMMENT '创建时间',
                                            PRIMARY KEY (`id`) USING BTREE,
                                            INDEX            `idx_archive_created_at`(`created_at` ASC) USING BTREE,
                                            INDEX            `idx_archive_user_id`(`user_id` ASC) USING BTREE,
                                            INDEX            `idx_archive_action_type`(`action_type` ASC) USING BTREE
                                        ) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci ROW_FORMAT = DYNAMIC COMMENT = '用户操作日志归档表';
                                        """)
                await db.execute(create_table_sql)
                await db.commit()
                logger.info("归档表创建成功")

            # 归档数据
            archive_sql = text("""
                               INSERT
                               IGNORE INTO `user_audit_logs_archive` 
                (`id`, `user_id`, `username`, `action_type`, `resource_type`, `resource_id`, 
                 `resource_name`, `ip_address`, `user_agent`, `request_method`, `request_path`, 
                 `request_params`, `status_code`, `success`, `error_message`, `details`, `created_at`)
                               SELECT `id`,
                                      `user_id`,
                                      `username`,
                                      `action_type`,
                                      `resource_type`,
                                      `resource_id`,
                                      `resource_name`,
                                      `ip_address`,
                                      `user_agent`,
                                      `request_method`,
                                      `request_path`,
                                      `request_params`,
                                      `status_code`,
                                      `success`,
                                      `error_message`,
                                      `details`,
                                      `created_at`
                               FROM `user_audit_logs`
                               WHERE `created_at` < :cutoff_date
                               """)

            archive_result = await db.execute(archive_sql, {"cutoff_date": cutoff_date})
            archived_count = archive_result.rowcount
            logger.info(f"已归档 {archived_count} 条日志到归档表")

        # 删除旧日志
        delete_stmt = delete(UserAuditLog).where(UserAuditLog.created_at < cutoff_date)
        delete_result = await db.execute(delete_stmt)
        deleted_count = delete_result.rowcount

        # 提交事务
        await db.commit()

        # 格式化结果摘要
        if archive:
            result_summary = f"归档 {archived_count} 条，删除 {deleted_count} 条日志"
        else:
            result_summary = f"删除 {deleted_count} 条日志"

        # 记录任务结果
        log_task_result(TASK_NAME, result_summary, level="info")

        # 保存执行结果
        result_message = f"执行成功: {result_summary}（日期 < {cutoff_date_str}）"
        set_task_result(TASK_NAME, result_message)

        logger.info(f"日志清理完成：{result_summary}")

        return {
            "deleted_count": deleted_count,
            "archived_count": archived_count if archive else 0,
            "cutoff_date": cutoff_date_str,
            "message": result_summary
        }

    except Exception as e:
        await db.rollback()
        error_msg = str(e)
        log_task_error(TASK_NAME, error_msg, exc_info=True)
        set_task_result(TASK_NAME, f"执行失败: {error_msg}")
        raise
    finally:
        # 如果使用的是外部会话，不关闭；否则关闭
        if not use_external_db:
            await db.close()
