#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置验证脚本
用于检查生产环境配置是否完整和正确

使用方法：
    python scripts/check_config.py
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv(override=True)

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_success(message):
    print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")

def print_error(message):
    print(f"{Colors.RED}❌ {message}{Colors.RESET}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.RESET}")

def print_info(message):
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.RESET}")

def check_required(key, description):
    """检查必填配置项"""
    value = os.getenv(key)
    if not value or not value.strip():
        print_error(f"{key}: {description} - 未设置")
        return False
    print_success(f"{key}: 已设置")
    return True

def check_production():
    """检查是否为生产环境"""
    env = os.getenv("PRODUCTION_ENV", "").lower()
    if env not in ["production", "prod"]:
        print_warning(f"PRODUCTION_ENV: 当前为 '{env}'，不是生产环境")
        return False
    print_success(f"PRODUCTION_ENV: 生产环境")
    return True

def check_secret_key():
    """检查SECRET_KEY"""
    secret_key = os.getenv("SECRET_KEY", "")
    if not secret_key:
        print_error("SECRET_KEY: 未设置")
        return False
    
    if len(secret_key) < 32:
        print_error(f"SECRET_KEY: 长度不足32字符（当前: {len(secret_key)}字符）")
        return False
    
    # 检查是否为默认值或示例值
    default_values = [
        "your-secret-key-here",
        "your-fixed-secret-key-here",
        "change-this-to-a-random-string"
    ]
    if any(default in secret_key.lower() for default in default_values):
        print_warning("SECRET_KEY: 可能使用了示例值，请更换为随机字符串")
        return False
    
    print_success(f"SECRET_KEY: 长度符合要求（{len(secret_key)}字符）")
    return True

def check_database():
    """检查数据库配置"""
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print_error("DATABASE_URL: 未设置")
        return False
    
    # 检查是否包含默认密码
    if "He800407" in database_url or "admin123" in database_url:
        print_warning("DATABASE_URL: 可能包含默认密码，生产环境建议使用强密码")
    
    # 检查格式
    if not database_url.startswith("mysql+aiomysql://"):
        print_warning("DATABASE_URL: 格式可能不正确，应为 mysql+aiomysql://...")
    
    print_success("DATABASE_URL: 已设置")
    return True

def check_cors():
    """检查CORS配置"""
    cors = os.getenv("BACKEND_CORS_ORIGINS", "")
    if not cors:
        print_error("BACKEND_CORS_ORIGINS: 未设置")
        return False
    
    cors_lower = cors.lower()
    if "localhost" in cors_lower or "127.0.0.1" in cors_lower:
        print_error("BACKEND_CORS_ORIGINS: 包含 localhost 或 127.0.0.1，生产环境不允许")
        return False
    
    # 检查是否使用HTTPS
    origins = [origin.strip() for origin in cors.split(",")]
    http_origins = [origin for origin in origins if origin.startswith("http://")]
    if http_origins:
        print_warning(f"BACKEND_CORS_ORIGINS: 以下域名使用HTTP，生产环境建议使用HTTPS: {', '.join(http_origins)}")
    
    print_success("BACKEND_CORS_ORIGINS: 已设置")
    return True

def check_admin_password():
    """检查管理员密码"""
    password = os.getenv("FIRST_SUPERUSER_PASSWORD", "")
    if not password:
        print_error("FIRST_SUPERUSER_PASSWORD: 未设置")
        return False
    
    if len(password) < 12:
        print_error(f"FIRST_SUPERUSER_PASSWORD: 长度不足12字符（当前: {len(password)}字符）")
        return False
    
    if password == "admin123":
        print_error("FIRST_SUPERUSER_PASSWORD: 不能使用默认密码 'admin123'")
        return False
    
    # 检查密码强度
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
    
    strength_issues = []
    if not has_upper:
        strength_issues.append("缺少大写字母")
    if not has_lower:
        strength_issues.append("缺少小写字母")
    if not has_digit:
        strength_issues.append("缺少数字")
    if not has_special:
        strength_issues.append("缺少特殊字符")
    
    if strength_issues:
        print_warning(f"FIRST_SUPERUSER_PASSWORD: 密码强度建议提升（{', '.join(strength_issues)}）")
    else:
        print_success("FIRST_SUPERUSER_PASSWORD: 密码强度良好")
    
    print_success(f"FIRST_SUPERUSER_PASSWORD: 长度符合要求（{len(password)}字符）")
    return True

def check_telegram():
    """检查Telegram配置"""
    enabled = os.getenv("TELEGRAM_ENABLE", "true").lower()
    if enabled not in ["true", "1", "yes"]:
        print_info("TELEGRAM_ENABLE: 已禁用，跳过Telegram配置检查")
        return True
    
    token = os.getenv("TELEGRAM_TOKEN", "")
    admin = os.getenv("TELEGRAM_ADMIN", "")
    
    if not token:
        print_warning("TELEGRAM_TOKEN: 未设置（Telegram功能已启用但未配置Token）")
        return False
    
    if not admin:
        print_warning("TELEGRAM_ADMIN: 未设置（Telegram功能已启用但未配置管理员Chat ID）")
        return False
    
    print_success("Telegram Bot: 配置完整")
    return True

def main():
    """主函数"""
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print("生产环境配置检查")
    print(f"{'='*60}{Colors.RESET}\n")
    
    results = []
    
    # 检查环境
    print(f"{Colors.BOLD}一、环境配置{Colors.RESET}")
    results.append(("环境配置", check_production()))
    print()
    
    # 检查必填项
    print(f"{Colors.BOLD}二、必填配置项{Colors.RESET}")
    results.append(("SECRET_KEY", check_secret_key()))
    results.append(("DATABASE_URL", check_database()))
    results.append(("BACKEND_CORS_ORIGINS", check_cors()))
    results.append(("FIRST_SUPERUSER", check_required("FIRST_SUPERUSER", "管理员用户名"))))
    results.append(("FIRST_SUPERUSER_PASSWORD", check_admin_password()))
    print()
    
    # 检查Telegram
    print(f"{Colors.BOLD}三、Telegram Bot配置{Colors.RESET}")
    results.append(("Telegram", check_telegram()))
    print()
    
    # 检查可选配置
    print(f"{Colors.BOLD}四、可选配置项{Colors.RESET}")
    optional_configs = [
        ("ACCESS_TOKEN_EXPIRE_MINUTES", "JWT令牌过期时间"),
        ("DB_POOL_SIZE", "数据库连接池大小"),
        ("REDIS_URL", "Redis连接URL"),
        ("API_RATE_LIMIT", "API限流配置"),
        ("LOG_LEVEL", "日志级别"),
    ]
    
    for key, desc in optional_configs:
        value = os.getenv(key)
        if value:
            print_success(f"{key}: 已设置 ({value})")
        else:
            print_info(f"{key}: 使用默认值 ({desc})")
    print()
    
    # 总结
    print(f"{Colors.BOLD}{'='*60}")
    print("检查结果总结")
    print(f"{'='*60}{Colors.RESET}\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        if result:
            print_success(f"{name}: 通过")
        else:
            print_error(f"{name}: 失败")
    
    print()
    if passed == total:
        print_success(f"所有检查通过！({passed}/{total})")
        return 0
    else:
        print_error(f"部分检查未通过 ({passed}/{total})")
        print_info("请参考 env.example 和 docs/CONFIG_CHECKLIST.md 进行配置")
        return 1

if __name__ == "__main__":
    sys.exit(main())

