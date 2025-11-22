# 生产环境配置快速参考

## 快速开始

### 1. 创建配置文件

```bash
# 复制模板文件
cp .env.production.example .env.production

# 设置文件权限（仅所有者可读写）
chmod 600 .env.production
```

### 2. 必须修改的配置项

打开 `.env.production` 文件，修改以下配置项：

#### 生成 SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

将生成的密钥设置到 `SECRET_KEY`。

#### 必须修改的配置

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| `SECRET_KEY` | JWT签名密钥（至少32字符） | 使用上述命令生成 |
| `MYSQL_ROOT_PASSWORD` | MySQL根密码（至少16字符） | `MyStr0ng!P@ssw0rd123` |
| `MYSQL_PASSWORD` | MySQL应用用户密码（至少16字符） | `AppUs3r!P@ssw0rd456` |
| `REDIS_PASSWORD` | Redis密码（至少16字符） | `R3d1s!P@ssw0rd789` |
| `FIRST_SUPERUSER_PASSWORD` | 管理员密码（至少12字符） | `Admin!P@ssw0rd` |
| `BACKEND_CORS_ORIGINS` | 前端域名（必须使用HTTPS） | `https://example.com` |

### 3. 启动服务

```bash
# 使用 Docker Compose
docker-compose --env-file .env.production up -d

# 查看日志
docker-compose logs -f
```

## 配置验证清单

部署前请确认：

- [ ] `SECRET_KEY` 已设置为强随机密钥
- [ ] 所有密码都已修改（不使用默认值）
- [ ] `BACKEND_CORS_ORIGINS` 已设置为实际域名
- [ ] `PRODUCTION_ENV` 已设置为 `production`
- [ ] 文件权限已设置为 `600`

## 详细文档

完整的配置说明请参考：[生产环境配置指南](docs/生产环境配置指南.md)

## 安全提示

1. **不要**将 `.env.production` 提交到版本控制系统
2. **必须**使用强密码（至少12-16字符）
3. **建议**定期轮换密码和密钥（每3-6个月）
4. **必须**使用 HTTPS（生产环境）
5. **建议**使用密钥管理服务存储敏感信息

