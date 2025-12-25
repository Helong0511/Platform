#!/bin/bash
# 修复 RSA 密钥文件权限脚本
# 用于 Ubuntu 生产环境
# 使用方法: sudo bash scripts/fix_rsa_keys_permissions.sh

set -e

echo "=========================================="
echo "RSA 密钥文件权限修复脚本"
echo "=========================================="

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then 
    echo "错误: 请使用 sudo 运行此脚本"
    exit 1
fi

# 项目路径
PROJECT_DIR="/data/Platform"
KEYS_DIR="$PROJECT_DIR/keys"
PRIVATE_KEY="$KEYS_DIR/private_key.pem"
PUBLIC_KEY="$KEYS_DIR/public_key.pem"

echo ""
echo "检查密钥文件..."

# 检查密钥目录是否存在
if [ ! -d "$KEYS_DIR" ]; then
    echo "错误: 密钥目录不存在: $KEYS_DIR"
    echo "请先运行: python3 scripts/generate_rsa_keys.py --output-dir $KEYS_DIR"
    exit 1
fi

# 检查私钥文件是否存在
if [ ! -f "$PRIVATE_KEY" ]; then
    echo "错误: 私钥文件不存在: $PRIVATE_KEY"
    echo "请先运行: python3 scripts/generate_rsa_keys.py --output-dir $KEYS_DIR"
    exit 1
fi

# 检查公钥文件是否存在
if [ ! -f "$PUBLIC_KEY" ]; then
    echo "错误: 公钥文件不存在: $PUBLIC_KEY"
    echo "请先运行: python3 scripts/generate_rsa_keys.py --output-dir $KEYS_DIR"
    exit 1
fi

echo "✓ 密钥文件存在"
echo ""

# 显示当前权限
echo "当前权限："
ls -la "$PRIVATE_KEY"
ls -la "$PUBLIC_KEY"
echo ""

# 设置密钥目录权限
echo "设置密钥目录权限..."
chown -R www-data:www-data "$KEYS_DIR"
chmod 750 "$KEYS_DIR"
echo "✓ 密钥目录权限已设置: 750 (www-data:www-data)"
echo ""

# 设置私钥文件权限（仅所有者可读）
echo "设置私钥文件权限..."
chown www-data:www-data "$PRIVATE_KEY"
chmod 600 "$PRIVATE_KEY"
echo "✓ 私钥文件权限已设置: 600 (www-data:www-data)"
echo ""

# 设置公钥文件权限（所有人可读）
echo "设置公钥文件权限..."
chown www-data:www-data "$PUBLIC_KEY"
chmod 644 "$PUBLIC_KEY"
echo "✓ 公钥文件权限已设置: 644 (www-data:www-data)"
echo ""

# 验证权限
echo "验证权限..."
echo "私钥文件权限："
ls -la "$PRIVATE_KEY"
echo ""
echo "公钥文件权限："
ls -la "$PUBLIC_KEY"
echo ""

# 测试 www-data 用户是否可以读取
echo "测试 www-data 用户是否可以读取私钥..."
if sudo -u www-data test -r "$PRIVATE_KEY"; then
    echo "✓ www-data 用户可以读取私钥文件"
else
    echo "✗ 警告: www-data 用户无法读取私钥文件"
    exit 1
fi

echo ""
echo "=========================================="
echo "权限修复完成！"
echo "=========================================="
echo ""
echo "建议重启服务以应用更改："
echo "  sudo systemctl restart Platform-backend.service"
echo ""

