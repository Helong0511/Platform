"""MySQL 表级字符集/排序规则契约。

BASELINE_MYSQL_TABLE_OPTIONS 对应 sql/platform.sql 中显式声明且由 ORM 映射的表。
MIGRATION_MYSQL_TABLE_OPTIONS 对应独立增量 migration 创建、未纳入完整 SQL 基线的 ORM 表。
未显式声明的表继续继承数据库默认值，不在此猜测。变更 DDL 时必须同步更新契约并运行真实 MySQL drift 测试。
"""

BASELINE_MYSQL_TABLE_OPTIONS: dict[str, dict[str, str]] = {
    "ad_data": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "ad_data_day_baseline": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "ad_data_health_alert": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "ad_data_health_settings": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "admin_notification_configs": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "advertiser_tests": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "advertisers": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "affiliate_tests": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "clicks": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "client_notification_configs": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "clients": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "conversion_deduction_configs": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "conversion_deduction_logs": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "countries": {"charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"},
    "country_aliases": {"charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"},
    "offer_caps": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "offer_discounts": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "offer_publisher_assignments": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "offers": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "pending_postback_conversions": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "postback_conversions": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "postback_forward_logs": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "postback_forward_queue": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "postback_ip_whitelist": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "postback_notifications": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "product_assignments": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "product_notification_configs": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "products": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "publishers": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "scheduled_tasks": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "short_links": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "tb_search_data": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "third_party_report_logs": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "third_party_report_identity_locks": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "cloak_configs": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "token_blacklist": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "user_audit_logs": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "user_sessions": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
    "users": {"charset": "utf8mb4", "collation": "utf8mb4_0900_ai_ci"},
}


# 独立增量 migration 创建的账本表：保留各自 DDL 明确声明的排序规则。
MIGRATION_MYSQL_TABLE_OPTIONS: dict[str, dict[str, str]] = {
    "cap_reservations": {"charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"},
    "short_link_click_sync_batches": {"charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"},
}
