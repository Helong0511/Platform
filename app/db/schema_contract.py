"""正式 SQL 基线中显式声明的 MySQL 表级字符集/排序规则契约。

本清单只覆盖 sql/platform.sql 中存在且由 ORM 映射的表。
未显式声明的表继续继承数据库默认值；迁移创建但不在完整基线中的表不在此猜测。
更新 sql/platform.sql 的表级选项时，必须同步更新本清单并运行真实 MySQL drift 测试。
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
