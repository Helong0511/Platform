-- 为 publishers 表添加 client_id 字段
-- 用于关联渠道到客户

ALTER TABLE `publishers`
ADD COLUMN `client_id` INT NULL COMMENT '关联的客户ID' AFTER `active_advertiser_count`,
ADD INDEX `idx_client_id` (`client_id`),
ADD CONSTRAINT `fk_publishers_client_id` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE CASCADE;

