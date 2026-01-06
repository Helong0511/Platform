#!/bin/bash

# 生产环境配置检查脚本
# 用于快速验证 Ubuntu 22.04.5 生产环境配置

echo "=========================================="
echo "生产环境配置检查脚本"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查函数
check_pass() {
    echo -e "${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# 1. 检查项目目录
echo "1. 检查项目目录..."
if [ -d "/data/Platform" ]; then
    check_pass "项目目录存在: /data/Platform"
else
    check_fail "项目目录不存在: /data/Platform"
    exit 1
fi

# 2. 检查环境变量文件
echo ""
echo "2. 检查环境变量文件..."
if [ -f "/data/Platform/.env" ]; then
    check_pass ".env 文件存在"
    
    # 检查文件权限
    PERMS=$(stat -c "%a" /data/Platform/.env)
    if [ "$PERMS" = "640" ] || [ "$PERMS" = "600" ]; then
        check_pass ".env 文件权限正确: $PERMS"
    else
        check_warn ".env 文件权限可能不安全: $PERMS (建议: 640 或 600)"
    fi
    
    # 检查必填配置项
    if grep -q "PRODUCTION_ENV=production" /data/Platform/.env; then
        check_pass "PRODUCTION_ENV=production 已设置"
    else
        check_fail "PRODUCTION_ENV 未设置为 production"
    fi
    
    if grep -q "SECRET_KEY=" /data/Platform/.env && ! grep -q "SECRET_KEY=$" /data/Platform/.env; then
        SECRET_KEY=$(grep "SECRET_KEY=" /data/Platform/.env | cut -d'=' -f2)
        if [ ${#SECRET_KEY} -ge 32 ]; then
            check_pass "SECRET_KEY 已设置（长度: ${#SECRET_KEY}）"
        else
            check_fail "SECRET_KEY 长度不足（当前: ${#SECRET_KEY}，要求: >= 32）"
        fi
    else
        check_fail "SECRET_KEY 未设置"
    fi
    
    if grep -q "DATABASE_URL=" /data/Platform/.env && ! grep -q "DATABASE_URL=$" /data/Platform/.env; then
        check_pass "DATABASE_URL 已设置"
    else
        check_fail "DATABASE_URL 未设置"
    fi
    
    if grep -q "BACKEND_CORS_ORIGINS=" /data/Platform/.env && ! grep -q "BACKEND_CORS_ORIGINS=$" /data/Platform/.env; then
        check_pass "BACKEND_CORS_ORIGINS 已设置"
    else
        check_fail "BACKEND_CORS_ORIGINS 未设置"
    fi
else
    check_fail ".env 文件不存在"
    check_warn "请复制 env.example 为 .env 并配置"
fi

# 3. 检查虚拟环境
echo ""
echo "3. 检查虚拟环境..."
if [ -d "/data/Platform/venv" ]; then
    check_pass "虚拟环境目录存在"
    
    if [ -f "/data/Platform/venv/bin/gunicorn" ]; then
        check_pass "Gunicorn 已安装"
    else
        check_fail "Gunicorn 未安装"
    fi
    
    if [ -f "/data/Platform/venv/bin/python" ]; then
        PYTHON_VERSION=$(/data/Platform/venv/bin/python --version)
        check_pass "Python 版本: $PYTHON_VERSION"
    else
        check_fail "Python 未找到"
    fi
else
    check_fail "虚拟环境目录不存在"
    check_warn "请运行: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
fi

# 4. 检查前端构建
echo ""
echo "4. 检查前端构建..."
if [ -d "/data/Platform/frontend/dist" ]; then
    check_pass "前端构建目录存在"
    
    if [ -f "/data/Platform/frontend/dist/index.html" ]; then
        check_pass "前端 index.html 存在"
    else
        check_fail "前端 index.html 不存在"
    fi
    
    # 检查静态资源
    if [ -d "/data/Platform/frontend/dist/assets" ]; then
        ASSET_COUNT=$(find /data/Platform/frontend/dist/assets -type f | wc -l)
        check_pass "前端静态资源存在（$ASSET_COUNT 个文件）"
    else
        check_warn "前端 assets 目录不存在（可能需要重新构建）"
    fi
else
    check_fail "前端构建目录不存在"
    check_warn "请运行: cd frontend && npm install && npm run build"
fi

# 5. 检查后端服务
echo ""
echo "5. 检查后端服务..."
if systemctl is-active --quiet Platform-backend.service; then
    check_pass "后端服务正在运行"
    
    # 检查端口监听
    if netstat -tlnp 2>/dev/null | grep -q ":8960"; then
        check_pass "后端端口 8960 正在监听"
    else
        check_warn "后端端口 8960 未监听（服务可能刚启动）"
    fi
else
    check_fail "后端服务未运行"
    check_warn "请运行: sudo systemctl start Platform-backend.service"
fi

# 6. 检查数据库连接
echo ""
echo "6. 检查数据库连接..."
if systemctl is-active --quiet mysql; then
    check_pass "MySQL 服务正在运行"
    
    # 尝试连接数据库（需要从 .env 读取配置）
    if [ -f "/data/Platform/.env" ]; then
        DB_URL=$(grep "DATABASE_URL=" /data/Platform/.env | cut -d'=' -f2-)
        if [ -n "$DB_URL" ]; then
            # 提取数据库信息（简单解析）
            if echo "$DB_URL" | grep -q "mysql"; then
                check_pass "数据库 URL 格式正确"
            else
                check_warn "数据库 URL 格式可能不正确"
            fi
        fi
    fi
else
    check_fail "MySQL 服务未运行"
    check_warn "请运行: sudo systemctl start mysql"
fi

# 7. 检查 Redis 连接
echo ""
echo "7. 检查 Redis 连接..."
if systemctl is-active --quiet redis 2>/dev/null || systemctl is-active --quiet redis-server 2>/dev/null; then
    check_pass "Redis 服务正在运行"
    
    if redis-cli -h 127.0.0.1 ping 2>/dev/null | grep -q "PONG"; then
        check_pass "Redis 连接正常"
    else
        check_warn "Redis 连接失败（可能未配置或密码错误）"
    fi
else
    check_warn "Redis 服务未运行（可选，如果不使用 Redis 可以忽略）"
fi

# 8. 检查 Nginx 配置
echo ""
echo "8. 检查 Nginx 配置..."
if systemctl is-active --quiet nginx; then
    check_pass "Nginx 服务正在运行"
    
    if nginx -t 2>/dev/null; then
        check_pass "Nginx 配置语法正确"
    else
        check_fail "Nginx 配置语法错误"
        check_warn "请运行: sudo nginx -t 查看详细错误"
    fi
else
    check_fail "Nginx 服务未运行"
    check_warn "请运行: sudo systemctl start nginx"
fi

# 9. 检查日志目录
echo ""
echo "9. 检查日志目录..."
if [ -d "/data/Platform/logs" ]; then
    check_pass "日志目录存在"
    
    # 检查权限
    LOG_PERMS=$(stat -c "%a" /data/Platform/logs)
    if [ "$LOG_PERMS" = "750" ] || [ "$LOG_PERMS" = "755" ]; then
        check_pass "日志目录权限正确: $LOG_PERMS"
    else
        check_warn "日志目录权限可能不正确: $LOG_PERMS (建议: 750)"
    fi
    
    # 检查日志文件
    if [ -f "/data/Platform/logs/app.log" ]; then
        LOG_SIZE=$(du -h /data/Platform/logs/app.log | cut -f1)
        check_pass "应用日志文件存在（大小: $LOG_SIZE）"
    else
        check_warn "应用日志文件不存在（服务可能刚启动）"
    fi
else
    check_warn "日志目录不存在（服务启动时会自动创建）"
fi

# 10. 检查 SSL 证书
echo ""
echo "10. 检查 SSL 证书..."
if [ -f "/data/Platform/nginx/btfrx.online/client.btfrx.online_bundle.pem" ]; then
    check_pass "SSL 证书文件存在"
    
    # 检查证书有效期（如果 openssl 可用）
    if command -v openssl &> /dev/null; then
        CERT_EXPIRY=$(openssl x509 -enddate -noout -in /data/Platform/nginx/btfrx.online/client.btfrx.online_bundle.pem 2>/dev/null | cut -d'=' -f2)
        if [ -n "$CERT_EXPIRY" ]; then
            check_pass "SSL 证书有效期: $CERT_EXPIRY"
        fi
    fi
else
    check_warn "SSL 证书文件不存在（请检查 Nginx 配置中的证书路径）"
fi

# 11. 检查 RSA 密钥
echo ""
echo "11. 检查 RSA 密钥（JWT）..."
if [ -f "/data/Platform/keys/private_key.pem" ] && [ -f "/data/Platform/keys/public_key.pem" ]; then
    check_pass "RSA 密钥文件存在"
else
    check_warn "RSA 密钥文件不存在（如果使用 RS256 算法需要配置）"
    check_warn "请运行: python scripts/generate_rsa_keys.py --output-dir keys"
fi

# 总结
echo ""
echo "=========================================="
echo "检查完成"
echo "=========================================="
echo ""
echo "如果发现问题，请参考检查报告："
echo "  docs/生产环境部署检查报告.md"
echo ""
echo "常用命令："
echo "  查看后端服务状态: sudo systemctl status Platform-backend.service"
echo "  查看后端日志: sudo journalctl -u Platform-backend.service -f"
echo "  查看应用日志: tail -f /data/Platform/logs/app.log"
echo "  重启后端服务: sudo systemctl restart Platform-backend.service"
echo "  测试 Nginx 配置: sudo nginx -t"
echo "  重载 Nginx: sudo systemctl reload nginx"
echo ""

