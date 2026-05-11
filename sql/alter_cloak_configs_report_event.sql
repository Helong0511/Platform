-- 已有库升级：斗篷配置增加「上报事件」「金额」「货币」
-- 执行一次即可；若某列已存在，请整段注释掉后重试。

ALTER TABLE `cloak_configs`
  ADD COLUMN `report_event` varchar(64) NOT NULL DEFAULT 'ViewContent' COMMENT '斗篷点击与测上报的CAPI event_name' AFTER `backup_access_token`,
  ADD COLUMN `report_value` double NULL DEFAULT NULL COMMENT '购物类事件金额' AFTER `report_event`,
  ADD COLUMN `report_currency` varchar(10) NULL DEFAULT 'USD' COMMENT '购物类事件货币' AFTER `report_value`;
