#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动环境配置生成脚本
根据当前系统自动判断环境模式，并生成推荐配置

功能特性：
1. 自动检测操作系统（Windows/Ubuntu/Linux）
   - Windows 系统 → 推荐开发模式（development）
   - Ubuntu 系统 → 推荐生产模式（production）
   - 其他 Linux → 默认开发模式（development）

2. 智能配置生成
   - 根据环境类型自动生成推荐配置值
   - 自动生成强随机 SECRET_KEY
   - 根据操作系统调整路径格式

3. 交互式配置编辑
   - 显示所有推荐配置值供查看
   - 支持交互式编辑重要配置项
   - 数据库URL分解编辑（分别输入用户名、密码、主机、端口、数据库名）
   - CORS域名逐个输入（自动验证格式）

4. RSA密钥自动管理
   - 自动检查RSA密钥文件是否存在
   - 如果不存在，自动生成2048位RSA密钥对
   - 根据操作系统自动设置正确的文件权限

5. 文件权限自动设置
   - Ubuntu系统：自动设置文件权限为600或640
   - 如果以root权限运行，自动设置所有者为www-data:www-data
   - Windows系统：提示确保文件不被共享

使用方法：
    基本使用（推荐）：
        python scripts/auto_generate_env_config.py
    
    强制指定环境模式：
        python scripts/auto_generate_env_config.py --env production
    
    指定输出文件：
        python scripts/auto_generate_env_config.py --output .env.production
    
    非交互模式（适合自动化）：
        python scripts/auto_generate_env_config.py --no-interactive

环境模式说明：
    - production/prod: 生产环境
      * 启用所有安全检查（CSRF、严格限流等）
      * 使用RS256算法（需要RSA密钥）
      * 启用Telegram通知
      * 使用HTTPS域名
    
    - development/dev: 开发环境
      * 关闭安全检查（便于调试）
      * 使用HS256算法（配置简单）
      * 关闭Telegram通知
      * 使用HTTP本地域名
    
    - test: 测试环境
      * 用于自动化测试
      * 必须关闭Telegram
      * 使用独立的测试数据库

配置项说明：
    必须修改的配置项（生产环境）：
        - DATABASE_URL: 数据库连接信息
        - BACKEND_CORS_ORIGINS: 生产环境域名（使用HTTPS）
        - FIRST_SUPERUSER_PASSWORD: 管理员密码（至少12字符）
    
    自动生成的配置项：
        - SECRET_KEY: 强随机密钥（自动生成）
        - RSA密钥: 如果使用RS256算法，自动检查并生成

注意事项：
    1. 生产环境必须修改所有标记为"必须修改"的配置项
    2. 确保配置文件权限安全（Ubuntu系统会自动设置）
    3. 不要将配置文件提交到版本控制系统
    4. 生产环境密码必须使用强密码（至少12字符）

依赖要求：
    - Python 3.7+
    - cryptography（如果使用RS256算法，用于生成RSA密钥）
      安装：pip install cryptography

