#!/usr/bin/env python3
"""
项目配置文件检查工具
用于检查生产环境配置是否正确设置

兼容 Windows 和 Linux/Ubuntu

使用方法:
    python scripts/check_config.py
    或
    python3 scripts/check_config.py
"""
import os
import sys
import stat
import re
import platform
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.core.config import settings
except ImportError:
    print("错误: 无法导入配置模块，请确保在项目根目录运行此脚本")
    sys.exit(1)

# 检测操作系统
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# 颜色支持检测（Windows 10+ 支持 ANSI，但需要启用）
def supports_color():
    """检测终端是否支持颜色"""
    if IS_WINDOWS:
        # Windows 10+ 支持 ANSI，但需要检查
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # 尝试启用虚拟终端处理
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except:
            return False
    else:
        # Linux/Unix 通常支持颜色
        return os.getenv('TERM') != 'dumb' and os.isatty(sys.stdout.fileno())

# 颜色定义
SUPPORTS_COLOR = supports_color()

class Colors:
    if SUPPORTS_COLOR:
        RED = '\033[0;31m'
        GREEN = '\033[0;32m'
        YELLOW = '\033[1;33m'
        BLUE = '\033[0;34m'
        CYAN = '\033[0;36m'
        RESET = '\033[0m'
        BOLD = '\033[1m'
    else:
        RED = ''
        GREEN = ''
        YELLOW = ''
        BLUE = ''
        CYAN = ''
        RESET = ''
        BOLD = ''

def print_header(text: str):
    """打印标题"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")

def print_success(text: str):
    """打印成功信息"""
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")

def print_error(text: str):
    """打印错误信息"""
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")

def print_warning(text: str):
    """打印警告信息"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")

def print_info(text: str):
    """打印信息"""
    print(f"{Colors.BLUE}ℹ {text}{Colors.RESET}")

