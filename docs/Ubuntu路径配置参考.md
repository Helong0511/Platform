# Ubuntu 路径配置参考

## 项目目录
**生产环境（Ubuntu）项目根目录：`/data/Platform`**

> **注意**: 本项目支持两个环境：
> - **生产环境**: Ubuntu，项目目录 `/data/Platform`
> - **测试环境**: Windows，项目目录 `E:\data\Platform`
> 
> 详细说明请参考 [环境配置说明](./环境配置说明.md)

## 关键路径配置

### 1. 项目结构
```
/data/Platform/
├── app/                    # 后端应用代码
├── frontend/               # 前端代码
│   └── dist/              # 前端构建输出
├── scripts/                # 脚本目录
│   ├── check_config.py    # 配置检查工具
│   └── generate_rsa_keys.py  # RSA 密钥生成工具
├── keys/                   # RSA 密钥目录（需要创建）
│   ├── private_key.pem    # 私钥文件
│   └── public_key.pem     # 公钥文件
├── logs/                   # 日志目录
├── venv/                   # Python 虚拟环境
├── .env                    # 环境变量配置文件
├── gunicorn.conf.py        # Gunicorn 配置文件
└── systemd/                # Systemd 服务文件
    └── Platform-backend.service
```

### 2. 环境变量配置（.env 文件）

#### RSA 密钥路径配置
```bash
# 方法1: 使用文件路径（推荐）
RSA_PRIVATE_KEY_PATH=/data/Platform/keys/private_key.pem
RSA_PUBLIC_KEY_PATH=/data/Platform/keys/public_key.pem

# 方法2: 使用相对路径（相对于项目根目录）
RSA_PRIVATE_KEY_PATH=keys/private_key.pem
RSA_PUBLIC_KEY_PATH=keys/public_key.pem
```

#### 其他关键路径配置
```bash
# 项目根目录（通常不需要在 .env 中配置，但某些脚本可能需要）
PROJECT_ROOT=/data/Platform

# 日志目录
LOG_DIR=/data/Platform/logs
```

### 3. Systemd 服务配置

**文件位置：** `/etc/systemd/system/Platform-backend.service`

**关键路径配置：**
```ini
[Service]
WorkingDirectory=/data/Platform
Environment="PATH=/data/Platform/venv/bin"
EnvironmentFile=/data/Platform/.env
ExecStartPre=/bin/mkdir -p /data/Platform/logs
ExecStart=/data/Platform/venv/bin/gunicorn \
    --config /data/Platform/gunicorn.conf.py \
    app.main:app
ReadWritePaths=/data/Platform/logs /data/Platform
```

### 4. Nginx 配置

**前端静态文件路径：**
```nginx
root /data/Platform/frontend/dist;
```

**SSL 证书路径（示例）：**
```nginx
ssl_certificate /data/Platform/nginx/btfrx.online/client.btfrx.online_bundle.pem;
ssl_certificate_key /data/Platform/nginx/btfrx.online/client.btfrx.online.key;
```

### 5. 常用命令

#### 生成 RSA 密钥对
```bash
cd /data/Platform
python3 scripts/generate_rsa_keys.py --output-dir /data/Platform/keys
# 或使用相对路径
python3 scripts/generate_rsa_keys.py --output-dir keys
```

#### 检查配置
```bash
cd /data/Platform
python3 scripts/check_config.py
```

#### 设置文件权限
```bash
# .env 文件权限
sudo chown www-data:www-data /data/Platform/.env
sudo chmod 640 /data/Platform/.env

# 日志目录权限
sudo mkdir -p /data/Platform/logs
sudo chown -R www-data:www-data /data/Platform/logs
sudo chmod 750 /data/Platform/logs

# RSA 密钥文件权限
sudo chown www-data:www-data /data/Platform/keys/private_key.pem
sudo chmod 600 /data/Platform/keys/private_key.pem
sudo chown www-data:www-data /data/Platform/keys/public_key.pem
sudo chmod 644 /data/Platform/keys/public_key.pem
```

#### 查看日志
```bash
# 应用日志
tail -f /data/Platform/logs/app.log

# Gunicorn 日志
tail -f /data/Platform/logs/gunicorn_error.log

# Systemd 日志
sudo journalctl -u Platform-backend.service -f
```

### 6. 目录权限建议

| 目录/文件 | 所有者 | 权限 | 说明 |
|---------|--------|------|------|
| `/data/Platform` | `www-data:www-data` | `755` | 项目根目录 |
| `/data/Platform/.env` | `www-data:www-data` | `640` | 环境变量文件（敏感） |
| `/data/Platform/logs` | `www-data:www-data` | `750` | 日志目录 |
| `/data/Platform/keys/` | `www-data:www-data` | `750` | 密钥目录 |
| `/data/Platform/keys/private_key.pem` | `www-data:www-data` | `600` | 私钥（仅所有者可读） |
| `/data/Platform/keys/public_key.pem` | `www-data:www-data` | `644` | 公钥（所有人可读） |
| `/data/Platform/frontend/dist` | `www-data:www-data` | `755` | 前端静态文件 |
| `/data/Platform/venv` | `www-data:www-data` | `755` | Python 虚拟环境 |

### 7. 快速部署检查清单

1. ✅ 确认项目目录存在：`/data/Platform`
2. ✅ 创建密钥目录：`mkdir -p /data/Platform/keys`
3. ✅ 生成 RSA 密钥：`python3 scripts/generate_rsa_keys.py --output-dir /data/Platform/keys`
4. ✅ 配置 .env 文件中的密钥路径
5. ✅ 设置文件权限（参考上面的权限表）
6. ✅ 验证 Systemd 服务配置中的路径
7. ✅ 验证 Nginx 配置中的路径
8. ✅ 运行配置检查：`python3 scripts/check_config.py`

### 8. 常见问题

#### Q: 如何确认当前项目路径？
```bash
cd /data/Platform
pwd  # 应该显示 /data/Platform
```

#### Q: 如何检查路径是否正确配置？
```bash
cd /data/Platform
python3 scripts/check_config.py
```

#### Q: 密钥文件找不到？
- 检查密钥文件是否存在：`ls -la /data/Platform/keys/`
- 检查 .env 中的路径配置是否正确
- 检查文件权限：`ls -la /data/Platform/keys/private_key.pem`

#### Q: 日志文件无法写入？
- 检查日志目录权限：`ls -ld /data/Platform/logs`
- 确保目录所有者是 www-data：`sudo chown -R www-data:www-data /data/Platform/logs`

### 9. 相关文档

- [Ubuntu 部署检查清单](./Ubuntu部署检查清单.md)
- [配置检查工具说明](../README_CHECK_CONFIG.md)
- [RSA 密钥生成工具](../scripts/generate_rsa_keys.py)

