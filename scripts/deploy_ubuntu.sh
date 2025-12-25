#!/bin/bash
# Ubuntu 22.04.5 LTS 快速部署脚本
# 使用方法: sudo bash scripts/deploy_ubuntu.sh

set -e  # 遇到错误立即退出

echo "=========================================="
echo "Platform 项目部署脚本"
echo "Ubuntu 22.04.5 LTS"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}错误: 请使用 sudo 运行此脚本${NC}"
    exit 1
fi

# 项目路径
PROJECT_DIR="/data/Platform"
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"

echo -e "${GREEN}[1/10] 检查系统环境...${NC}"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}安装 Python3...${NC}"
    apt update
    apt install -y python3 python3-pip python3-venv python3-dev
fi

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}警告: Node.js 未安装，请先安装 Node.js 18+${NC}"
    echo "可以使用 nvm 安装: curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash"
fi

# 检查 MySQL
if ! command -v mysql &> /dev/null; then
    echo -e "${YELLOW}警告: MySQL 客户端未安装${NC}"
fi

# 检查 Redis
if ! command -v redis-cli &> /dev/null; then
    echo -e "${YELLOW}警告: Redis 未安装（可选）${NC}"
fi

echo -e "${GREEN}[2/10] 创建项目目录...${NC}"
mkdir -p "$PROJECT_DIR"
mkdir -p "$LOG_DIR"

echo -e "${GREEN}[3/10] 创建 Python 虚拟环境...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}虚拟环境创建成功${NC}"
else
    echo -e "${YELLOW}虚拟环境已存在，跳过创建${NC}"
fi

echo -e "${GREEN}[4/10] 安装 Python 依赖...${NC}"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$PROJECT_DIR/requirements.txt"

# 验证关键依赖
echo -e "${GREEN}验证关键依赖...${NC}"
if ! "$VENV_DIR/bin/gunicorn" --version &> /dev/null; then
    echo -e "${RED}错误: Gunicorn 安装失败${NC}"
    exit 1
fi
echo -e "${GREEN}Gunicorn 安装成功${NC}"

deactivate

echo -e "${GREEN}[5/10] 配置环境变量...${NC}"
if [ ! -f "$PROJECT_DIR/.env" ]; then
    if [ -f "$PROJECT_DIR/env.example" ]; then
        cp "$PROJECT_DIR/env.example" "$PROJECT_DIR/.env"
        echo -e "${YELLOW}已从 env.example 创建 .env 文件，请编辑配置${NC}"
    else
        echo -e "${RED}错误: 找不到 env.example 文件${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}.env 文件已存在，跳过创建${NC}"
fi

# 设置 .env 文件权限
chown www-data:www-data "$PROJECT_DIR/.env"
chmod 640 "$PROJECT_DIR/.env"

echo -e "${GREEN}[6/10] 设置目录权限...${NC}"
chown -R www-data:www-data "$PROJECT_DIR"
chmod -R 755 "$PROJECT_DIR"

# 日志目录特殊权限
chown -R www-data:www-data "$LOG_DIR"
chmod 750 "$LOG_DIR"

echo -e "${GREEN}[7/10] 配置 Systemd 服务...${NC}"
if [ -f "$PROJECT_DIR/systemd/Platform-backend.service" ]; then
    cp "$PROJECT_DIR/systemd/Platform-backend.service" /etc/systemd/system/
    systemctl daemon-reload
    echo -e "${GREEN}Systemd 服务配置完成${NC}"
else
    echo -e "${RED}错误: 找不到 systemd 服务文件${NC}"
    exit 1
fi

echo -e "${GREEN}[8/10] 检查数据库连接...${NC}"
# 这里可以添加数据库连接测试
echo -e "${YELLOW}请手动验证数据库连接${NC}"

echo -e "${GREEN}[9/10] 构建前端（如果存在）...${NC}"
if [ -d "$PROJECT_DIR/frontend" ] && command -v npm &> /dev/null; then
    cd "$PROJECT_DIR/frontend"
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}安装前端依赖...${NC}"
        npm install
    fi
    echo -e "${YELLOW}构建前端...${NC}"
    npm run build
    chown -R www-data:www-data "$PROJECT_DIR/frontend/dist"
    echo -e "${GREEN}前端构建完成${NC}"
else
    echo -e "${YELLOW}跳过前端构建（目录不存在或 Node.js 未安装）${NC}"
fi

echo -e "${GREEN}[10/10] 启动服务...${NC}"
systemctl enable Platform-backend.service
systemctl restart Platform-backend.service

# 等待服务启动
sleep 3

# 检查服务状态
if systemctl is-active --quiet Platform-backend.service; then
    echo -e "${GREEN}✓ 服务启动成功${NC}"
else
    echo -e "${RED}✗ 服务启动失败，请检查日志${NC}"
    echo "查看日志: sudo journalctl -u Platform-backend.service -n 50"
    exit 1
fi

echo ""
echo "=========================================="
echo -e "${GREEN}部署完成！${NC}"
echo "=========================================="
echo ""
echo "下一步操作："
echo "1. 编辑 .env 文件配置数据库和其他设置:"
echo "   sudo nano $PROJECT_DIR/.env"
echo ""
echo "2. 检查服务状态:"
echo "   sudo systemctl status Platform-backend.service"
echo ""
echo "3. 查看日志:"
echo "   sudo journalctl -u Platform-backend.service -f"
echo "   或"
echo "   tail -f $LOG_DIR/app.log"
echo ""
echo "4. 配置 Nginx（如果需要）:"
echo "   sudo cp $PROJECT_DIR/nginx/your-domain/nginx.conf /etc/nginx/nginx.conf"
echo "   sudo nginx -t"
echo "   sudo systemctl restart nginx"
echo ""
echo "5. 配置防火墙:"
echo "   sudo ufw allow 80/tcp"
echo "   sudo ufw allow 443/tcp"
echo "   sudo ufw enable"
echo ""

