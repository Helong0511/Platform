-- 将用户密码哈希字段扩展到正式基线定义，兼容 Argon2id 编码并修复 ORM/SQL 长度漂移。
ALTER TABLE `users`
  MODIFY COLUMN `hashed_password` VARCHAR(191) NOT NULL COMMENT '用户Hash密码';
