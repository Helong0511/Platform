-- 点击时保存客户归属快照，防止 Publisher.client_id 后续变更导致历史转化归错客户。
-- 不创建 clients 外键：客户记录删除/迁移不得级联清空已发生点击的历史归属。
ALTER TABLE clicks
    ADD COLUMN client_id INT NULL DEFAULT NULL
    COMMENT '点击时客户ID快照（不设外键，保留历史归属）'
    AFTER publisher_id;
