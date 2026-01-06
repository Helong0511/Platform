# MySQL 配置自动优化脚本使用说明

## 脚本功能

`optimize_mysql_config.py` 是一个自动检测硬件信息并优化 MySQL 8.0 配置的脚本，适用于 Ubuntu 22.04.5。

### 主要功能

1. **自动检测硬件信息**
   - CPU 核心数
   - 内存大小（总内存、已用内存、可用内存）
   - 磁盘空间

2. **智能计算最优配置**
   - 根据硬件资源自动计算 MySQL 配置参数
   - 针对 2核4GB 服务器优化
   - 平衡性能和资源占用

3. **安全备份和回滚**
   - 自动备份原配置文件
   - 支持一键回滚

4. **配置对比**
   - 显示当前配置与优化配置的对比
   - 高亮显示需要修改的配置项

## 使用方法

### 1. 检查配置（不应用）

```bash
sudo python3 scripts/optimize_mysql_config.py
```

这会显示：
- 硬件信息（CPU、内存、磁盘）
- 当前 MySQL 配置
- 优化后的配置建议
- 配置对比

**不会实际修改配置文件**

### 2. 应用优化配置

```bash
sudo python3 scripts/optimize_mysql_config.py --apply
```

这会：
1. 备份原配置文件（带时间戳）
2. 应用优化后的配置
3. 验证配置是否正确
4. 提示重启 MySQL 服务

### 3. 回滚配置

如果优化后出现问题，可以回滚到备份：

```bash
sudo python3 scripts/optimize_mysql_config.py --rollback /etc/mysql/mysql.conf.d/mysqld.cnf.backup_20240101_120000
```

## 配置优化说明

### 针对 2核4GB 服务器的优化策略

#### 1. InnoDB Buffer Pool Size（最重要）

- **优化值**: 512MB-768MB
- **说明**: 
  - 总内存 4GB
  - 系统占用约 800MB
  - MySQL 其他部分约 200MB
  - Gunicorn 3个 worker 约 900MB
  - 预留缓冲约 500MB
  - 因此 Buffer Pool 设置为 512-768MB 最合适

#### 2. Max Connections

- **优化值**: 100-150
- **说明**: 
  - 3个 Gunicorn worker × 20个连接 = 60个连接
  - 加上其他服务和预留，设置为 100-150 足够

#### 3. InnoDB Log File Size

- **优化值**: 128MB-256MB
- **说明**: 建议为 Buffer Pool 的 25%

#### 4. 其他优化

- `innodb_flush_log_at_trx_commit = 2`: 平衡性能和安全性
- `innodb_flush_method = O_DIRECT`: SSD 优化
- `slow_query_log = 1`: 启用慢查询日志，便于性能分析

## 配置参数说明

### 关键配置项

| 配置项 | 说明 | 2核4GB推荐值 |
|--------|------|-------------|
| `innodb_buffer_pool_size` | InnoDB 缓冲池大小 | 512M-768M |
| `max_connections` | 最大连接数 | 100-150 |
| `innodb_log_file_size` | InnoDB 日志文件大小 | 128M-256M |
| `thread_cache_size` | 线程缓存大小 | 20-50 |
| `table_open_cache` | 表缓存大小 | 2000 |
| `tmp_table_size` | 临时表大小 | 32M |
| `max_heap_table_size` | 内存表最大大小 | 32M |

## 注意事项

### 1. 备份重要性

脚本会自动备份配置文件，但建议在应用前手动备份：

```bash
sudo cp /etc/mysql/mysql.conf.d/mysqld.cnf /etc/mysql/mysql.conf.d/mysqld.cnf.backup_manual
```

### 2. 重启 MySQL

应用配置后必须重启 MySQL 服务：

```bash
sudo systemctl restart mysql
```

### 3. 验证配置

重启后检查 MySQL 是否正常运行：

```bash
sudo systemctl status mysql
mysql -u root -p -e "SHOW VARIABLES LIKE 'innodb_buffer_pool_size';"
```

### 4. 监控内存使用

优化后监控系统内存使用情况：

```bash
# 查看内存使用
free -h

# 查看 MySQL 进程内存
ps aux | grep mysql | awk '{print $2, $4, $11}'

# 如果内存使用超过 90%，考虑减少 innodb_buffer_pool_size
```

### 5. 性能测试

优化后建议进行性能测试：

```bash
# 查看慢查询日志
sudo tail -f /var/log/mysql/slow-query.log

# 查看 MySQL 状态
mysql -u root -p -e "SHOW STATUS LIKE 'Innodb_buffer_pool%';"
```

## 故障排查

### 问题 1: MySQL 启动失败

**原因**: 配置参数错误或资源不足

**解决**:
1. 检查错误日志: `sudo tail -n 50 /var/log/mysql/error.log`
2. 回滚配置: `sudo python3 scripts/optimize_mysql_config.py --rollback <备份文件>`
3. 或手动恢复: `sudo cp <备份文件> /etc/mysql/mysql.conf.d/mysqld.cnf`

### 问题 2: 内存不足

**原因**: `innodb_buffer_pool_size` 设置过大

**解决**:
1. 减少 `innodb_buffer_pool_size` 到 384M 或 512M
2. 重启 MySQL: `sudo systemctl restart mysql`

### 问题 3: 连接数不足

**原因**: `max_connections` 设置过小

**解决**:
1. 增加 `max_connections` 到 150 或 200
2. 注意：增加连接数会增加内存占用

## 最佳实践

1. **定期监控**
   - 监控内存使用率
   - 监控 MySQL 连接数
   - 查看慢查询日志

2. **渐进式优化**
   - 先应用配置
   - 观察 1-2 天
   - 根据实际情况微调

3. **保留备份**
   - 保留多个时间点的备份
   - 记录每次优化的效果

4. **文档记录**
   - 记录优化前后的性能指标
   - 记录遇到的问题和解决方案

## 示例输出

```
================================================================
硬件信息检测
================================================================

CPU 信息:
  核心数: 2
  物理核心数: 1
  型号: Intel(R) Core(TM) i5-xxxx CPU @ x.xxGHz

内存信息:
  总内存: 4.00 GB (4096 MB)
  已用内存: 2.50 GB (2560 MB)
  可用内存: 1.50 GB (1536 MB)

磁盘信息:
  总容量: 50G
  已用: 20G (40%)
  可用: 30G

================================================================
配置对比
================================================================

配置项                                          当前值                         优化值
--------------------------------------------------------------------------------------------------------------
mysqld.innodb_buffer_pool_size                  128M                          512M
mysqld.max_connections                          151                           100
mysqld.innodb_log_file_size                     未设置                        128M
...
```

## 相关文件

- 脚本: `scripts/optimize_mysql_config.py`
- MySQL 配置文件: `/etc/mysql/mysql.conf.d/mysqld.cnf`
- MySQL 错误日志: `/var/log/mysql/error.log`
- MySQL 慢查询日志: `/var/log/mysql/slow-query.log`

## 技术支持

如有问题，请检查：
1. MySQL 错误日志
2. 系统日志: `journalctl -u mysql`
3. 内存使用: `free -h`
4. 磁盘空间: `df -h`

