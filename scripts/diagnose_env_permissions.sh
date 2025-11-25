#!/bin/bash
# -*- coding: utf-8 -*-
#
# .env 文件权限诊断和修复脚本
# 用于诊断和修复 systemd 服务无法读取 .env 文件的问题
#
# 使用方法：
#   sudo bash scripts/diagnose_env_permissions.sh
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="/data/Platform"
ENV_FILE="${PROJECT_ROOT}/.env"
SERVICE_USER="www-data"
SERVICE_GROUP="www-data"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}.env 文件权限诊断和修复工具${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}错误：此脚本需要 root 权限${NC}"
    echo -e "${YELLOW}请使用：sudo bash scripts/diagnose_env_permissions.sh${NC}"
    exit 1
fi

# 1. 检查 .env 文件是否存在
echo -e "${CYAN}[1/6] 检查 .env 文件是否存在...${NC}"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}✗ .env 文件不存在：${ENV_FILE}${NC}"
    echo -e "${YELLOW}请先创建 .env 文件：${NC}"
    echo -e "  cp ${PROJECT_ROOT}/env.example ${ENV_FILE}"
    exit 1
else
    echo -e "${GREEN}✓ .env 文件存在${NC}"
fi
echo ""

# 2. 检查 www-data 用户是否存在
echo -e "${CYAN}[2/6] 检查服务用户是否存在...${NC}"
if ! id "$SERVICE_USER" &>/dev/null; then
    echo -e "${RED}✗ 用户 ${SERVICE_USER} 不存在${NC}"
    echo -e "${YELLOW}请确认 systemd 服务使用的用户${NC}"
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✓ 用户 ${SERVICE_USER} 存在${NC}"
    id "$SERVICE_USER"
fi
echo ""

# 3. 显示当前文件信息
echo -e "${CYAN}[3/6] 当前文件信息：${NC}"
ls -la "$ENV_FILE"
echo ""

# 获取当前所有者和权限
CURRENT_OWNER=$(stat -c '%U:%G' "$ENV_FILE" 2>/dev/null || echo "unknown")
CURRENT_PERMS=$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo "unknown")
CURRENT_UID=$(stat -c '%u' "$ENV_FILE" 2>/dev/null || echo "unknown")
CURRENT_GID=$(stat -c '%g' "$ENV_FILE" 2>/dev/null || echo "unknown")

SERVICE_UID=$(id -u "$SERVICE_USER" 2>/dev/null || echo "unknown")
SERVICE_GID=$(id -g "$SERVICE_USER" 2>/dev/null || echo "unknown")

echo -e "${BLUE}当前所有者：${CURRENT_OWNER} (UID:${CURRENT_UID}, GID:${CURRENT_GID})${NC}"
echo -e "${BLUE}当前权限：${CURRENT_PERMS}${NC}"
echo -e "${BLUE}服务用户：${SERVICE_USER} (UID:${SERVICE_UID}, GID:${SERVICE_GID})${NC}"
echo ""

# 4. 检查权限问题
echo -e "${CYAN}[4/6] 诊断权限问题...${NC}"
HAS_ISSUE=false

if [ "$CURRENT_UID" != "$SERVICE_UID" ] && [ "$CURRENT_UID" != "unknown" ] && [ "$SERVICE_UID" != "unknown" ]; then
    echo -e "${YELLOW}⚠ 文件所有者不是 ${SERVICE_USER}${NC}"
    HAS_ISSUE=true
fi

if [ "$CURRENT_PERMS" != "640" ] && [ "$CURRENT_PERMS" != "600" ] && [ "$CURRENT_PERMS" != "644" ]; then
    echo -e "${YELLOW}⚠ 文件权限可能不正确（当前：${CURRENT_PERMS}，推荐：640）${NC}"
    HAS_ISSUE=true
fi

