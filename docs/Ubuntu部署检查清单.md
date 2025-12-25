# Ubuntu 22.04.5 LTS 部署检查清单

## 系统要求

- **操作系统**: Ubuntu 22.04.5 LTS (GNU/Linux 5.15.0-161-generic x86_64)
- **Python版本**: Python 3.10+ (Ubuntu 22.04 默认 Python 3.10)
- **Node.js版本**: Node.js 18+ (推荐使用 nvm 安装)
- **数据库**: MySQL 8.0+
- **Redis**: Redis 6.0+ (可选，用于缓存和限流)
- **Web服务器**: Nginx 1.18+

## 1. 系统环境准备

### 1.1 更新系统
```bash
sudo apt update
sudo apt upgrade -y
```

### 1.2 安装基础依赖
```bash
# Python 和虚拟环境
sudo apt install -y python3 python3-pip python3-venv python3-dev

# 编译工具（某些 Python 包需要）
sudo apt install -y build-essential gcc g++ make

# MySQL 客户端和开发库
sudo apt install -y mysql-client libmysqlclient-dev

# Redis（可选）
sudo apt install -y redis-server

# Nginx
sudo apt install -y nginx

# Git
sudo apt install -y git

# 其他工具
sudo apt install -y curl wget vim
```

### 1.3 安装 Node.js (使用 nvm)
```bash
# 安装 nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc

# 安装 Node.js 18 LTS
nvm install 18
nvm use 18
nvm alias default 18

# 验证
node --version
npm --version
```

## 2. 项目部署

### 2.1 创建项目目录
```bash
sudo mkdir -p /data/Platform
sudo chown -R $USER:$USER /data/Platform
```

### 2.2 克隆或上传项目代码
```bash
cd /data/Platform
# 如果使用 Git
git clone <repository-url> .

# 或者直接上传代码到 /data/Platform
```

### 2.3 创建 Python 虚拟环境
```bash
cd /data/Platform
python3 -m venv venv
source venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt
```

### 2.4 验证关键依赖
```bash
# 验证 Gunicorn
venv/bin/gunicorn --version

# 验证其他关键包
python -c "import fastapi; print(fastapi.__version__)"
python -c "import sqlalchemy; print(sqlalchemy.__version__)"
```

## 3. 数据库配置

### 3.1 创建数据库和用户
```bash
sudo mysql -u root -p
```

在 MySQL 中执行：
```sql
-- 创建数据库
CREATE DATABASE platform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建用户（根据实际情况修改）
CREATE USER 'remote'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON platform.* TO 'remote'@'localhost';
FLUSH PRIVILEGES;

-- 退出
EXIT;
```

### 3.2 导入数据库结构（如果需要）
```bash
# 如果有 SQL 文件
mysql -u remote -p platform < /data/Platform/scripts/data/platform20251219.sql
```

## 4. 环境变量配置

### 4.1 创建 .env 文件
```bash
cd /data/Platform
cp env.example .env
sudo chmod 640 .env
sudo chown www-data:www-data .env
```

### 4.2 配置 .env 文件
编辑 `.env` 文件，设置以下关键配置：

```bash
# 生产环境标志
PRODUCTION_ENV=production

# 安全密钥（必须设置，至少32字符）
SECRET_KEY=your_very_long_and_secure_secret_key_here_at_least_32_characters

# 数据库配置
DATABASE_URL=mysql+aiomysql://remote:your_password@localhost:3306/platform

# Redis 配置（可选）
REDIS_URL=redis://localhost:6379/0

# CORS 配置（生产环境必须设置，不能包含 localhost）
BACKEND_CORS_ORIGINS=https://your-domain.com,https://www.your-domain.com

# 管理员账户
FIRST_SUPERUSER=admin
FIRST_SUPERUSER_PASSWORD=your_secure_admin_password_at_least_12_characters

# JWT 配置
ACCESS_TOKEN_EXPIRE_MINUTES=240
JWT_ALGORITHM=RS256

# RSA 密钥路径（如果使用 RS256）
RSA_PRIVATE_KEY_PATH=/data/Platform/keys/private_key.pem
RSA_PUBLIC_KEY_PATH=/data/Platform/keys/public_key.pem

# 时区配置
TIMEZONE=Asia/Shanghai

# Telegram Bot（可选）
TELEGRAM_ENABLE=true
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_ADMIN=your_telegram_chat_id
```