作者：自动生成
创建时间：2025年
版本：1.0
"""

import argparse
import secrets
import os
import sys
import platform
import stat
import subprocess
import urllib.parse
from pathlib import Path
from datetime import datetime


# 不同环境的推荐配置
ENV_CONFIGS = {
    "production": {
        "PRODUCTION_ENV": "production",
        "SECRET_KEY": lambda: secrets.token_urlsafe(64),
        "JWT_ALGORITHM": "RS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "240",
        "RSA_PRIVATE_KEY_PATH": "/data/Platform/keys/private_key.pem",
        "RSA_PUBLIC_KEY_PATH": "/data/Platform/keys/public_key.pem",
        "DATABASE_URL": "mysql+aiomysql://root:kb7%24rL3d8%21tQ@127.0.0.1:3306/platform",
        "DB_POOL_SIZE": "15",
        "DB_MAX_OVERFLOW": "10",
        "DB_POOL_RECYCLE": "3600",
        "REDIS_HOST": "127.0.0.1",
        "REDIS_PORT": "6379",
        "REDIS_DB": "0",
        "REDIS_PASSWORD": "",
        "REDIS_MAX_CONNECTIONS": "30",
        "FRONTEND_PORT": "3310",
        "BACKEND_PORT": "8960",
        "LOGIN_URL": "https://client.btfrx.online",
        "BACKEND_CORS_ORIGINS": "https://btfrx.online,https://www.btfrx.online,https://client.btfrx.online",
        "FIRST_SUPERUSER": "admin",
        "FIRST_SUPERUSER_PASSWORD": "Your@StrongP@ssw0rd2025!",
        "API_RATE_LIMIT": "100",
        "LOGIN_RATE_LIMIT": "5",
        "MAX_UPLOAD_SIZE": "10485760",
        "ENABLE_CSRF": "true",
        "CSRF_TOKEN_EXPIRE_SECONDS": "3600",
        "MAX_CONCURRENT_SCHEDULED_TASKS": "2",
        "LOG_LEVEL": "INFO",
        "LOG_FILE": "logs/app.log",
        "LOG_MAX_BYTES": "10485760",
        "LOG_BACKUP_COUNT": "10",
        "AUDIT_LOG_RETENTION_DAYS": "90",
        "AUDIT_LOG_ARCHIVE": "false",
        "TIMEZONE": "Asia/Shanghai",
        "TELEGRAM_ENABLE": "true",
        "TELEGRAM_TOKEN": "8348688058:AAE0CXsgR4iNjzvcPjHOICQp8e3WSKJ5OtQ",
        "TELEGRAM_ADMIN": "5312177749",
        "TRACKING_BASE_URL": "https://client.btfrx.online",
        "WORKERS": "9",
        "PRELOAD_APP": "true",
        "MEMORY_GB": "8",
    },
    "development": {
        "PRODUCTION_ENV": "development",
        "SECRET_KEY": lambda: secrets.token_urlsafe(64),
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "120",
        "RSA_PRIVATE_KEY_PATH": "keys/private_key.pem",
        "RSA_PUBLIC_KEY_PATH": "keys/public_key.pem",
        "DATABASE_URL": "mysql+aiomysql://root:kb7%24rL3d8%21tQ@127.0.0.1:3306/platform",
        "DB_POOL_SIZE": "5",
        "DB_MAX_OVERFLOW": "3",
        "DB_POOL_RECYCLE": "3600",
        "REDIS_HOST": "127.0.0.1",
        "REDIS_PORT": "6379",
        "REDIS_DB": "0",
        "REDIS_PASSWORD": "",
        "REDIS_MAX_CONNECTIONS": "5",
        "FRONTEND_PORT": "3310",
        "BACKEND_PORT": "8960",
        "LOGIN_URL": "http://localhost:3310",
        "BACKEND_CORS_ORIGINS": "http://localhost:3310,http://127.0.0.1:3310",
        "FIRST_SUPERUSER": "admin",
        "FIRST_SUPERUSER_PASSWORD": "admin123",
        "API_RATE_LIMIT": "1000",
        "LOGIN_RATE_LIMIT": "100",
        "MAX_UPLOAD_SIZE": "52428800",
        "ENABLE_CSRF": "false",
        "CSRF_TOKEN_EXPIRE_SECONDS": "7200",
        "MAX_CONCURRENT_SCHEDULED_TASKS": "1",
        "LOG_LEVEL": "DEBUG",
        "LOG_FILE": "logs/app.log",
        "LOG_MAX_BYTES": "5242880",
        "LOG_BACKUP_COUNT": "3",
        "AUDIT_LOG_RETENTION_DAYS": "30",
        "AUDIT_LOG_ARCHIVE": "false",
        "TIMEZONE": "Asia/Shanghai",
        "TELEGRAM_ENABLE": "false",
        "TELEGRAM_TOKEN": "",
        "TELEGRAM_ADMIN": "",
        "TRACKING_BASE_URL": "http://localhost:3310",
        "WORKERS": "",
        "PRELOAD_APP": "false",
        "MEMORY_GB": "",
    },
    "test": {
        "PRODUCTION_ENV": "test",
        "SECRET_KEY": lambda: secrets.token_urlsafe(64),
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "RSA_PRIVATE_KEY_PATH": "keys/private_key.pem",
        "RSA_PUBLIC_KEY_PATH": "keys/public_key.pem",
        "DATABASE_URL": "mysql+aiomysql://test_user:test_pass@127.0.0.1:3306/platform_test",
        "DB_POOL_SIZE": "3",
        "DB_MAX_OVERFLOW": "2",
        "DB_POOL_RECYCLE": "1800",
        "REDIS_HOST": "127.0.0.1",
        "REDIS_PORT": "6379",
        "REDIS_DB": "15",
        "REDIS_PASSWORD": "",
        "REDIS_MAX_CONNECTIONS": "3",
        "FRONTEND_PORT": "3310",
        "BACKEND_PORT": "8960",
        "LOGIN_URL": "http://localhost:3310",
        "BACKEND_CORS_ORIGINS": "http://localhost:3310",
        "FIRST_SUPERUSER": "test_admin",
        "FIRST_SUPERUSER_PASSWORD": "test_password_123",
        "API_RATE_LIMIT": "1000",
        "LOGIN_RATE_LIMIT": "100",
        "MAX_UPLOAD_SIZE": "10485760",
        "ENABLE_CSRF": "false",
        "CSRF_TOKEN_EXPIRE_SECONDS": "3600",
        "MAX_CONCURRENT_SCHEDULED_TASKS": "1",
        "LOG_LEVEL": "DEBUG",
        "LOG_FILE": "logs/app.log",
        "LOG_MAX_BYTES": "1048576",
        "LOG_BACKUP_COUNT": "2",
        "AUDIT_LOG_RETENTION_DAYS": "7",
        "AUDIT_LOG_ARCHIVE": "false",
        "TIMEZONE": "Asia/Shanghai",
        "TELEGRAM_ENABLE": "false",
        "TELEGRAM_TOKEN": "",
        "TELEGRAM_ADMIN": "",
        "TRACKING_BASE_URL": "http://localhost:3310",
        "WORKERS": "",
        "PRELOAD_APP": "false",
        "MEMORY_GB": "",
    },
}

# 设置别名
ENV_CONFIGS["dev"] = ENV_CONFIGS["development"]
ENV_CONFIGS["prod"] = ENV_CONFIGS["production"]


def detect_os() -> tuple[str, str]:
    """
    检测当前操作系统
    
    功能说明：
        - 自动识别 Windows、Ubuntu 或其他 Linux 发行版
        - 返回操作系统名称和类型标识
    
    Returns:
        (os_name, os_type): 操作系统名称和类型
            - os_name: 操作系统显示名称（如 "Windows", "Ubuntu", "Linux"）
            - os_type: 操作系统类型标识（'windows', 'linux', 'ubuntu', 'other'）
    
    示例：
        >>> detect_os()
        ('Windows', 'windows')
        >>> detect_os()
        ('Ubuntu', 'ubuntu')
    """
    system = platform.system().lower()
    release = platform.release().lower()
    
    if system == "windows":
        return "Windows", "windows"
    elif system == "linux":
        # 尝试检测是否为Ubuntu
        try:
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release", "r", encoding="utf-8") as f:
                    content = f.read().lower()
                    if "ubuntu" in content:
                        return "Ubuntu", "ubuntu"
            # 检查是否为其他Linux发行版
            if os.path.exists("/etc/redhat-release"):
                return "RedHat/CentOS", "linux"
            return "Linux", "linux"
        except Exception:
            return "Linux", "linux"
    else:
        return system.capitalize(), "other"


def recommend_env(os_type: str) -> str:
    """
    根据操作系统类型推荐环境模式
    
    推荐规则：
        - Windows 系统 → 推荐开发模式（development）
        - Ubuntu 系统 → 推荐生产模式（production）
        - 其他系统 → 默认开发模式（development）
    
    Args:
        os_type: 操作系统类型（'windows', 'ubuntu', 'linux', 'other'）
    
    Returns:
        推荐的环境模式字符串（'development' 或 'production'）
    
    示例：
        >>> recommend_env('windows')
        'development'
        >>> recommend_env('ubuntu')
        'production'
    """
    if os_type == "windows":
        return "development"
    elif os_type == "ubuntu":
        return "production"
    else:
        return "development"  # 默认开发模式


def check_and_generate_rsa_keys(private_key_path: str, public_key_path: str, os_type: str) -> bool:
    """
    检查RSA密钥文件是否存在，如果不存在则自动生成
    
    功能说明：
        1. 检查私钥和公钥文件是否都存在
        2. 如果文件不存在，自动生成 2048 位 RSA 密钥对
        3. 根据操作系统自动设置正确的文件权限
        4. 支持绝对路径和相对路径
    
    文件权限设置：
        - Linux/Ubuntu: 私钥 600（仅所有者可读写），公钥 644（所有者可读写，其他可读）
        - Windows: 使用系统默认权限
    
    Args:
        private_key_path: 私钥文件路径（支持绝对路径和相对路径）
        public_key_path: 公钥文件路径（支持绝对路径和相对路径）
        os_type: 操作系统类型（'windows', 'ubuntu', 'linux', 'other'）
    
    Returns:
        bool: 
            - True: 密钥已存在或成功生成
            - False: 密钥生成失败（需要手动生成）
    
    异常处理：
        - 如果 cryptography 库未安装，会提示安装命令
        - 如果权限不足，会提示手动生成密钥的命令
        - 其他错误会显示详细的错误信息
    
    示例：
        >>> check_and_generate_rsa_keys('/data/Platform/keys/private_key.pem', 
        ...                            '/data/Platform/keys/public_key.pem', 'ubuntu')
        True
    """
    private_path = Path(private_key_path)
    public_path = Path(public_key_path)
    
    # 检查密钥文件是否都存在
    if private_path.exists() and public_path.exists():
        print(f"✅ RSA密钥文件已存在:")
        print(f"   私钥: {private_key_path}")
        print(f"   公钥: {public_key_path}")
        return True
    
    # 如果密钥文件不存在，尝试生成
    print(f"⚠️  RSA密钥文件不存在，正在自动生成...")
    
    # 确定输出目录
    if private_path.is_absolute():
        output_dir = private_path.parent
    else:
        # 相对路径，使用项目根目录
        project_root = Path(__file__).parent.parent
        output_dir = (project_root / private_path.parent).resolve()
    
    try:
        # 尝试导入cryptography库
        try:
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.backends import default_backend
        except ImportError:
            print(f"❌ 错误: 需要安装 cryptography 库")
            print(f"   请运行: pip install cryptography")
            print(f"   或者手动运行: python scripts/generate_rsa_keys.py --output-dir {output_dir}")
            return False
        
        # 生成密钥对
        print(f"   正在生成RSA密钥对（2048位）...")
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # 序列化私钥
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        
        # 获取并序列化公钥
        public_key = private_key.public_key()
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        # 创建输出目录
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存私钥
        private_path_full = output_dir / "private_key.pem"
        private_path_full.write_text(private_key_pem, encoding='utf-8')
        
        # 保存公钥
        public_path_full = output_dir / "public_key.pem"
        public_path_full.write_text(public_key_pem, encoding='utf-8')
        
        # 设置文件权限（Linux/Ubuntu）
        if os_type in ["ubuntu", "linux"]:
            try:
                os.chmod(private_path_full, stat.S_IRUSR | stat.S_IWUSR)  # 600
                os.chmod(public_path_full, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 644
                print(f"✅ 已设置密钥文件权限")
            except Exception as e:
                print(f"⚠️  设置文件权限时出错: {e}")
        
        print(f"✅ RSA密钥对已成功生成:")
        print(f"   私钥: {private_path_full}")
        print(f"   公钥: {public_path_full}")
        
        return True
        
    except PermissionError as e:
        print(f"❌ 权限错误: 无法创建密钥文件")
        print(f"   请检查目录权限或手动运行:")
        print(f"   python scripts/generate_rsa_keys.py --output-dir {output_dir}")
        return False
    except Exception as e:
        print(f"❌ 生成RSA密钥时出错: {e}")
        print(f"   请手动运行: python scripts/generate_rsa_keys.py --output-dir {output_dir}")
        return False


def set_file_permissions(file_path: Path, is_ubuntu: bool = False):
    """
    设置配置文件权限
    
    功能说明：
        - Windows 系统：提示确保文件不被共享
        - Ubuntu 系统：自动设置文件权限为 600（仅所有者可读写）
        - 如果以 root 权限运行，会尝试设置所有者为 www-data:www-data，权限为 640
    
    权限说明：
        - 600: 仅所有者可读写（推荐用于配置文件）
        - 640: 所有者可读写，组可读（适用于 www-data 用户运行的应用）
    
    Args:
        file_path: 配置文件路径（Path 对象）
        is_ubuntu: 是否为 Ubuntu 系统（bool）
    
    注意：
        - 设置所有者为 www-data 需要 root 权限
        - 如果 www-data 用户/组不存在，会跳过所有者设置
    """
    if not is_ubuntu:
        print(f"ℹ️  Windows系统：请确保 .env 文件不被共享")
        return
    
    try:
        # Ubuntu系统：设置文件权限为 600（仅所有者可读写）
        os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)
        print(f"✅ 已设置文件权限: chmod 600 {file_path}")
        
        # 尝试设置所有者为 www-data（如果存在）
        try:
            import pwd
            import grp
            
            # 检查是否存在 www-data 用户和组
            try:
                www_data_uid = pwd.getpwnam("www-data").pw_uid
                www_data_gid = grp.getgrnam("www-data").gr_gid
                
                # 检查当前用户是否有权限修改所有者
                current_uid = os.getuid()
                if current_uid == 0:  # root用户
                    os.chown(file_path, www_data_uid, www_data_gid)
                    # 设置为 640（所有者可读写，组可读）
                    os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
                    print(f"✅ 已设置文件所有者和权限:")
                    print(f"   chown www-data:www-data {file_path}")
                    print(f"   chmod 640 {file_path}")
                else:
                    print(f"⚠️  需要root权限来设置文件所有者为 www-data")
                    print(f"   请手动执行: sudo chown www-data:www-data {file_path}")
                    print(f"   然后执行: sudo chmod 640 {file_path}")
            except KeyError:
                print(f"ℹ️  www-data 用户/组不存在，跳过所有者设置")
                print(f"   文件权限已设置为 600（仅所有者可读写）")
        except ImportError:
            # Windows系统没有 pwd 和 grp 模块
            pass
    except Exception as e:
        print(f"⚠️  设置文件权限时出错: {e}")
        print(f"   请手动执行: chmod 600 {file_path}")


def display_recommended_config(config: dict, env: str):
    """
    显示推荐的配置值
    
    功能说明：
        - 按分类组织显示所有配置项
        - 突出显示需要特别注意的重要配置项
        - 对敏感信息进行部分隐藏处理
        - 显示配置项的当前值或默认值
    
    显示内容：
        - 环境配置、安全配置、JWT配置
        - 数据库配置、Redis配置、CORS配置
        - 管理员配置、API限流配置等
    
    重要提示：
        - 标记为 ⚠️ 的配置项必须修改
        - 标记为 💡 的配置项为可选配置
    
    Args:
        config: 配置字典，包含所有配置项及其值
        env: 环境类型（'production', 'development', 'test'）
    
    注意：
        - 敏感信息（密码、密钥等）会部分隐藏显示
        - 动态生成的配置（如 SECRET_KEY）会显示为 "[将自动生成]"
    """
    print(f"\n{'='*70}")
    print(f"📋 {env.upper()} 环境推荐配置值")
    print(f"{'='*70}\n")
    
    # 按分类组织配置
    categories = {
        "环境配置": ["PRODUCTION_ENV"],
        "安全配置": ["SECRET_KEY"],
        "JWT配置": ["JWT_ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES", "RSA_PRIVATE_KEY_PATH", "RSA_PUBLIC_KEY_PATH"],
        "数据库配置": ["DATABASE_URL", "DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_RECYCLE"],
        "Redis配置": ["REDIS_HOST", "REDIS_PORT", "REDIS_DB", "REDIS_PASSWORD", "REDIS_MAX_CONNECTIONS"],
        "端口配置": ["FRONTEND_PORT", "BACKEND_PORT"],
        "CORS配置": ["BACKEND_CORS_ORIGINS"],
        "管理员配置": ["FIRST_SUPERUSER", "FIRST_SUPERUSER_PASSWORD"],
        "API限流配置": ["API_RATE_LIMIT", "LOGIN_RATE_LIMIT"],
        "文件上传配置": ["MAX_UPLOAD_SIZE"],
        "CSRF配置": ["ENABLE_CSRF", "CSRF_TOKEN_EXPIRE_SECONDS"],
        "定时任务配置": ["MAX_CONCURRENT_SCHEDULED_TASKS"],
        "日志配置": ["LOG_LEVEL", "LOG_FILE", "LOG_MAX_BYTES", "LOG_BACKUP_COUNT"],
        "审计日志配置": ["AUDIT_LOG_RETENTION_DAYS", "AUDIT_LOG_ARCHIVE"],
        "时区配置": ["TIMEZONE"],
        "Telegram配置": ["TELEGRAM_ENABLE", "TELEGRAM_TOKEN", "TELEGRAM_ADMIN"],
        "追踪服务配置": ["TRACKING_BASE_URL"],
        "Gunicorn配置": ["WORKERS", "PRELOAD_APP", "MEMORY_GB"],
    }
    
    # 需要特别注意的配置项（标记为重要）
    important_configs = {
        "DATABASE_URL": "⚠️  必须修改：数据库连接信息",
        "BACKEND_CORS_ORIGINS": "⚠️  必须修改：生产环境域名（使用HTTPS）",
        "FIRST_SUPERUSER_PASSWORD": "⚠️  必须修改：管理员密码（至少12字符）",
        "FRONTEND_PORT": "💡 默认：前端端口 3310",
        "BACKEND_PORT": "💡 默认：后端端口 8960",
        "LOGIN_URL": "💡 默认：登录地址 https://client.btfrx.online（生产环境）",
        "TELEGRAM_TOKEN": "💡 可选：Telegram Bot Token",
        "TELEGRAM_ADMIN": "💡 可选：Telegram 管理员ID",
    }
    
    for category, keys in categories.items():
        print(f"\n【{category}】")
        print("-" * 70)
        for key in keys:
            if key in config:
                value = config[key]
                if callable(value):
                    value = "[将自动生成]"
                elif value == "":
                    value = "[留空，使用默认值]"
                elif len(str(value)) > 60:
                    # 长值截断显示
                    display_value = str(value)[:57] + "..."
                else:
                    display_value = str(value)
                
                # 敏感信息部分隐藏
                if key in ["SECRET_KEY", "FIRST_SUPERUSER_PASSWORD", "TELEGRAM_TOKEN", "DATABASE_URL"]:
                    if not callable(value) and value != "" and value != "[将自动生成]" and value != "[留空，使用默认值]":
                        if len(str(value)) > 20:
                            display_value = str(value)[:10] + "..." + str(value)[-5:]
                
                # 显示重要提示
                if key in important_configs:
                    print(f"  {key:35} = {display_value}")
                    print(f"    {important_configs[key]}")
                else:
                    print(f"  {key:35} = {display_value}")
    
    print(f"\n{'='*70}\n")


def parse_database_url(url: str) -> dict:
    """
    解析数据库URL
    
    Args:
        url: 数据库URL，格式：mysql+aiomysql://用户名:密码@主机:端口/数据库名
    
    Returns:
        包含各部分的字典
    """
    try:
        # 移除 mysql+aiomysql:// 前缀
        if url.startswith("mysql+aiomysql://"):
            url = url[18:]
        elif url.startswith("mysql://"):
            url = url[8:]
        
        # 分离认证信息和连接信息
        if "@" in url:
            auth_part, conn_part = url.split("@", 1)
            if ":" in auth_part:
                username, password = auth_part.split(":", 1)
                # 对密码进行URL解码（如果包含URL编码）
                password = urllib.parse.unquote(password)
            else:
                username, password = auth_part, ""
        else:
            username, password = "", ""
            conn_part = url
        
        # 分离主机端口和数据库名
        if "/" in conn_part:
            host_port, db_name = conn_part.split("/", 1)
        else:
            host_port, db_name = conn_part, ""
        
        # 分离主机和端口
        if ":" in host_port:
            host, port = host_port.split(":", 1)
        else:
            host, port = host_port, "3306"
        
        return {
            "username": username,
            "password": password,
            "host": host,
            "port": port,
            "database": db_name
        }
    except Exception:
        return {
            "username": "",
            "password": "",
            "host": "127.0.0.1",
            "port": "3306",
            "database": ""
        }


def build_database_url(parts: dict) -> str:
    """
    根据各个组成部分构建完整的数据库URL
    
    功能说明：
        - 将数据库连接的各个部分组合成完整的 URL 字符串
        - 自动处理用户名和密码的格式
        - 自动对密码中的特殊字符进行URL编码
        - 生成标准的 MySQL 连接 URL
    
    Args:
        parts: 包含数据库连接各部分的字典
            - username: 数据库用户名（可选）
            - password: 数据库密码（可选，特殊字符会自动URL编码）
            - host: 数据库主机地址（默认：127.0.0.1）
            - port: 数据库端口（默认：3306）
            - database: 数据库名称
    
    Returns:
        str: 完整的数据库URL字符串
            格式：mysql+aiomysql://用户名:密码@主机:端口/数据库名
            注意：密码中的特殊字符会自动进行URL编码
    
    示例：
        >>> parts = {
        ...     'username': 'root',
        ...     'password': 'kb7$rL3d8!tQ',
        ...     'host': '127.0.0.1',
        ...     'port': '3306',
        ...     'database': 'platform'
        ... }
        >>> build_database_url(parts)
        'mysql+aiomysql://root:kb7%24rL3d8%21tQ@127.0.0.1:3306/platform'
    """
    username = parts.get("username", "")
    password = parts.get("password", "")
    host = parts.get("host", "127.0.0.1")
    port = parts.get("port", "3306")
    database = parts.get("database", "")
    
    # 对密码进行URL编码（处理特殊字符）
    if password:
        password = urllib.parse.quote(password, safe='')
    
    if username and password:
        auth = f"{username}:{password}@"
    elif username:
        auth = f"{username}@"
    else:
        auth = ""
    
    return f"mysql+aiomysql://{auth}{host}:{port}/{database}"


def edit_database_url_interactive(current_url: str) -> str:
    """
    交互式编辑数据库URL（分解为各个部分）
    
    功能说明：
        - 将数据库URL分解为：用户名、密码、主机、端口、数据库名
        - 逐个提示用户输入或修改各个部分
        - 直接回车保持当前值不变
        - 自动构建完整的数据库URL
    
    使用场景：
        - 用户不想手动拼接复杂的数据库URL
        - 只需要修改部分信息（如密码或数据库名）
        - 更直观的配置方式
    
    Args:
        current_url: 当前的数据库URL字符串
            示例：mysql+aiomysql://root:password@127.0.0.1:3306/platform
    
    Returns:
        str: 新的数据库URL字符串
    
    交互提示：
        - 数据库用户名：显示当前用户名，可直接回车保持
        - 数据库密码：部分隐藏显示，输入新密码或回车保持
        - 数据库主机：显示当前主机，可直接回车保持
        - 数据库端口：显示当前端口，可直接回车保持
        - 数据库名称：显示当前数据库名，可直接回车保持
    """
    print("\n" + "="*70)
    print("📊 数据库连接配置（分解编辑）")
    print("="*70)
    print("提示：直接回车保持当前值，输入新值进行修改")
    print("="*70)
    
    parts = parse_database_url(current_url)
    
    print(f"\n当前数据库URL: {current_url[:60]}{'...' if len(current_url) > 60 else ''}\n")
    
    # 编辑各个部分
    new_username = input(f"数据库用户名 [{parts['username']}]: ").strip()
    if new_username:
        parts["username"] = new_username
    
    new_password = input(f"数据库密码 [{parts['password'][:5] + '***' if parts['password'] else '[空]'}]: ").strip()
    if new_password:
        parts["password"] = new_password
    
    new_host = input(f"数据库主机 [{parts['host']}]: ").strip()
    if new_host:
        parts["host"] = new_host
    
    new_port = input(f"数据库端口 [{parts['port']}]: ").strip()
    if new_port:
        parts["port"] = new_port
    
    new_database = input(f"数据库名称 [{parts['database']}]: ").strip()
    if new_database:
        parts["database"] = new_database
    
    new_url = build_database_url(parts)
    print(f"\n✅ 新的数据库URL: {new_url[:60]}{'...' if len(new_url) > 60 else ''}\n")
    
    return new_url


def edit_cors_origins_interactive(current_origins: str) -> str:
    """
    交互式编辑CORS域名（逐个输入）
    
    功能说明：
        - 逐个输入域名，每行一个
        - 自动验证域名格式（自动添加 https:// 前缀）
        - 自动合并新旧域名并去重
        - 支持生产环境（HTTPS）和开发环境（HTTP）
    
    使用场景：
        - 需要添加多个域名
        - 不想手动用逗号分隔
        - 需要验证域名格式
    
    Args:
        current_origins: 当前的CORS域名列表（逗号分隔的字符串）
            示例："https://btfrx.online,https://www.btfrx.online,https://client.btfrx.online"
    
    Returns:
        str: 新的CORS域名列表（逗号分隔的字符串）
    
    交互提示：
        - 显示当前域名列表
        - 逐个提示输入新域名
        - 输入空行或 'done' 完成输入
        - 自动验证并添加协议前缀（http:// 或 https://）
    
    格式验证：
        - 如果域名不以 http:// 或 https:// 开头，自动添加 https://
        - 生产环境建议使用 HTTPS
        - 开发环境可以使用 HTTP
    """
    print("\n" + "="*70)
    print("🌐 CORS域名配置（逐个输入）")
    print("="*70)
    print("提示：")
    print("  - 生产环境必须使用 HTTPS（https://btfrx.online）")
    print("  - 开发环境可以使用 HTTP（http://localhost:3310，默认前端端口）")
    print("  - 多个域名用逗号分隔，或逐个输入后按回车")
    print("  - 输入 'done' 完成输入")
    print("="*70)
    
    if current_origins:
        origins_list = [o.strip() for o in current_origins.split(",") if o.strip()]
        print(f"\n当前域名列表: {', '.join(origins_list)}\n")
    else:
        origins_list = []
        print("\n当前无域名配置\n")
    
    print("请逐个输入域名（每行一个，输入空行或 'done' 完成）：")
    new_origins = []
    
    while True:
        try:
            origin = input("域名: ").strip()
            if not origin or origin.lower() == "done":
                break
            if origin:
                # 验证格式
                if not origin.startswith("http://") and not origin.startswith("https://"):
                    print(f"  ⚠️  警告：域名应以 http:// 或 https:// 开头，已自动添加 https://")
                    origin = "https://" + origin
                new_origins.append(origin)
                print(f"  ✅ 已添加: {origin}")
        except KeyboardInterrupt:
            print("\n\n⚠️  输入已取消")
            break
    
    # 合并新旧域名
    if new_origins:
        if origins_list:
            # 合并并去重
            all_origins = list(set(origins_list + new_origins))
        else:
            all_origins = new_origins
    else:
        all_origins = origins_list
    
    result = ",".join(all_origins)
    print(f"\n✅ 最终域名列表: {result}\n")
    
    return result


def interactive_edit_config(config: dict) -> dict:
    """
    交互式编辑配置项
    
    功能说明：
        - 提供友好的交互式界面编辑配置项
        - 优先编辑重要配置项（数据库、密码、域名等）
        - 支持特殊编辑模式（数据库URL分解、域名逐个输入）
        - 支持跳过、查看列表、完成编辑等操作
    
    编辑模式：
        - 直接回车：保持当前值不变
        - 输入新值：更新配置项
        - 输入 'skip'：跳过剩余配置项
        - 输入 'list'：重新显示所有配置值
        - 输入 'done'：完成编辑
    
    特殊编辑：
        - DATABASE_URL：输入 'edit' 进入分解编辑模式
        - BACKEND_CORS_ORIGINS：输入 'edit' 进入逐个输入模式
    
    Args:
        config: 原始配置字典，包含所有配置项及其值
    
    Returns:
        dict: 修改后的配置字典
    
    编辑流程：
        1. 先编辑重要配置项（数据库、密码、域名等）
        2. 询问是否编辑其他配置项
        3. 如果选择是，逐个编辑其他配置项
        4. 返回修改后的配置字典
    """
    print("\n" + "="*70)
    print("✏️  配置编辑模式")
    print("="*70)
    print("提示：")
    print("  - 直接回车保持当前值不变")
    print("  - 输入 'skip' 跳过剩余配置项")
    print("  - 输入 'list' 重新显示所有配置值")
    print("  - 输入 'done' 完成编辑")
    print("="*70 + "\n")
    
    # 重要配置项列表（优先显示）
    important_keys = [
        "DATABASE_URL",
        "SECRET_KEY",
        "FIRST_SUPERUSER_PASSWORD",
        "BACKEND_CORS_ORIGINS",
        "TELEGRAM_TOKEN",
        "TELEGRAM_ADMIN",
        "RSA_PRIVATE_KEY_PATH",
        "RSA_PUBLIC_KEY_PATH",
    ]
    
    # 其他配置项
    other_keys = [k for k in config.keys() if k not in important_keys and k != "PRODUCTION_ENV"]
    
    edited_config = config.copy()
    skip_remaining = False
    
    # 先编辑重要配置项
    print("【重要配置项】")
    print("-" * 70)
    for key in important_keys:
        if skip_remaining:
            break
        
        if key not in edited_config:
            continue
        
        current_value = edited_config[key]
        if callable(current_value):
            display_value = "[将自动生成]"
        elif current_value == "":
            display_value = "[留空]"
        else:
            display_value = str(current_value)
            # 敏感信息部分隐藏
            if key in ["SECRET_KEY", "FIRST_SUPERUSER_PASSWORD", "TELEGRAM_TOKEN", "DATABASE_URL"]:
                if len(display_value) > 20:
                    display_value = display_value[:10] + "..." + display_value[-5:]
        
        while True:
            try:
                # 特殊处理：数据库URL和CORS域名
                if key == "DATABASE_URL":
                    print(f"\n💡 提示：可以输入 'edit' 进入分解编辑模式（分别输入用户名、密码、主机、端口、数据库名）")
                    user_input = input(f"{key:35} [{display_value}]: ").strip()
                    
                    if user_input.lower() == "edit":
                        # 进入分解编辑模式
                        new_url = edit_database_url_interactive(edited_config[key])
                        edited_config[key] = new_url
                        print(f"  ✅ 已更新: {key}")
                        break
                elif key == "BACKEND_CORS_ORIGINS":
                    print(f"\n💡 提示：可以输入 'edit' 进入逐个输入模式（逐个输入域名）")
                    user_input = input(f"{key:35} [{display_value}]: ").strip()
                    
                    if user_input.lower() == "edit":
                        # 进入逐个输入模式
                        new_origins = edit_cors_origins_interactive(edited_config[key])
                        edited_config[key] = new_origins
                        print(f"  ✅ 已更新: {key}")
                        break
                else:
                    user_input = input(f"{key:35} [{display_value}]: ").strip()
                
                if user_input == "":
                    # 保持原值（如果是callable，保持callable；否则保持原值）
                    # 如果原值是callable，用户回车表示保持自动生成
                    if callable(edited_config[key]):
                        # 保持callable，稍后会生成
                        pass
                    break
                elif user_input.lower() == "skip":
                    skip_remaining = True
                    break
                elif user_input.lower() == "list":
                    display_recommended_config(edited_config, edited_config.get("PRODUCTION_ENV", "unknown"))
                    continue
                elif user_input.lower() == "done":
                    skip_remaining = True
                    break
                else:
                    # 更新值
                    edited_config[key] = user_input
                    print(f"  ✅ 已更新: {key} = {user_input[:50]}{'...' if len(user_input) > 50 else ''}")
                    break
            except KeyboardInterrupt:
                print("\n\n⚠️  编辑已取消")
                return config
            except Exception as e:
                print(f"  ❌ 输入错误: {e}")
                continue
    
    if not skip_remaining:
        # 询问是否编辑其他配置项
        print("\n" + "-" * 70)
        edit_others = input("是否编辑其他配置项？(y/n，默认n): ").strip().lower()
        
        if edit_others == "y":
            print("\n【其他配置项】")
            print("-" * 70)
            for key in other_keys:
                current_value = edited_config[key]
                if current_value == "":
                    display_value = "[留空，使用默认值]"
                else:
                    display_value = str(current_value)
                
                while True:
                    try:
                        user_input = input(f"{key:35} [{display_value}]: ").strip()
                        
                        if user_input == "":
                            break
                        elif user_input.lower() == "skip":
                            skip_remaining = True
                            break
                        elif user_input.lower() == "list":
                            display_recommended_config(edited_config, edited_config.get("PRODUCTION_ENV", "unknown"))
                            continue
                        elif user_input.lower() == "done":
                            skip_remaining = True
                            break
                        else:
                            edited_config[key] = user_input
                            print(f"  ✅ 已更新: {key} = {user_input[:50]}{'...' if len(user_input) > 50 else ''}")
                            break
                    except KeyboardInterrupt:
                        print("\n\n⚠️  编辑已取消")
                        return config
                    except Exception as e:
                        print(f"  ❌ 输入错误: {e}")
                        continue
                
                if skip_remaining:
                    break
    
    print("\n✅ 配置编辑完成！\n")
    return edited_config


def generate_config(env: str, output_file: str = None, os_type: str = None, config: dict = None) -> str:
    """
    根据环境类型生成配置
    
    Args:
        env: 环境类型 (production, development, test)
        output_file: 输出文件路径，如果为None则返回配置字符串
        os_type: 操作系统类型，用于调整路径等配置
        config: 可选的配置字典，如果提供则使用此配置而不是默认配置
    
    Returns:
        配置内容字符串
    """
    env_lower = env.lower()
    
    if env_lower not in ENV_CONFIGS:
        raise ValueError(f"不支持的环境类型: {env}。支持的类型: production/prod, development/dev, test")
    
    # 如果提供了自定义配置，使用它；否则使用默认配置
    if config is None:
        config = ENV_CONFIGS[env_lower].copy()
    
    # 根据操作系统调整路径
    if os_type == "windows" and env_lower in ["development", "dev"]:
        # Windows开发环境使用相对路径
        if "RSA_PRIVATE_KEY_PATH" in config:
            config["RSA_PRIVATE_KEY_PATH"] = "keys/private_key.pem"
        if "RSA_PUBLIC_KEY_PATH" in config:
            config["RSA_PUBLIC_KEY_PATH"] = "keys/public_key.pem"
    
    # 处理需要动态生成的配置
    if callable(config.get("SECRET_KEY")):
        # 自动生成强随机 SECRET_KEY
        config["SECRET_KEY"] = config["SECRET_KEY"]()
        # 注意：这里不打印，因为可能是在生成文件时调用，会在主函数中统一提示
    
    # 生成配置内容
    lines = [
        "# ==============================================================================",
        f"# 环境配置文件 - {env.upper()} 环境",
        "# ==============================================================================",
        f"# 此文件由 scripts/auto_generate_env_config.py 自动生成",
        f"# 环境类型: {env}",
        f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# 操作系统: {os_type or '未知'}",
        "# ==============================================================================",
        "",
    ]
    
    # 按分类组织配置
    categories = {
        "环境配置": ["PRODUCTION_ENV"],
        "安全配置": ["SECRET_KEY"],
        "JWT配置": ["JWT_ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES", "RSA_PRIVATE_KEY_PATH", "RSA_PUBLIC_KEY_PATH"],
        "数据库配置": ["DATABASE_URL", "DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_RECYCLE"],
        "Redis配置": ["REDIS_HOST", "REDIS_PORT", "REDIS_DB", "REDIS_PASSWORD", "REDIS_MAX_CONNECTIONS"],
        "端口配置": ["FRONTEND_PORT", "BACKEND_PORT"],
        "CORS配置": ["BACKEND_CORS_ORIGINS"],
        "管理员配置": ["FIRST_SUPERUSER", "FIRST_SUPERUSER_PASSWORD"],
        "API限流配置": ["API_RATE_LIMIT", "LOGIN_RATE_LIMIT"],
        "文件上传配置": ["MAX_UPLOAD_SIZE"],
        "CSRF配置": ["ENABLE_CSRF", "CSRF_TOKEN_EXPIRE_SECONDS"],
        "定时任务配置": ["MAX_CONCURRENT_SCHEDULED_TASKS"],
        "日志配置": ["LOG_LEVEL", "LOG_FILE", "LOG_MAX_BYTES", "LOG_BACKUP_COUNT"],
        "审计日志配置": ["AUDIT_LOG_RETENTION_DAYS", "AUDIT_LOG_ARCHIVE"],
        "时区配置": ["TIMEZONE"],
        "Telegram配置": ["TELEGRAM_ENABLE", "TELEGRAM_TOKEN", "TELEGRAM_ADMIN"],
        "追踪服务配置": ["TRACKING_BASE_URL"],
        "Gunicorn配置": ["WORKERS", "PRELOAD_APP", "MEMORY_GB"],
    }
    
    for category, keys in categories.items():
        lines.append(f"# ==============================================================================")
        lines.append(f"# {category}")
        lines.append(f"# ==============================================================================")
        
        for key in keys:
            if key in config:
                value = config[key]
                if value == "":
                    # 空值不输出
                    lines.append(f"# {key}=（留空，使用默认值）")
                else:
                    lines.append(f"{key}={value}")
        
        lines.append("")
    
    # 添加使用说明
    lines.extend([
        "# ==============================================================================",
        "# 使用说明",
        "# ==============================================================================",
        "# 1. 请根据实际情况修改以下配置项：",
        "#    - DATABASE_URL: 数据库连接信息",
        "#    - SECRET_KEY: 生产环境请使用强随机密钥（已自动生成）",
        "#    - FIRST_SUPERUSER_PASSWORD: 管理员密码",
        "#    - BACKEND_CORS_ORIGINS: 跨域来源（生产环境必须设置，使用HTTPS）",
        "#    - LOGIN_URL: 登录地址（生产环境：https://client.btfrx.online）",
        "#    - FRONTEND_PORT: 前端端口（默认：3310）",
        "#    - BACKEND_PORT: 后端端口（默认：8960）",
        "#    - TELEGRAM_TOKEN 和 TELEGRAM_ADMIN: 如果启用Telegram",
        "#    - RSA密钥路径: 如果使用RS256算法，请确保密钥文件存在",
        "",
        "# 2. 生产环境必须设置：",
        "#    - SECRET_KEY（强随机密钥，至少32字符，已自动生成）",
        "#    - DATABASE_URL（生产数据库，强密码）",
        "#    - BACKEND_CORS_ORIGINS（不包含localhost，使用HTTPS）",
        "#    - FIRST_SUPERUSER_PASSWORD（至少12字符，不是admin123）",
        "",
        "# 3. 测试环境注意事项：",
        "#    - TELEGRAM_ENABLE 必须为 false",
        "#    - 使用独立的测试数据库",
        "#    - 使用独立的Redis数据库（REDIS_DB=15）",
        "",
        "# 4. 文件权限设置：",
    ])
    
    if os_type == "ubuntu":
        lines.extend([
            "#    - Ubuntu系统：文件权限已自动设置为 600 或 640",
            "#    - 如果使用 www-data 用户运行，请执行：",
            "#      sudo chown www-data:www-data <配置文件路径>",
            "#      sudo chmod 640 <配置文件路径>",
        ])
    else:
        lines.extend([
            "#    - Windows系统：确保文件不被共享",
            "#    - Linux系统：chmod 600 <配置文件路径>",
        ])
    
    lines.append("# ==============================================================================")
    
    content = "\n".join(lines)
    
    # 如果指定了输出文件，写入文件
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        
        # 设置文件权限（如果是Ubuntu系统）
        is_ubuntu = os_type == "ubuntu"
        set_file_permissions(output_path, is_ubuntu)
        
        print(f"✅ 配置已生成: {output_file}")
        print(f"   环境类型: {env}")
        print(f"   操作系统: {os_type or '未知'}")
        print(f"   请根据实际情况修改配置项")
    else:
        print(content)
    
    return content


def interactive_select_env(recommended_env: str) -> str:
    """
    交互式选择环境模式
    
    功能说明：
        - 显示系统推荐的环境模式
        - 提供三个选项：开发模式、生产模式、测试模式
        - 支持直接回车使用推荐值
        - 验证用户输入的有效性
    
    环境模式说明：
        - development (开发模式)：用于本地开发，配置宽松，便于调试
        - production (生产模式)：用于生产环境，配置严格，安全性高
        - test (测试模式)：用于自动化测试，使用独立数据库
    
    Args:
        recommended_env: 系统推荐的环境模式字符串
            - 'development'：开发模式
            - 'production'：生产模式
            - 'test'：测试模式
    
    Returns:
        str: 用户选择的环境模式字符串
    
    交互提示：
        - 显示推荐的环境模式
        - 显示三个选项及说明
        - 提示可以直接回车使用推荐值
        - 验证输入的有效性（1、2、3 或回车）
    """
    print(f"\n推荐环境模式: {recommended_env.upper()}")
    print("请选择环境模式：")
    print("  1. development (开发模式)")
    print("  2. production (生产模式)")
    print("  3. test (测试模式)")
    print(f"  默认: {recommended_env} (直接回车)")
    
    while True:
        choice = input("\n请输入选项 (1/2/3) 或直接回车使用推荐值: ").strip()
        
        if not choice:
            return recommended_env
        
        if choice == "1":
            return "development"
        elif choice == "2":
            return "production"
        elif choice == "3":
            return "test"
        else:
            print("❌ 无效选项，请输入 1、2 或 3")


def main():
    parser = argparse.ArgumentParser(
        description="自动环境配置生成脚本\n"
                    "功能：根据当前系统自动判断环境模式并生成推荐配置\n"
                    "特性：自动检测操作系统、推荐环境模式、生成配置文件、设置权限、检查RSA密钥",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 自动检测系统并生成配置（推荐，交互式）
  python scripts/auto_generate_env_config.py
  
  # 强制指定环境模式
  python scripts/auto_generate_env_config.py --env production
  
  # 指定输出文件
  python scripts/auto_generate_env_config.py --output .env.production
  
  # 非交互模式（使用推荐值，不询问用户）
  python scripts/auto_generate_env_config.py --no-interactive
  
  # 组合使用：生产环境 + 非交互模式 + 指定输出文件
  python scripts/auto_generate_env_config.py --env production --output .env.prod --no-interactive

功能说明:
  - 自动检测操作系统（Windows/Ubuntu/Linux）
  - 根据系统推荐环境模式（Windows→开发，Ubuntu→生产）
  - 显示所有推荐配置值供查看和编辑
  - 支持交互式编辑配置（数据库URL分解、域名逐个输入等）
  - 自动检查并生成RSA密钥（如果使用RS256算法）
  - 自动设置文件权限（Ubuntu系统）
        """
    )
    
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        choices=["production", "prod", "development", "dev", "test"],
        help="环境类型（可选）\n"
             "  - production/prod: 生产环境（启用所有安全检查）\n"
             "  - development/dev: 开发环境（配置宽松，便于调试）\n"
             "  - test: 测试环境（用于自动化测试）\n"
             "如果不指定，将根据操作系统自动推荐"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default=".env",
        help="输出文件路径（默认: .env）\n"
             "示例: .env, .env.production, .env.development"
    )
    
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="非交互模式，使用系统推荐的环境模式，不询问用户\n"
             "适用于自动化脚本和CI/CD环境"
    )
    
    args = parser.parse_args()
    
    try:
        # 检测操作系统
        os_name, os_type = detect_os()
        print(f"🔍 检测到操作系统: {os_name} ({os_type})")
        
        # 推荐环境模式
        recommended_env = recommend_env(os_type)
        print(f"💡 系统推荐环境模式: {recommended_env.upper()}")
        
        # 确定使用的环境模式
        if args.env:
            env = args.env
            print(f"📝 使用指定的环境模式: {env.upper()}")
        elif args.no_interactive:
            env = recommended_env
            print(f"📝 使用推荐的环境模式: {env.upper()} (非交互模式)")
        else:
            # 交互式选择
            env = interactive_select_env(recommended_env)
            print(f"📝 已选择环境模式: {env.upper()}")
        
        # 准备配置
        env_lower = env.lower()
        config = ENV_CONFIGS[env_lower].copy()
        
        # 根据操作系统调整路径
        if os_type == "windows" and env_lower in ["development", "dev"]:
            if "RSA_PRIVATE_KEY_PATH" in config:
                config["RSA_PRIVATE_KEY_PATH"] = "keys/private_key.pem"
            if "RSA_PUBLIC_KEY_PATH" in config:
                config["RSA_PUBLIC_KEY_PATH"] = "keys/public_key.pem"
        
        # 处理需要动态生成的配置（先不生成，等用户确认后再生成）
        # 暂时保留 lambda，在显示时特殊处理
        
        # 显示推荐配置值
        if not args.no_interactive:
            display_recommended_config(config, env)
            
            # 询问是否编辑配置
            edit_choice = input("是否要编辑这些配置值？(y/n，默认n): ").strip().lower()
            
            if edit_choice == "y":
                # 在编辑前，先处理动态生成的配置（生成一个临时值用于显示和编辑）
                if callable(config.get("SECRET_KEY")):
                    # 生成一个临时值用于编辑，但记住它是自动生成的
                    temp_secret = config["SECRET_KEY"]()
                    config["SECRET_KEY"] = temp_secret
                    print(f"✅ SECRET_KEY 已自动生成（64字符强随机密钥）")
                    print(f"   提示：如果不需要修改，直接回车保持自动生成的值")
                
                # 交互式编辑配置
                config = interactive_edit_config(config)
            
            # 编辑完成后，如果 SECRET_KEY 没有被用户修改（仍然是自动生成的值），保持它
            # 如果用户修改了，使用用户的值
            # 这里不需要特殊处理，因为用户要么修改了，要么保持原值
            
            # 确保所有动态配置都已生成
            if callable(config.get("SECRET_KEY")):
                # 自动生成强随机 SECRET_KEY
                config["SECRET_KEY"] = config["SECRET_KEY"]()
                print(f"✅ SECRET_KEY 已自动生成（64字符强随机密钥）")
        else:
            # 非交互模式，直接生成动态配置
            if callable(config.get("SECRET_KEY")):
                # 自动生成强随机 SECRET_KEY
                config["SECRET_KEY"] = config["SECRET_KEY"]()
                print(f"✅ SECRET_KEY 已自动生成（64字符强随机密钥）")
        
        # 检查并生成RSA密钥（如果使用RS256算法）
        if config.get("JWT_ALGORITHM") == "RS256":
            private_key_path = config.get("RSA_PRIVATE_KEY_PATH", "")
            public_key_path = config.get("RSA_PUBLIC_KEY_PATH", "")
            
            if private_key_path and public_key_path:
                print(f"\n🔐 检查RSA密钥文件...")
                keys_generated = check_and_generate_rsa_keys(private_key_path, public_key_path, os_type)
                if not keys_generated:
                    print(f"⚠️  警告: RSA密钥生成失败，请手动生成密钥文件")
                    key_dir = Path(private_key_path).parent
                    if not key_dir.is_absolute():
                        # 相对路径，使用项目根目录
                        project_root = Path(__file__).parent.parent
                        key_dir = project_root / key_dir
                    print(f"   运行: python scripts/generate_rsa_keys.py --output-dir {key_dir}")
        
        # 生成配置
        print(f"\n🚀 正在生成配置文件...")
        
        # 确保 SECRET_KEY 已生成（如果还没有生成）
        if callable(config.get("SECRET_KEY")):
            config["SECRET_KEY"] = config["SECRET_KEY"]()
            if not args.no_interactive:
                print(f"✅ SECRET_KEY 已自动生成（64字符强随机密钥）")
        
        generate_config(env, args.output, os_type, config)
        
        # 输出后续建议
        print(f"\n📋 后续步骤：")
        print(f"   1. 检查并修改生成的配置文件: {args.output}")
        
        # 提示 SECRET_KEY 已自动生成
        if config.get("SECRET_KEY"):
            secret_key = config.get("SECRET_KEY", "")
            if len(secret_key) >= 32:
                print(f"   2. SECRET_KEY 已自动生成（强随机密钥，{len(secret_key)}字符）")
                print(f"      ✅ 无需手动设置，已包含在配置文件中")
        
        if env.lower() in ["production", "prod"]:
            print(f"   3. 确保以下配置已正确设置：")
            print(f"      - DATABASE_URL: 生产数据库连接")
            print(f"      - BACKEND_CORS_ORIGINS: 生产域名（使用HTTPS）")
            print(f"      - FIRST_SUPERUSER_PASSWORD: 强密码（至少12字符）")
            print(f"      - TELEGRAM_TOKEN 和 TELEGRAM_ADMIN: 如果启用Telegram")
            env_config = ENV_CONFIGS.get(env.lower(), {})
            if env_config.get("JWT_ALGORITHM") == "RS256":
                print(f"      - RSA密钥文件: 确保密钥文件存在")
        
        if os_type == "ubuntu":
            print(f"   4. Ubuntu系统权限设置：")
            print(f"      - 文件权限已自动设置")
            print(f"      - 如果使用 www-data 用户运行，可能需要：")
            print(f"        sudo chown www-data:www-data {args.output}")
            print(f"        sudo chmod 640 {args.output}")
        
        print(f"\n✅ 配置生成完成！")
        
    except KeyboardInterrupt:
        print(f"\n\n❌ 用户取消操作")
        return 1
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
