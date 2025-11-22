# 快速迁移指南

## 一键迁移

```bash
# 1. 确保数据库配置正确（.env文件中的DATABASE_URL）
# 2. 运行迁移脚本
python scripts/migrate_from_old_sql.py
```

## 主要功能

✅ 自动解析SQL文件  
✅ 处理表结构差异（chat_id、country_code、表名等）  
✅ 验证外键关系  
✅ 跳过已存在记录（避免重复）  
✅ 详细的迁移统计和错误报告  

## 表结构差异处理

| 旧表 | 新表 | 处理方式 |
|------|------|---------|
| `country_info` | `countries` | 自动映射字段名 |
| `clients.chat_id` | 无 | 跳过该字段 |
| `ad_data` (无country_code) | `ad_data.country_code` | 设为NULL |

## 常见问题

**Q: 迁移失败怎么办？**  
A: 检查日志输出，查看具体错误。通常是外键约束或唯一约束冲突。

**Q: 可以重复运行吗？**  
A: 可以，默认会跳过已存在的记录。

**Q: 如何清空数据重新迁移？**  
A: 手动删除表数据或使用数据库备份恢复。

