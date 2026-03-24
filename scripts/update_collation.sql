-- 统一更改数据库排序规则为 utf8mb4_0900_ai_ci
-- 生成时间: 2026-03-24

-- 1. 修改表级排序规则

-- ad_data
ALTER TABLE `ad_data` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- ad_data_archive
ALTER TABLE `ad_data_archive` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- admin_notification_configs
ALTER TABLE `admin_notification_configs` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- advertiser_tests
ALTER TABLE `advertiser_tests` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- advertisers
ALTER TABLE `advertisers` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- affiliate_tests
ALTER TABLE `affiliate_tests` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- clicks
ALTER TABLE `clicks` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- clicks_archive
ALTER TABLE `clicks_archive` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- client_notification_configs
ALTER TABLE `client_notification_configs` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- clients
ALTER TABLE `clients` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- conversion_deduction_configs (已使用 utf8mb4_0900_ai_ci，无需修改)

-- conversion_deduction_logs (已使用 utf8mb4_0900_ai_ci，无需修改)

-- countries
ALTER TABLE `countries` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- offer_caps
ALTER TABLE `offer_caps` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- offer_discounts
ALTER TABLE `offer_discounts` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- offer_publisher_assignments
ALTER TABLE `offer_publisher_assignments` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- offers
ALTER TABLE `offers` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- pending_postback_conversions
ALTER TABLE `pending_postback_conversions` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- postback_conversions
ALTER TABLE `postback_conversions` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- postback_forward_logs
ALTER TABLE `postback_forward_logs` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- postback_forward_queue
ALTER TABLE `postback_forward_queue` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- postback_ip_whitelist
ALTER TABLE `postback_ip_whitelist` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- postback_notifications
ALTER TABLE `postback_notifications` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- product_assignments
ALTER TABLE `product_assignments` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- product_notification_configs
ALTER TABLE `product_notification_configs` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- products
ALTER TABLE `products` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- publishers
ALTER TABLE `publishers` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- scheduled_tasks
ALTER TABLE `scheduled_tasks` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- short_links
ALTER TABLE `short_links` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- tb_search_data
ALTER TABLE `tb_search_data` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- third_party_report_logs (已使用 utf8mb4_0900_ai_ci，无需修改)

-- token_blacklist
ALTER TABLE `token_blacklist` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- user_audit_logs
ALTER TABLE `user_audit_logs` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- user_sessions
ALTER TABLE `user_sessions` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- users
ALTER TABLE `users` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- 2. 验证排序规则更改
SELECT table_name, table_collation 
FROM information_schema.tables 
WHERE table_schema = 'platform' 
ORDER BY table_name;

-- 3. 验证字段级排序规则
SELECT table_name, column_name, collation_name 
FROM information_schema.columns 
WHERE table_schema = 'platform' 
AND collation_name IS NOT NULL 
ORDER BY table_name, column_name;
