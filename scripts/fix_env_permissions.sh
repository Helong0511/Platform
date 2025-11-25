#!/bin/bash
# -*- coding: utf-8 -*-
#
# 修复 .env 文件权限脚本
# 用于解决 systemd 服务无法读取 .env 文件的权限问题
#
# 使用方法：
#   sudo bash scripts/fix_env_permissions.sh
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="/data/Platform"
ENV_FILE="${PROJECT_ROOT}/.env"
SERVICE_USER="www-data"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}修复 .env 文件权限${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}错误：此脚本需要 root 权限${NC}"
    echo -e "${YELLOW}请使用：sudo bash scripts/fix_env_permissions.sh${NC}"
    exit 1
fi

# 检查 .env 文件是否存在
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}错误：.env 文件不存在：${ENV_FILE}${NC}"
    echo -e "${YELLOW}请先创建 .env 文件：cp env.example .env${NC}"
    exit 1
fi

# 检查 www-data 用户是否存在
if ! id "$SERVICE_USER" &>/dev/null; then
    echo -e "${YELLOW}警告：用户 ${SERVICE_USER} 不存在${NC}"
    echo -e "${YELLOW}请确认 systemd 服务使用的用户，或手动修改脚本中的 SERVICE_USER 变量${NC}"
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 显示当前权限
echo -e "${BLUE}当前文件信息：${NC}"
ls -la "$ENV_FILE"
echo ""

# 获取当前所有者和权限
CURRENT_OWNER=$(stat -c '%U:%G' "$ENV_FILE")
CURRENT_PERMS=$(stat -c '%a' "$ENV_FILE")

echo -e "${BLUE}当前所有者：${CURRENT_OWNER}${NC}"
echo -e "${BLUE}当前权限：${CURRENT_PERMS}${NC}"
echo ""

# 修复权限
echo -e "${YELLOW}正在修复权限...${NC}"

# 设置所有者
chown "${SERVICE_USER}:${SERVICE_USER}" "$ENV_FILE"
echo -e "${GREEN}✓ 已设置所有者：${SERVICE_USER}:${SERVICE_USER}${NC}"

# 设置权限为 640
chmod 640 "$ENV_FILE"
echo -e "${GREEN}✓ 已设置权限：640${NC}"

echo ""

# 显示修复后的权限
echo -e "${BLUE}修复后的文件信息：${NC}"
ls -la "$ENV_FILE"
echo ""

# 验证权限
NEW_OWNER=$(stat -c '%U:%G' "$ENV_FILE")
NEW_PERMS=$(stat -c '%a' "$ENV_FILE")

if [ "$NEW_OWNER" = "${SERVICE_USER}:${SERVICE_USER}" ] && [ "$NEW_PERMS" = "640" ]; then
    echo -e "${GREEN}✓ 权限修复成功！${NC}"
    echo ""
    echo -e "${BLUE}下一步：${NC}"
    echo -e "1. 重启服务：${YELLOW}sudo systemctl restart Platform-backend.service${NC}"
    echo -e "2. 检查状态：${YELLOW}sudo systemctl status Platform-backend.service${NC}"
    echo -e "3. 查看日志：${YELLOW}sudo journalctl -u Platform-backend.service -f${NC}"
else
    echo -e "${RED}✗ 权限修复失败${NC}"
    echo -e "${YELLOW}请手动检查并修复权限${NC}"
    exit 1
fi

