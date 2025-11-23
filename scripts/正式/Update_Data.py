import datetime
import os
import mysql.connector as mysql

config = {
    "host": "43.156.101.243",
    "port": 3306,
    "user": "remote",
    "password": "kb7$rL3d8!tQ",
    "database": "platform",
    "charset": "utf8mb4",
    "raise_on_warnings": True
}

# 连接到 MySQL 数据库
conn = mysql.connect(**config)
cursor = conn.cursor()

sql_file = r"E:\data\Platform\scripts\正式\append_data_test.sql"

if os.path.exists(sql_file):
    os.remove(sql_file)

hand = open(sql_file, "w", encoding="utf-8")

need_exp = [
    {
        "table_name": "`users`",
        "field_name": "`id`, `username`, `hashed_password`, `role`, `is_active`",
        "order": "`id`",
        "note": "-- 添加用户数据\n"
    },
    {
        "table_name": "`clients`",
        "field_name": "`id`, `user_id`, `company_name`, `key`, `is_active`, `api_enabled`, `password_change_enabled`",
        "order": "`id`",
        "note": "-- 添加客户数据\n"
    },
    {
        "table_name": "`products`",
        "field_name": "`id`, `client_id`, `name`, `ecpm_deduct_ratio`, `revenue_deduct_ratio`, `is_active`",
        "order": "`id`",
        "note": "-- 添加产品数据\n"
    },
    {
        "table_name": "`product_assignments`",
        "field_name": "`product_id`, `client_id`, `start_date`, `end_date`",
        "order": "`product_id`",
        "note": "-- 添加产品历史分配数据\n"
    },
    {
        "table_name": "`ad_data`",
        "field_name": "`date`, `product_id`, `request_count`, `match_count`, `display_count`, `click_count`, `ecpm_before_deduct`, `ecpm_after_deduct`, `revenue_before_deduct`, `revenue_after_deduct`",
        "order": "`date`, `product_id`",
        "note": "-- 添加广告数据\n"
    },
    {
        "table_name": "`scheduled_tasks`",
        "field_name": "`task_name`, `cron_expression`, `description`, `function_path`, `is_active`",
        "order": "`id`",
        "note": "-- 添加定时任务数据\n"
    },
]

a = 0
for exp in need_exp:
    a = a + 1
    table_name = exp.get("table_name", "")
    field_name = exp.get("field_name", "")
    order = exp.get("order", "")
    note = exp.get("note", "")

    if a > 1:
        hand.write("\n")

    hand.write(note)

    if order:
        sql = f"SELECT {field_name} FROM {table_name} ORDER BY {order} ASC ;"
    else:
        sql = f"SELECT {field_name} FROM {table_name} ;"

    cursor.execute(sql)
    info = cursor.fetchall()
    if info:
        if len(info) > 0:
            hand.write(f"INSERT INTO {table_name} ({field_name}) VALUES \n")
        i = 0
        for item in info:
            i = i + 1

            wr = "("
            for b in range(len(item)):

                if item[b] is None:
                    wr = wr + "NULL"
                elif isinstance(item[b], int):
                    wr = wr + str(item[b])
                elif isinstance(item[b], float):
                    wr = wr + f"{item[b]:.2f}"
                elif isinstance(item[b], str):
                    wr = wr + "'" + str(item[b]) + "'"
                elif isinstance(item[b], datetime.date):
                    wr = wr + "'" + str(item[b]) + "'"
                else:
                    print(type(item[b]))

                if b == len(item) - 1:
                    wr = wr + ")"
                else:
                    wr = wr + ","

            hand.write(wr)

            if i == len(info):
                hand.write(";\n")
            else:
                hand.write(",\n")

    if table_name == "`scheduled_tasks`":
        hand.write("\nINSERT INTO `scheduled_tasks` (`task_name`, `cron_expression`, `description`, `function_path`, `is_active`) VALUES \n")
        hand.write("('数据归档任务', '0 1 1 * *', '归档6个月前的数据','app.scheduler_module.tasks.archive_old_data.archive_old_ad_data', 1),\n")
        hand.write("('清理旧日志', '0 2 1 * *','清理90天前的用户操作日志，减少日志表数据量','app.scheduler_module.tasks.cleanup_old_logs.cleanup_old_audit_logs', 1),\n")
        hand.write("('清理过期会话和黑名单', '0 2 * * *','清理过期超过30天的会话记录和黑名单记录，标记超过7天未活动的会话为非活跃','app.scheduler_module.tasks.cleanup_expired_sessions.cleanup_expired_sessions', 1),\n")
        hand.write("('TQT API获取数据', '*/10 * * * *', '每隔10分钟执行一次，从TQT API获取广告数据并导入到数据库','app.scheduler_module.tasks.tqt_task.tqt_api_task', 1),\n")
        hand.write("('Skymobi API获取数据', '*/10 * * * *', '每隔10分钟执行一次，从Skymobi API获取广告数据','app.scheduler_module.tasks.skymobi_task.skymobi_api_task', 1);\n")

    if table_name == "`ad_data`":
        hand.write("\n-- 更新广告数据统计字段（避免除零错误）\n")
        hand.write("UPDATE `ad_data` SET `coverage_rate` = CASE WHEN `request_count` > 0 THEN (`match_count` / `request_count` * 100) ELSE 0 END;\n")
        hand.write("UPDATE `ad_data` SET `display_rate` = CASE WHEN `match_count` > 0 THEN (`display_count` / `match_count` * 100) ELSE 0 END;\n")
        hand.write("UPDATE `ad_data` SET `click_rate` = CASE WHEN `display_count` > 0 THEN (`click_count` / `display_count` * 100) ELSE 0 END;\n")

# 关闭文件
hand.close()

# 关闭数据库连接
cursor.close()
conn.close()

print(f"数据已成功导出到{sql_file}")
