-- 验证 CPL 系统表是否创建成功
-- 执行此脚本可以检查所有表是否存在

USE `platform`;

-- 检查新表是否存在
SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 表已存在'
        ELSE '❌ 表不存在'
    END AS status,
    'advertisers' AS table_name
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'platform' AND TABLE_NAME = 'advertisers'

UNION ALL

SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 表已存在'
        ELSE '❌ 表不存在'
    END AS status,
    'publishers' AS table_name
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'platform' AND TABLE_NAME = 'publishers'

UNION ALL

SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 表已存在'
        ELSE '❌ 表不存在'
    END AS status,
    'offers' AS table_name
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'platform' AND TABLE_NAME = 'offers'

UNION ALL

SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 表已存在'
        ELSE '❌ 表不存在'
    END AS status,
    'offer_publisher_assignments' AS table_name
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'platform' AND TABLE_NAME = 'offer_publisher_assignments'

UNION ALL

SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 表已存在'
        ELSE '❌ 表不存在'
    END AS status,
    'clicks' AS table_name
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'platform' AND TABLE_NAME = 'clicks'

UNION ALL

SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 表已存在'
        ELSE '❌ 表不存在'
    END AS status,
    'offer_caps' AS table_name
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'platform' AND TABLE_NAME = 'offer_caps'

UNION ALL

SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 表已存在'
        ELSE '❌ 表不存在'
    END AS status,
    'offer_discounts' AS table_name
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'platform' AND TABLE_NAME = 'offer_discounts'

UNION ALL

SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 表已存在'
        ELSE '❌ 表不存在'
    END AS status,
    'advertiser_tests' AS table_name
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'platform' AND TABLE_NAME = 'advertiser_tests'

UNION ALL

SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 表已存在'
        ELSE '❌ 表不存在'
    END AS status,
    'affiliate_tests' AS table_name
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'platform' AND TABLE_NAME = 'affiliate_tests';

-- 检查 postback_conversions 表的新字段
SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 字段已存在'
        ELSE '❌ 字段不存在'
    END AS status,
    'click_id' AS column_name
FROM information_schema.COLUMNS 
WHERE TABLE_SCHEMA = 'platform' 
  AND TABLE_NAME = 'postback_conversions' 
  AND COLUMN_NAME = 'click_id'

UNION ALL

SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 字段已存在'
        ELSE '❌ 字段不存在'
    END AS status,
    'click_time' AS column_name
FROM information_schema.COLUMNS 
WHERE TABLE_SCHEMA = 'platform' 
  AND TABLE_NAME = 'postback_conversions' 
  AND COLUMN_NAME = 'click_time'

UNION ALL

SELECT 
    CASE 
        WHEN COUNT(*) > 0 THEN '✅ 字段已存在'
        ELSE '❌ 字段不存在'
    END AS status,
    'conversion_status' AS column_name
FROM information_schema.COLUMNS 
WHERE TABLE_SCHEMA = 'platform' 
  AND TABLE_NAME = 'postback_conversions' 
  AND COLUMN_NAME = 'conversion_status';