### 4.3 设置文件权限
```bash
sudo chown www-data:www-data /data/Platform/.env
sudo chmod 640 /data/Platform/.env
```

## 5. 日志目录配置

### 5.1 创建日志目录
```bash
sudo mkdir -p /data/Platform/logs
sudo chown -R www-data:www-data /data/Platform/logs
sudo chmod 750 /data/Platform/logs
```

## 6. Systemd 服务配置

### 6.1 复制服务文件
```bash
sudo cp /data/Platform/systemd/Platform-backend.service /etc/systemd/system/
```

### 6.2 验证服务文件
检查 `/etc/systemd/system/Platform-backend.service` 中的路径是否正确：
- `WorkingDirectory=/data/Platform`
- `ExecStart=/data/Platform/venv/bin/gunicorn`
- `EnvironmentFile=/data/Platform/.env`

### 6.3 重载 systemd
```bash
sudo systemctl daemon-reload
```

### 6.4 启动服务
```bash
sudo systemctl start Platform-backend.service
sudo systemctl enable Platform-backend.service  # 开机自启
```

### 6.5 检查服务状态
```bash
sudo systemctl status Platform-backend.service
```

### 6.6 查看日志
```bash
# systemd 日志
sudo journalctl -u Platform-backend.service -f

# 应用日志
tail -f /data/Platform/logs/app.log

# Gunicorn 日志
tail -f /data/Platform/logs/gunicorn_error.log
```

## 7. 前端构建

### 7.1 安装前端依赖
```bash
cd /data/Platform/frontend
npm install
```

### 7.2 构建前端
```bash
npm run build
```

### 7.3 验证构建结果
```bash
ls -la /data/Platform/frontend/dist
```

## 8. Nginx 配置

### 8.1 复制 Nginx 配置
```bash
# 根据实际域名选择配置文件
sudo cp /data/Platform/nginx/btfrx.online/nginx.conf /etc/nginx/nginx.conf

# 或者使用其他域名配置
# sudo cp /data/Platform/nginx/king-sms.com/nginx.conf /etc/nginx/nginx.conf
```

### 8.2 修改 Nginx 配置
根据实际情况修改：
- 服务器名称（server_name）
- SSL 证书路径
- 前端静态文件路径
- 后端代理地址（默认 127.0.0.1:8960）

### 8.3 测试 Nginx 配置
```bash
sudo nginx -t
```

### 8.4 启动/重启 Nginx
```bash
sudo systemctl restart nginx
sudo systemctl enable nginx
```

## 9. 防火墙配置

### 9.1 配置 UFW 防火墙
```bash
# 允许 SSH
sudo ufw allow 22/tcp

# 允许 HTTP 和 HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 启用防火墙
sudo ufw enable

# 查看状态
sudo ufw status
```

## 10. SSL 证书配置

### 10.1 使用 Let's Encrypt (推荐)
```bash
# 安装 Certbot
sudo apt install -y certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# 自动续期测试
sudo certbot renew --dry-run
```

### 10.2 或使用已有证书
将证书文件放到指定位置：
```bash
sudo mkdir -p /data/Platform/nginx/your-domain.com
# 复制证书文件
sudo cp your-cert.pem /data/Platform/nginx/your-domain.com/
sudo cp your-key.key /data/Platform/nginx/your-domain.com/
```

## 11. 权限设置

### 11.1 设置项目目录权限
```bash
# 项目根目录
sudo chown -R www-data:www-data /data/Platform
sudo chmod -R 755 /data/Platform

# 日志目录（特殊权限）
sudo chown -R www-data:www-data /data/Platform/logs
sudo chmod 750 /data/Platform/logs

# .env 文件（敏感文件）
sudo chown www-data:www-data /data/Platform/.env
sudo chmod 640 /data/Platform/.env

# 前端构建目录
sudo chown -R www-data:www-data /data/Platform/frontend/dist
```

## 12. 验证部署

### 12.1 检查后端服务
```bash
# 检查服务状态
sudo systemctl status Platform-backend.service

# 检查端口监听
sudo netstat -tlnp | grep 8960
# 或使用
sudo ss -tlnp | grep 8960

# 测试 API
curl http://127.0.0.1:8960/api/v1/health
```

### 12.2 检查前端
```bash
# 检查 Nginx 状态
sudo systemctl status nginx

# 测试前端访问
curl -I https://your-domain.com
```