class ConfigChecker:
    """配置检查器"""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.solutions: Dict[str, str] = {}  # 存储问题和解决方案
        self.env_file = project_root / ".env"
        self.is_production = settings.is_production
        
        # 检测项目路径和环境
        self.project_path = project_root.absolute()
        project_path_str = str(self.project_path)
        self.is_ubuntu_prod = project_path_str == "/data/Platform" or project_path_str.startswith("/data/Platform/")
        self.is_windows_test = IS_WINDOWS and ("E:\\data\\Platform" in project_path_str or "E:/data/Platform" in project_path_str.replace("\\", "/"))
    
    def add_solution(self, issue: str, solution: str):
        """添加问题和解决方案"""
        self.solutions[issue] = solution
    
    def print_solution(self, issue: str):
        """打印解决方案"""
        if issue in self.solutions:
            print(f"{Colors.CYAN}   解决方案: {self.solutions[issue]}{Colors.RESET}")
    
    def get_solution(self, issue: str) -> Optional[str]:
        """获取解决方案（不打印）"""
        return self.solutions.get(issue)
        
    def check_all(self) -> bool:
        """执行所有检查"""
        print_header("项目配置文件检查工具")
        
        print_info(f"操作系统: {platform.system()} {platform.release()}")
        print_info(f"Python 版本: {sys.version.split()[0]}")
        print_info(f"项目路径: {project_root}")
        print_info(f"环境类型: {'生产环境' if self.is_production else '开发环境'}")
        print_info(f".env 文件: {self.env_file}")
        if IS_WINDOWS:
            print_info("运行环境: Windows（部分检查已适配）")
        elif IS_LINUX:
            print_info("运行环境: Linux/Ubuntu")
        print()
        
        # 1. 检查 .env 文件
        self.check_env_file()
        
        # 2. 检查环境变量
        self.check_environment()
        
        # 3. 检查安全配置
        self.check_security_config()
        
        # 4. 检查数据库配置
        self.check_database_config()
        
        # 5. 检查 Redis 配置
        self.check_redis_config()
        
        # 6. 检查 CORS 配置
        self.check_cors_config()
        
        # 7. 检查管理员账户配置
        self.check_admin_config()
        
        # 8. 检查 JWT 配置
        self.check_jwt_config()
        
        # 9. 检查时区配置
        self.check_timezone_config()
        
        # 10. 检查文件权限
        self.check_file_permissions()
        
        # 11. 检查目录结构
        self.check_directory_structure()
        
        # 12. 检查依赖
        self.check_dependencies()
        
        # 打印总结
        self.print_summary()
        
        return len(self.errors) == 0
    
    def check_env_file(self):
        """检查 .env 文件"""
        print_header("1. 检查项目环境和 .env 文件")
        
        # 显示项目路径和环境信息
        print_info(f"项目路径: {self.project_path}")
        if self.is_ubuntu_prod:
            print_success("✓ 检测到 Ubuntu 生产环境 (/data/Platform)")
        elif self.is_windows_test:
            print_info("ℹ 检测到 Windows 测试环境 (E:\\data\\Platform)")
        else:
            print_info(f"ℹ 项目路径: {self.project_path}")
        
        print_info(f"环境类型: {'生产环境' if self.is_production else '开发/测试环境'}")
        print()
        
        if not self.env_file.exists():
            self.errors.append(".env 文件不存在")
            print_error(".env 文件不存在")
            solution = "从 env.example 复制: " + ("copy env.example .env" if IS_WINDOWS else "cp env.example .env")
            self.add_solution(".env 文件不存在", solution)
            self.print_solution(".env 文件不存在")
            return
        
        print_success(".env 文件存在")
        print_info(f".env 文件路径: {self.env_file.absolute()}")
        
        # 检查文件大小
        size = self.env_file.stat().st_size
        if size == 0:
            self.errors.append(".env 文件为空")
            print_error(".env 文件为空")
            solution = "编辑 .env 文件并添加必要的配置项，参考 env.example"
            self.add_solution(".env 文件为空", solution)
            self.print_solution(".env 文件为空")
        else:
            print_success(f".env 文件大小: {size} 字节")
    
    def check_environment(self):
        """检查环境配置"""
        print_header("2. 检查环境配置")
        
        prod_env = os.getenv("PRODUCTION_ENV", "development").lower()
        if self.is_production:
            if prod_env not in ["production", "prod"]:
                self.errors.append(f"生产环境 PRODUCTION_ENV 设置错误: {prod_env}")
                print_error(f"PRODUCTION_ENV={prod_env}，生产环境应设置为 'production' 或 'prod'")
                solution = "在 .env 文件中设置: PRODUCTION_ENV=production"
                self.add_solution(f"生产环境 PRODUCTION_ENV 设置错误: {prod_env}", solution)
                self.print_solution(f"生产环境 PRODUCTION_ENV 设置错误: {prod_env}")
            else:
                print_success(f"PRODUCTION_ENV={prod_env}")
        else:
            print_info(f"PRODUCTION_ENV={prod_env} (开发环境)")
    
    def check_security_config(self):
        """检查安全配置"""
        print_header("3. 检查安全配置")
        
        # SECRET_KEY
        secret_key = settings.SECRET_KEY
        if not secret_key or secret_key == "":
            self.errors.append("SECRET_KEY 未设置")
            print_error("SECRET_KEY 未设置")
            solution = "在 .env 文件中设置 SECRET_KEY，运行以下命令生成: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            self.add_solution("SECRET_KEY 未设置", solution)
            self.print_solution("SECRET_KEY 未设置")
        elif secret_key == "your-fixed-secret-key-here":
            self.errors.append("SECRET_KEY 使用默认值，不安全")
            print_error("SECRET_KEY 使用默认值")
            solution = "生成新的 SECRET_KEY: python -c \"import secrets; print(secrets.token_urlsafe(64))\" 然后更新 .env 文件"
            self.add_solution("SECRET_KEY 使用默认值，不安全", solution)
            self.print_solution("SECRET_KEY 使用默认值，不安全")
        elif len(secret_key) < 32:
            if self.is_production:
                self.errors.append(f"SECRET_KEY 长度不足: {len(secret_key)} 字符（生产环境至少32字符）")
                print_error(f"SECRET_KEY 长度不足: {len(secret_key)} 字符")
                solution = f"生成新的 SECRET_KEY（至少32字符）: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
                self.add_solution(f"SECRET_KEY 长度不足: {len(secret_key)} 字符（生产环境至少32字符）", solution)
                self.print_solution(f"SECRET_KEY 长度不足: {len(secret_key)} 字符（生产环境至少32字符）")
            else:
                self.warnings.append(f"SECRET_KEY 长度不足: {len(secret_key)} 字符（建议至少32字符）")
                print_warning(f"SECRET_KEY 长度不足: {len(secret_key)} 字符")
                solution = "建议生成更长的 SECRET_KEY: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
                self.add_solution(f"SECRET_KEY 长度不足: {len(secret_key)} 字符（建议至少32字符）", solution)
                self.print_solution(f"SECRET_KEY 长度不足: {len(secret_key)} 字符（建议至少32字符）")
        else:
            print_success(f"SECRET_KEY 已设置（长度: {len(secret_key)} 字符）")
    
    def check_database_config(self):
        """检查数据库配置"""
        print_header("4. 检查数据库配置")
        
        db_url = settings.SQLALCHEMY_DATABASE_URI
        
        if not db_url:
            self.errors.append("DATABASE_URL 未设置")
            print_error("DATABASE_URL 未设置")
            return
        
        print_success("DATABASE_URL 已设置")
        
        # 解析数据库 URL
        try:
            # 处理 mysql+aiomysql:// 格式
            if db_url.startswith("mysql+aiomysql://"):
                db_url_parsed = db_url.replace("mysql+aiomysql://", "mysql://")
            else:
                db_url_parsed = db_url
            
            parsed = urlparse(db_url_parsed)
            
            # 检查主机
            host = parsed.hostname or "localhost"
            print_info(f"数据库主机: {host}")
            
            # 检查端口
            port = parsed.port or 3306
            print_info(f"数据库端口: {port}")
            
            # 检查数据库名
            db_name = parsed.path.lstrip('/')
            if db_name:
                print_info(f"数据库名: {db_name}")
            else:
                self.warnings.append("数据库名未指定")
                print_warning("数据库名未指定")
            
            # 检查用户名
            username = parsed.username
            if username:
                print_info(f"数据库用户: {username}")
            else:
                self.errors.append("数据库用户名未设置")
                print_error("数据库用户名未设置")
                solution = "在 .env 文件中设置 DATABASE_URL，格式: mysql+aiomysql://用户名:密码@主机:端口/数据库名"
                self.add_solution("数据库用户名未设置", solution)
                self.print_solution("数据库用户名未设置")
            
            # 检查密码
            password = parsed.password
            if not password:
                self.errors.append("数据库密码未设置")
                print_error("数据库密码未设置")
                solution = "在 .env 文件中设置 DATABASE_URL，包含数据库密码"
                self.add_solution("数据库密码未设置", solution)
                self.print_solution("数据库密码未设置")
            elif self.is_production:
                # 检查是否使用默认密码
                if "He800407" in password or "admin123" in password:
                    self.errors.append("数据库密码使用默认值，不安全")
                    print_error("数据库密码使用默认值")
                    solution = "修改数据库密码，然后在 .env 文件中更新 DATABASE_URL"
                    self.add_solution("数据库密码使用默认值，不安全", solution)
                    self.print_solution("数据库密码使用默认值，不安全")
                else:
                    print_success("数据库密码已设置（非默认值）")
            
            # 测试数据库连接（可选）
            if password and username:
                print_info("尝试测试数据库连接...")
                try:
                    import asyncio
                    from app.core.database import engine
                    
                    async def test_connection():
                        try:
                            from sqlalchemy import text
                            async with engine.connect() as conn:
                                await conn.execute(text("SELECT 1"))
                                return True
                        except Exception as e:
                            return str(e)
                        finally:
                            # 确保连接关闭
                            try:
                                await engine.dispose()
                            except:
                                pass
                    
                    # Windows 上需要设置事件循环策略
                    if IS_WINDOWS:
                        try:
                            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                        except AttributeError:
                            pass
                    
                    # 创建新的事件循环（避免 Windows 上的事件循环关闭错误）
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        result = loop.run_until_complete(test_connection())
                        loop.close()
                    except Exception as e:
                        result = str(e)
                    if result is True:
                        print_success("数据库连接成功")
                    else:
                        self.warnings.append(f"数据库连接失败: {result}")
                        print_warning(f"数据库连接失败: {result}")
                        solution = "1. 检查 MySQL 服务是否运行 2. 验证 DATABASE_URL 配置 3. 检查数据库用户权限"
                        self.add_solution(f"数据库连接失败: {result}", solution)
                        self.print_solution(f"数据库连接失败: {result}")
                except ImportError:
                    print_info("数据库引擎未初始化，跳过连接测试")
                except Exception as e:
                    self.warnings.append(f"无法测试数据库连接: {e}")
                    print_warning(f"无法测试数据库连接: {e}")
        
        except Exception as e:
            self.errors.append(f"数据库 URL 格式错误: {e}")
            print_error(f"数据库 URL 格式错误: {e}")
            solution = "检查 DATABASE_URL 格式，应为: mysql+aiomysql://用户名:密码@主机:端口/数据库名"
            self.add_solution(f"数据库 URL 格式错误: {e}", solution)
            self.print_solution(f"数据库 URL 格式错误: {e}")
    
    def check_redis_config(self):
        """检查 Redis 配置"""
        print_header("5. 检查 Redis 配置")
        
        redis_host = getattr(settings, 'REDIS_HOST', None)
        redis_url = getattr(settings, 'REDIS_URL', None)
        
        if redis_host or redis_url:
            print_success("Redis 配置已设置")
            if redis_host:
                print_info(f"Redis 主机: {redis_host}")
            if redis_url:
                print_info(f"Redis URL: {redis_url}")
            
            # 测试 Redis 连接（可选）
            try:
                import redis
                from app.core.redis_client import get_redis_client
                import asyncio
                
                # Windows 上需要设置事件循环策略
                if IS_WINDOWS:
                    try:
                        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                    except AttributeError:
                        pass
                
                async def test_redis():
                    try:
                        client = await get_redis_client()
                        if client:
                            await client.ping()
                            return True
                        return False
                    except Exception as e:
                        return str(e)
                
                # 创建新的事件循环（避免 Windows 上的事件循环关闭错误）
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(test_redis())
                    loop.close()
                except Exception as e:
                    result = str(e)
                if result is True:
                    print_success("Redis 连接成功")
                else:
                    error_msg = "Redis 连接失败"
                    if result is False:
                        error_msg = "Redis 连接失败: 无法获取 Redis 客户端（可能 Redis 服务未运行或配置错误）"
                    elif isinstance(result, str):
                        error_msg = f"Redis 连接失败: {result}"
                    self.warnings.append(error_msg)
                    print_warning(error_msg)
                    solution = (
                        "解决方案：\n"
                        "1. 确保 Redis 服务正在运行：\n"
                        "   - Windows: 检查 Redis 服务是否启动\n"
                        "   - Linux: sudo systemctl status redis 或 sudo service redis status\n"
                        "2. 检查 .env 文件中的 Redis 配置：\n"
                        "   - REDIS_HOST=localhost (或 Redis 服务器地址)\n"
                        "   - REDIS_PORT=6379 (默认端口)\n"
                        "   - REDIS_PASSWORD=your_password (如果设置了密码)\n"
                        "   - 或使用 REDIS_URL=redis://localhost:6379/0\n"
                        "3. 如果不需要 Redis，可以移除相关配置（某些功能可能不可用）"
                    )
                    self.add_solution(error_msg, solution)
                    self.print_solution(error_msg)
            except ImportError:
                print_info("Redis 客户端未安装，跳过连接测试")
            except Exception as e:
                self.warnings.append(f"无法测试 Redis 连接: {e}")
                print_warning(f"无法测试 Redis 连接: {e}")
        else:
            self.warnings.append("Redis 未配置（可选，用于缓存和限流）")
            print_warning("Redis 未配置（可选）")
    
    def check_cors_config(self):
        """检查 CORS 配置"""
        print_header("6. 检查 CORS 配置")
        
        cors_origins = settings.BACKEND_CORS_ORIGINS
        
        if not cors_origins or len(cors_origins) == 0:
            if self.is_production:
                self.errors.append("BACKEND_CORS_ORIGINS 未设置（生产环境必填）")
                print_error("BACKEND_CORS_ORIGINS 未设置")
                solution = "在 .env 文件中设置: BACKEND_CORS_ORIGINS=https://your-domain.com,https://www.your-domain.com"
                self.add_solution("BACKEND_CORS_ORIGINS 未设置（生产环境必填）", solution)
                self.print_solution("BACKEND_CORS_ORIGINS 未设置（生产环境必填）")
            else:
                print_info("BACKEND_CORS_ORIGINS 未设置（开发环境使用默认值）")
        else:
            print_success(f"CORS 已配置 {len(cors_origins)} 个来源")
            
            # 检查是否包含 localhost
            has_localhost = any("localhost" in origin.lower() or "127.0.0.1" in origin.lower() 
                              for origin in cors_origins)
            
            if has_localhost and self.is_production:
                self.errors.append("生产环境 CORS 配置包含 localhost")
                print_error("CORS 配置包含 localhost（生产环境不允许）")
                solution = "从 BACKEND_CORS_ORIGINS 中移除 localhost 和 127.0.0.1，只保留生产域名"
                self.add_solution("生产环境 CORS 配置包含 localhost", solution)
                self.print_solution("生产环境 CORS 配置包含 localhost")
            
            # 检查是否使用 HTTPS
            has_http = any(origin.startswith("http://") for origin in cors_origins)
            if has_http and self.is_production:
                self.warnings.append("生产环境 CORS 配置包含 HTTP（建议使用 HTTPS）")
                print_warning("CORS 配置包含 HTTP（建议使用 HTTPS）")
                solution = "将 HTTP 协议改为 HTTPS: BACKEND_CORS_ORIGINS=https://your-domain.com"
                self.add_solution("生产环境 CORS 配置包含 HTTP（建议使用 HTTPS）", solution)
                self.print_solution("生产环境 CORS 配置包含 HTTP（建议使用 HTTPS）")
            
            for origin in cors_origins:
                if origin.startswith("https://"):
                    print_success(f"  ✓ {origin}")
                else:
                    print_warning(f"  ⚠ {origin} (非 HTTPS)")
    
    def check_admin_config(self):
        """检查管理员账户配置"""
        print_header("7. 检查管理员账户配置")
        
        username = settings.FIRST_SUPERUSER
        password = settings.FIRST_SUPERUSER_PASSWORD
        
        if not username:
            self.errors.append("FIRST_SUPERUSER 未设置")
            print_error("FIRST_SUPERUSER 未设置")
            solution = "在 .env 文件中设置: FIRST_SUPERUSER=admin"
            self.add_solution("FIRST_SUPERUSER 未设置", solution)
            self.print_solution("FIRST_SUPERUSER 未设置")
        else:
            print_success(f"管理员用户名: {username}")
        
        if not password:
            if self.is_production:
                self.errors.append("FIRST_SUPERUSER_PASSWORD 未设置（生产环境必填）")
                print_error("FIRST_SUPERUSER_PASSWORD 未设置")
                solution = "在 .env 文件中设置强密码（至少12字符）: FIRST_SUPERUSER_PASSWORD=your_secure_password_here"
                self.add_solution("FIRST_SUPERUSER_PASSWORD 未设置（生产环境必填）", solution)
                self.print_solution("FIRST_SUPERUSER_PASSWORD 未设置（生产环境必填）")
            else:
                print_warning("FIRST_SUPERUSER_PASSWORD 未设置")
        elif password == "admin123":
            if self.is_production:
                self.errors.append("管理员密码使用默认值 'admin123'（不安全）")
                print_error("管理员密码使用默认值")
                solution = "在 .env 文件中设置强密码（至少12字符，包含大小写字母、数字、特殊字符）"
                self.add_solution("管理员密码使用默认值 'admin123'（不安全）", solution)
                self.print_solution("管理员密码使用默认值 'admin123'（不安全）")
            else:
                self.warnings.append("管理员密码使用默认值")
                print_warning("管理员密码使用默认值")
                solution = "建议设置更强的密码（至少12字符）"
                self.add_solution("管理员密码使用默认值", solution)
                self.print_solution("管理员密码使用默认值")
        elif len(password) < 12:
            if self.is_production:
                self.errors.append(f"管理员密码长度不足: {len(password)} 字符（生产环境至少12字符）")
                print_error(f"管理员密码长度不足: {len(password)} 字符")
                solution = f"在 .env 文件中设置至少12字符的密码: FIRST_SUPERUSER_PASSWORD=your_longer_password_here"
                self.add_solution(f"管理员密码长度不足: {len(password)} 字符（生产环境至少12字符）", solution)
                self.print_solution(f"管理员密码长度不足: {len(password)} 字符（生产环境至少12字符）")
            else:
                self.warnings.append(f"管理员密码长度不足: {len(password)} 字符")
                print_warning(f"管理员密码长度不足: {len(password)} 字符")
                solution = "建议设置至少12字符的密码"
                self.add_solution(f"管理员密码长度不足: {len(password)} 字符", solution)
                self.print_solution(f"管理员密码长度不足: {len(password)} 字符")
        else:
            print_success(f"管理员密码已设置（长度: {len(password)} 字符）")
    
    def check_jwt_config(self):
        """检查 JWT 配置"""
        print_header("8. 检查 JWT 配置")
        
        expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        algorithm = settings.JWT_ALGORITHM
        
        print_info(f"访问令牌过期时间: {expire_minutes} 分钟")
        print_info(f"JWT 算法: {algorithm}")
        
        if algorithm == "RS256":
            private_key_path = getattr(settings, 'RSA_PRIVATE_KEY_PATH', '')
            public_key_path = getattr(settings, 'RSA_PUBLIC_KEY_PATH', '')
            private_key_content = getattr(settings, 'RSA_PRIVATE_KEY', '')
            public_key_content = getattr(settings, 'RSA_PUBLIC_KEY', '')
            
            if not private_key_path and not private_key_content:
                self.warnings.append("RS256 算法但未配置 RSA 私钥")
                print_warning("RSA 私钥未配置")
                solution = (
                    "解决方案（选择其一）：\n"
                    "方法1 - 使用自动生成脚本（最简单，推荐）：\n"
                    "  运行: python scripts/generate_rsa_keys.py\n"
                    "  脚本会自动生成密钥对并保存到 keys/ 目录\n"
                    "  然后在 .env 中设置:\n"
                    "    RSA_PRIVATE_KEY_PATH=keys/private_key.pem\n"
                    "    RSA_PUBLIC_KEY_PATH=keys/public_key.pem\n\n"
                    "方法2 - 使用环境变量（推荐用于容器部署）：\n"
                    "  在 .env 文件中设置 RSA_PRIVATE_KEY，值为完整的 PEM 格式私钥内容\n"
                    "  注意：私钥内容需要包含换行符，可以使用 \\n 或直接多行输入\n\n"
                    "方法3 - 使用 OpenSSL 命令：\n"
                    "  openssl genrsa -out private_key.pem 2048\n"
                    "  openssl rsa -in private_key.pem -pubout -out public_key.pem\n"
                    "  然后在 .env 中设置: RSA_PRIVATE_KEY_PATH=private_key.pem"
                )
                self.add_solution("RS256 算法但未配置 RSA 私钥", solution)
                self.print_solution("RS256 算法但未配置 RSA 私钥")
            else:
                print_success("RSA 私钥已配置")
            
            if not public_key_path and not public_key_content:
                self.warnings.append("RS256 算法但未配置 RSA 公钥")
                print_warning("RSA 公钥未配置")
                solution = (
                    "解决方案（选择其一）：\n"
                    "方法1 - 使用自动生成脚本（最简单，推荐）：\n"
                    "  运行: python scripts/generate_rsa_keys.py\n"
                    "  脚本会自动生成密钥对（包括公钥）并保存到 keys/ 目录\n"
                    "  然后在 .env 中设置:\n"
                    "    RSA_PUBLIC_KEY_PATH=keys/public_key.pem\n\n"
                    "方法2 - 使用环境变量：\n"
                    "  在 .env 文件中设置 RSA_PUBLIC_KEY，值为完整的 PEM 格式公钥内容\n\n"
                    "方法3 - 从私钥生成公钥（如果已有私钥文件）：\n"
                    "  openssl rsa -in private_key.pem -pubout -out public_key.pem\n"
                    "  然后在 .env 中设置: RSA_PUBLIC_KEY_PATH=keys/public_key.pem"
                )
                self.add_solution("RS256 算法但未配置 RSA 公钥", solution)
                self.print_solution("RS256 算法但未配置 RSA 公钥")
            else:
                print_success("RSA 公钥已配置")
    
    def check_timezone_config(self):
        """检查时区配置"""
        print_header("9. 检查时区配置")
        
        timezone = settings.TIMEZONE
        print_info(f"应用时区: {timezone}")
        
        # 检查时区是否有效
        try:
            import pytz
            pytz.timezone(timezone)
            print_success(f"时区 '{timezone}' 有效")
        except pytz.UnknownTimeZoneError:
            self.errors.append(f"时区 '{timezone}' 无效")
            print_error(f"时区 '{timezone}' 无效")
            solution = f"在 .env 文件中设置有效的时区，例如: TIMEZONE=Asia/Shanghai 或 TIMEZONE=UTC"
            self.add_solution(f"时区 '{timezone}' 无效", solution)
            self.print_solution(f"时区 '{timezone}' 无效")
        except ImportError:
            print_warning("pytz 未安装，无法验证时区")
            solution = "安装 pytz: pip install pytz"
            self.add_solution("pytz 未安装，无法验证时区", solution)
            self.print_solution("pytz 未安装，无法验证时区")
        
        # 检查系统时区（Linux/Ubuntu）
        if IS_LINUX:
            try:
                import subprocess
                result = subprocess.run(
                    ["timedatectl", "show", "--property=Timezone", "--value"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    system_tz = result.stdout.strip()
                    print_info(f"系统时区: {system_tz}")
                    if system_tz != timezone:
                        self.warnings.append(f"系统时区 ({system_tz}) 与应用时区 ({timezone}) 不一致")
                        print_warning(f"系统时区与应用时区不一致（应用将使用配置的时区）")
                        solution = f"可选：调整系统时区与配置一致，或保持现状（应用会使用配置的时区）"
                        self.add_solution(f"系统时区 ({system_tz}) 与应用时区 ({timezone}) 不一致", solution)
                        self.print_solution(f"系统时区 ({system_tz}) 与应用时区 ({timezone}) 不一致")
                    else:
                        print_success("系统时区与应用时区一致")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                # 尝试读取 /etc/timezone
                try:
                    with open("/etc/timezone", "r") as f:
                        system_tz = f.read().strip()
                        print_info(f"系统时区: {system_tz} (从 /etc/timezone 读取)")
                        if system_tz != timezone:
                            self.warnings.append(f"系统时区 ({system_tz}) 与应用时区 ({timezone}) 不一致")
                            print_warning(f"系统时区与应用时区不一致（应用将使用配置的时区）")
                            solution = f"可选：调整系统时区与配置一致，或保持现状（应用会使用配置的时区）"
                            self.add_solution(f"系统时区 ({system_tz}) 与应用时区 ({timezone}) 不一致", solution)
                            self.print_solution(f"系统时区 ({system_tz}) 与应用时区 ({timezone}) 不一致")
                        else:
                            print_success("系统时区与应用时区一致")
                except (FileNotFoundError, PermissionError):
                    print_info("无法检测系统时区（timedatectl 和 /etc/timezone 不可用）")
        elif IS_WINDOWS:
            # Windows 时区检测
            try:
                import time
                # 尝试导入 winreg（Windows 专用）
                try:
                    import winreg as wr
                    # 尝试从注册表读取时区
                    try:
                        key = wr.OpenKey(
                            wr.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation"
                        )
                        try:
                            tz_name = wr.QueryValueEx(key, "TimeZoneKeyName")[0]
                            print_info(f"系统时区: {tz_name} (Windows)")
                            # Windows 时区名称格式不同，只做信息提示
                        except:
                            # 使用 time.tzname
                            tz_name = time.tzname[0] if time.tzname else "未知"
                            print_info(f"系统时区: {tz_name} (Windows)")
                        finally:
                            wr.CloseKey(key)
                    except Exception as e:
                        # 使用 time.tzname 作为后备
                        tz_name = time.tzname[0] if time.tzname else "未知"
                        print_info(f"系统时区: {tz_name} (Windows, 从 time.tzname 获取)")
                except ImportError:
                    # winreg 不可用，使用 time.tzname
                    tz_name = time.tzname[0] if time.tzname else "未知"
                    print_info(f"系统时区: {tz_name} (Windows)")
            except Exception as e:
                print_info(f"无法检测 Windows 系统时区: {e}")
        else:
            print_info("无法检测系统时区（不支持的操作系统）")
    
    def check_file_permissions(self):
        """检查文件权限"""
        print_header("10. 检查文件权限")
        
        if IS_WINDOWS:
            # Windows 权限检查（简化版）
            if self.env_file.exists():
                print_info(f".env 文件存在（Windows 权限检查较复杂，建议手动验证）")
                # Windows 上检查文件是否可读
                if os.access(self.env_file, os.R_OK):
                    print_success(".env 文件可读")
                else:
                    self.errors.append(".env 文件不可读")
                    print_error(".env 文件不可读")
                    solution = "检查文件权限，确保当前用户有读取权限"
                    self.add_solution(".env 文件不可读", solution)
                    self.print_solution(".env 文件不可读")
            else:
                self.errors.append(".env 文件不存在")
                print_error(".env 文件不存在")
                solution = "从 env.example 复制: " + ("copy env.example .env" if IS_WINDOWS else "cp env.example .env")
                self.add_solution(".env 文件不存在", solution)
                self.print_solution(".env 文件不存在")
            
            # 检查日志目录
            log_dir = project_root / "logs"
            if log_dir.exists():
                print_info("日志目录存在")
            else:
                print_warning("日志目录不存在")
        else:
            # Linux/Unix 权限检查
            # 检查 .env 文件权限
            if self.env_file.exists():
                mode = self.env_file.stat().st_mode
                permissions = stat.filemode(mode)
                
                # 检查是否为 640 或更严格
                if mode & 0o077:  # 其他用户有权限
                    self.warnings.append(f".env 文件权限过宽: {permissions}（建议 640）")
                    print_warning(f".env 文件权限: {permissions}（建议 640）")
                    solution = "设置文件权限: chmod 640 .env 和 chown www-data:www-data .env"
                    self.add_solution(f".env 文件权限过宽: {permissions}（建议 640）", solution)
                    self.print_solution(f".env 文件权限过宽: {permissions}（建议 640）")
                else:
                    print_success(f".env 文件权限: {permissions}")
            else:
                self.errors.append(".env 文件不存在")
                print_error(".env 文件不存在")
                solution = "从 env.example 复制: " + ("copy env.example .env" if IS_WINDOWS else "cp env.example .env")
                self.add_solution(".env 文件不存在", solution)
                self.print_solution(".env 文件不存在")
            
            # 检查日志目录权限
            log_dir = project_root / "logs"
            if log_dir.exists():
                mode = log_dir.stat().st_mode
                permissions = stat.filemode(mode)
                print_info(f"日志目录权限: {permissions}")
            else:
                print_warning("日志目录不存在")
                solution = "创建日志目录: mkdir -p logs"
                self.add_solution("日志目录不存在", solution)
                self.print_solution("日志目录不存在")
    
    def check_directory_structure(self):
        """检查目录结构"""
        print_header("11. 检查目录结构")
        
        required_dirs = [
            "app",
            "frontend",
            "logs",
            "systemd",
        ]
        
        for dir_name in required_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists():
                print_success(f"{dir_name}/ 目录存在")
            else:
                self.warnings.append(f"{dir_name}/ 目录不存在")
                print_warning(f"{dir_name}/ 目录不存在")
        
        # 检查关键文件
        required_files = [
            "requirements.txt",
            "gunicorn.conf.py",
            "app/main.py",
        ]
        
        for file_name in required_files:
            file_path = project_root / file_name
            if file_path.exists():
                print_success(f"{file_name} 文件存在")
            else:
                self.errors.append(f"{file_name} 文件不存在")
                print_error(f"{file_name} 文件不存在")
                if file_name == "requirements.txt":
                    solution = "创建 requirements.txt 文件，列出所有 Python 依赖"
                elif file_name == "gunicorn.conf.py":
                    solution = "创建 gunicorn.conf.py 配置文件，或使用默认配置"
                else:
                    solution = f"检查项目结构，确保 {file_name} 文件存在"
                self.add_solution(f"{file_name} 文件不存在", solution)
                self.print_solution(f"{file_name} 文件不存在")
                if file_name == "requirements.txt":
                    solution = "创建 requirements.txt 文件，列出所有 Python 依赖"
                elif file_name == "gunicorn.conf.py":
                    solution = "创建 gunicorn.conf.py 配置文件，或使用默认配置"
                else:
                    solution = f"检查项目结构，确保 {file_name} 文件存在"
                self.add_solution(f"{file_name} 文件不存在", solution)
                self.print_solution(f"{file_name} 文件不存在")
    
    def check_dependencies(self):
        """检查依赖"""
        print_header("12. 检查关键依赖")
        
        # 检查 Python 版本
        python_version = sys.version_info
        print_info(f"Python 版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
        
        if python_version < (3, 10):
            self.errors.append(f"Python 版本过低: {python_version.major}.{python_version.minor}（需要 3.10+）")
            print_error(f"Python 版本过低（需要 3.10+）")
            solution = "升级 Python 到 3.10 或更高版本。Ubuntu: sudo apt install python3.10; Windows: 从 python.org 下载安装"
            self.add_solution(f"Python 版本过低: {python_version.major}.{python_version.minor}（需要 3.10+）", solution)
            self.print_solution(f"Python 版本过低: {python_version.major}.{python_version.minor}（需要 3.10+）")
        else:
            print_success("Python 版本符合要求")
        
        # 检查关键包
        critical_packages = [
            ("fastapi", "FastAPI"),
            ("sqlalchemy", "SQLAlchemy"),
            ("gunicorn", "Gunicorn"),
            ("pydantic", "Pydantic"),
        ]
        
        for package_name, display_name in critical_packages:
            try:
                __import__(package_name)
                print_success(f"{display_name} 已安装")
            except ImportError:
                self.errors.append(f"{display_name} 未安装")
                print_error(f"{display_name} 未安装")
                solution = f"安装依赖: pip install {package_name} 或 pip install -r requirements.txt"
                self.add_solution(f"{display_name} 未安装", solution)
                self.print_solution(f"{display_name} 未安装")
    
    def print_summary(self):
        """打印检查总结"""
        print_header("检查总结")
        
        total_checks = len(self.errors) + len(self.warnings)
        
        if len(self.errors) > 0:
            print_error(f"发现 {len(self.errors)} 个错误:")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
        
        if len(self.warnings) > 0:
            print_warning(f"发现 {len(self.warnings)} 个警告:")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")
        
        if len(self.errors) == 0 and len(self.warnings) == 0:
            print_success("所有检查通过！配置正确。")
        elif len(self.errors) == 0:
            print_warning("配置基本正确，但有一些警告需要注意。")
        else:
            print_error("配置存在问题，请修复错误后重新检查。")
        
        print()
        print_info(f"总计: {len(self.errors)} 个错误, {len(self.warnings)} 个警告")


def main():
    """主函数"""
    try:
        checker = ConfigChecker()
        success = checker.check_all()
        
        # 返回退出码
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n检查被用户中断")
        sys.exit(130)
    except Exception as e:
        print_error(f"检查过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

