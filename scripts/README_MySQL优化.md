# MySQL 配置自动优化 - 快速指南

## 快速开始

### 1. 检查当前配置（推荐先执行）

```bash
cd /data/Platform
sudo python3 scripts/optimize_mysql_config.py
```

### 2. 应用优化配置

```bash
sudo python3 scripts/optimize_mysql_config.py --apply
```

### 3. 重启 MySQL 使配置生效

```bash
sudo systemctl restart mysql
sudo systemctl status mysql
```

## 针对 2核4GB 服务器的优化

脚本会自动检测硬件并应用以下优化：

- **InnoDB Buffer Pool**: 512MB-768MB（根据实际内存调整）
- **Max Connections**: 100-150
- **InnoDB Log File Size**: 128MB-256MB
- **其他性能优化参数**

## 回滚配置

如果出现问题，可以回滚：

```bash
# 查看备份文件
ls -lh /etc/mysql/mysql.conf.d/mysqld.cnf.backup_*

# 回滚到指定备份
sudo python3 scripts/optimize_mysql_config.py --rollback /etc/mysql/mysql.conf.d/mysqld.cnf.backup_20240101_120000
```

## 验证配置

```bash
# 查看 Buffer Pool 大小
mysql -u root -p -e "SHOW VARIABLES LIKE 'innodb_buffer_pool_size';"

# 查看最大连接数
mysql -u root -p -e "SHOW VARIABLES LIKE 'max_connections';"

# 查看内存使用
free -h
```

## 注意事项

1. ⚠️ **必须使用 sudo 运行**
2. ⚠️ **应用配置后必须重启 MySQL**
3. ⚠️ **建议在低峰期执行**
4. ⚠️ **保留备份文件以便回滚**

详细说明请查看: `scripts/MySQL优化说明.md`