# 测试读取权限
if [ "$CURRENT_UID" = "$SERVICE_UID" ] || [ "$CURRENT_GID" = "$SERVICE_GID" ]; then
    # 如果所有者或组匹配，检查权限
    if [ "$CURRENT_PERMS" = "600" ] || [ "$CURRENT_PERMS" = "640" ] || [ "$CURRENT_PERMS" = "644" ]; then
        echo -e "${GREEN}✓ 权限配置看起来正确${NC}"
    else
        echo -e "${YELLOW}⚠ 权限可能不足${NC}"
        HAS_ISSUE=true
    fi
else
    # 所有者不匹配，需要修复
    echo -e "${RED}✗ 文件所有者不匹配，需要修复${NC}"
    HAS_ISSUE=true
fi

# 测试实际读取权限
echo -e "${BLUE}测试读取权限...${NC}"
if sudo -u "$SERVICE_USER" test -r "$ENV_FILE" 2>/dev/null; then
    echo -e "${GREEN}✓ ${SERVICE_USER} 用户可以读取文件${NC}"
else
    echo -e "${RED}✗ ${SERVICE_USER} 用户无法读取文件${NC}"
    HAS_ISSUE=true
fi
echo ""

# 5. 修复权限
if [ "$HAS_ISSUE" = true ]; then
    echo -e "${CYAN}[5/6] 修复权限...${NC}"
    
    # 设置所有者
    chown "${SERVICE_USER}:${SERVICE_GROUP}" "$ENV_FILE"
    echo -e "${GREEN}✓ 已设置所有者：${SERVICE_USER}:${SERVICE_GROUP}${NC}"
    
    # 设置权限为 640
    chmod 640 "$ENV_FILE"
    echo -e "${GREEN}✓ 已设置权限：640${NC}"
    
    # 验证修复
    NEW_OWNER=$(stat -c '%U:%G' "$ENV_FILE")
    NEW_PERMS=$(stat -c '%a' "$ENV_FILE")
    
    if [ "$NEW_OWNER" = "${SERVICE_USER}:${SERVICE_GROUP}" ] && [ "$NEW_PERMS" = "640" ]; then
        echo -e "${GREEN}✓ 权限修复成功！${NC}"
    else
        echo -e "${RED}✗ 权限修复失败${NC}"
        exit 1
    fi
else
    echo -e "${CYAN}[5/6] 权限检查...${NC}"
    echo -e "${GREEN}✓ 权限配置正确，无需修复${NC}"
fi
echo ""

# 6. 最终验证
echo -e "${CYAN}[6/6] 最终验证...${NC}"
if sudo -u "$SERVICE_USER" test -r "$ENV_FILE" 2>/dev/null; then
    echo -e "${GREEN}✓ ${SERVICE_USER} 用户可以成功读取文件${NC}"
    
    # 显示修复后的文件信息
    echo ""
    echo -e "${BLUE}修复后的文件信息：${NC}"
    ls -la "$ENV_FILE"
    echo ""
    
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}权限诊断和修复完成！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}下一步操作：${NC}"
    echo -e "1. 重启服务：${YELLOW}sudo systemctl restart Platform-backend.service${NC}"
    echo -e "2. 检查状态：${YELLOW}sudo systemctl status Platform-backend.service${NC}"
    echo -e "3. 查看日志：${YELLOW}sudo journalctl -u Platform-backend.service -f${NC}"
else
    echo -e "${RED}✗ ${SERVICE_USER} 用户仍然无法读取文件${NC}"
    echo -e "${YELLOW}可能的原因：${NC}"
    echo -e "  - SELinux 或 AppArmor 限制"
    echo -e "  - 文件系统挂载选项限制"
    echo -e "  - systemd 服务配置中的安全限制"
    echo ""
    echo -e "${YELLOW}请检查：${NC}"
    echo -e "  - systemd 服务配置中的 ReadWritePaths"
    echo -e "  - SELinux 上下文：ls -Z ${ENV_FILE}"
    echo -e "  - 文件系统挂载选项：mount | grep $(df ${ENV_FILE} | tail -1 | awk '{print $1}')"
    exit 1
fi