### 12.3 检查数据库连接
```bash
# 在 Python 环境中测试
cd /data/Platform
source venv/bin/activate
python -c "from app.core.database import engine; import asyncio; asyncio.run(engine.connect())"
```

## 13. 常见问题排查

### 13.1 服务无法启动
```bash
# 查看详细错误
sudo journalctl -u Platform-backend.service -n 50

# 检查 Python 环境
/data/Platform/venv/bin/python --version

# 检查依赖
/data/Platform/venv/bin/pip list | grep gunicorn
```

### 13.2 数据库连接失败
```bash
# 测试数据库连接
mysql -u remote -p -h 127.0.0.1 platform

# 检查 .env 中的 DATABASE_URL
cat /data/Platform/.env | grep DATABASE_URL
```

### 13.3 权限问题
```bash
# 检查文件所有者
ls -la /data/Platform | grep www-data

# 修复权限
sudo chown -R www-data:www-data /data/Platform
```

### 13.4 端口被占用
```bash
# 查找占用 8960 端口的进程
sudo lsof -i :8960
# 或
sudo netstat -tlnp | grep 8960
```

## 14. 性能优化

### 14.1 Gunicorn Workers 配置
根据服务器配置调整 `gunicorn.conf.py`：
- 2核CPU + 4GB内存：默认 3 workers
- 4核CPU + 8GB内存：建议 5-7 workers
- 可通过环境变量 `WORKERS` 覆盖

### 14.2 数据库连接池
在 `.env` 中配置：
```bash
DB_POOL_SIZE=12
DB_MAX_OVERFLOW=8
DB_POOL_RECYCLE=3600
```

### 14.3 Redis 连接池
```bash
REDIS_MAX_CONNECTIONS=20
```

## 15. 监控和维护

### 15.1 日志轮转
系统会自动轮转日志（配置在 `app/main.py` 中）：
- 日志文件最大 5MB
- 保留 5 个备份文件

### 15.2 定期检查
```bash
# 检查服务状态
sudo systemctl status Platform-backend.service

# 检查磁盘空间
df -h

# 检查内存使用
free -h

# 检查进程
ps aux | grep gunicorn
```

## 16. 更新部署

### 16.1 后端更新
```bash
cd /data/Platform
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart Platform-backend.service
```

### 16.2 前端更新
```bash
cd /data/Platform/frontend
npm install
npm run build
sudo systemctl reload nginx
```

或使用更新脚本：
```bash
sudo /data/Platform/update_frontend.sh
```

## 17. 备份

### 17.1 数据库备份
```bash
# 创建备份脚本
mysqldump -u remote -p platform > /backup/platform_$(date +%Y%m%d).sql
```

### 17.2 代码备份
```bash
# 使用 Git
cd /data/Platform
git add .
git commit -m "Backup before deployment"
git push
```

## 18. 安全检查清单

- [ ] `.env` 文件权限设置为 640，所有者 www-data
- [ ] `SECRET_KEY` 已设置且足够复杂（至少32字符）
- [ ] `FIRST_SUPERUSER_PASSWORD` 已设置且足够复杂（至少12字符）
- [ ] `BACKEND_CORS_ORIGINS` 不包含 localhost（生产环境）
- [ ] SSL 证书已正确配置
- [ ] 防火墙已启用并正确配置
- [ ] 数据库用户密码足够复杂
- [ ] 日志目录权限正确（750）
- [ ] Systemd 服务使用非 root 用户（www-data）

## 19. 时区检查

项目启动时会自动检查系统时区与配置时区是否一致：
- 配置时区：`TIMEZONE=Asia/Shanghai`（在 .env 中）
- 系统时区：通过 `timedatectl` 或 `/etc/timezone` 检测
- 如果不一致，应用会使用配置的时区，并记录警告日志

检查系统时区：
```bash
timedatectl
# 或
cat /etc/timezone
```

## 20. 完成部署

部署完成后，访问：
- 前端：`https://your-domain.com`
- API：`https://your-domain.com/api/v1/`
- 健康检查：`https://your-domain.com/api/v1/health`

默认管理员账户：
- 用户名：在 `.env` 中配置的 `FIRST_SUPERUSER`
- 密码：在 `.env` 中配置的 `FIRST_SUPERUSER_PASSWORD`

---

**注意**：所有涉及密码和密钥的配置都应该使用强密码，生产环境绝对不能使用默认值。

