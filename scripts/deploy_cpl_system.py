"""
CPL 系统部署脚本
用于自动化执行数据库迁移和验证
"""
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts" / "data"
VERIFY_SCRIPT = PROJECT_ROOT / "scripts" / "verify_cpl_tables.sql"

# 颜色输出（Windows 和 Linux 兼容）
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    
    @staticmethod
    def disable():
        Colors.GREEN = ''
        Colors.RED = ''
        Colors.YELLOW = ''
        Colors.BLUE = ''
        Colors.RESET = ''

# 如果 Windows 且不支持颜色，禁用颜色
if sys.platform == 'win32':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except:
        Colors.disable()


def print_step(step_num, message):
    """打印步骤信息"""
    print(f"\n{Colors.BLUE}[步骤 {step_num}]{Colors.RESET} {message}")


def print_success(message):
    """打印成功信息"""
    print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")


def print_error(message):
    """打印错误信息"""
    print(f"{Colors.RED}❌ {message}{Colors.RESET}")


def print_warning(message):
    """打印警告信息"""
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.RESET}")


def print_info(message):
    """打印信息"""
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.RESET}")


def run_mysql_command(command, database, username, password=None):
    """执行 MySQL 命令"""
    if password:
        cmd = f'mysql -u {username} -p{password} {database}'
    else:
        cmd = f'mysql -u {username} -p {database}'
    
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=command)
        
        if process.returncode != 0:
            return False, stderr
        return True, stdout
    except Exception as e:
        return False, str(e)


def backup_database(username, password, database):
    """备份数据库"""
    print_step(1, "备份数据库")
    
    backup_file = PROJECT_ROOT / "backups" / f"platform_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
    backup_file.parent.mkdir(exist_ok=True)
    
    if password:
        cmd = f'mysqldump -u {username} -p{password} {database} > "{backup_file}"'
    else:
        cmd = f'mysqldump -u {username} -p {database} > "{backup_file}"'
    
    print_info(f"执行备份命令: mysqldump -u {username} -p*** {database} > {backup_file}")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print_success(f"数据库备份成功: {backup_file}")
            return True, backup_file
        else:
            print_error(f"数据库备份失败: {result.stderr}")
            return False, None
    except Exception as e:
        print_error(f"备份过程出错: {str(e)}")
        return False, None


def execute_sql_file(sql_file, username, password, database):
    """执行 SQL 文件"""
    if not sql_file.exists():
        print_error(f"SQL 文件不存在: {sql_file}")
        return False
    
    print_info(f"执行 SQL 文件: {sql_file.name}")
    
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    success, output = run_mysql_command(sql_content, database, username, password)
    
    if success:
        print_success(f"SQL 文件执行成功: {sql_file.name}")
        return True
    else:
        print_error(f"SQL 文件执行失败: {sql_file.name}")
        print_error(f"错误信息: {output}")
        return False


def verify_tables(username, password, database):
    """验证表结构"""
    print_step(4, "验证表结构")
    
    if not VERIFY_SCRIPT.exists():
        print_warning("验证脚本不存在，跳过验证")
        return True
    
    print_info(f"执行验证脚本: {VERIFY_SCRIPT.name}")
    
    with open(VERIFY_SCRIPT, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    success, output = run_mysql_command(sql_content, database, username, password)
    
    if success:
        print_success("验证脚本执行成功")
        print_info("验证结果:")
        print(output)
        return True
    else:
        print_warning(f"验证脚本执行失败: {output}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("CPL 系统部署脚本")
    print("=" * 60)
    
    # 获取数据库配置
    print("\n请输入数据库配置信息：")
    database = input("数据库名称 [platform]: ").strip() or "platform"
    username = input("数据库用户名: ").strip()
    if not username:
        print_error("数据库用户名不能为空")
        return 1
    
    use_password = input("是否使用密码？(y/n) [y]: ").strip().lower() or "y"
    password = None
    if use_password == "y":
        password = input("数据库密码: ").strip()
    
    # 确认
    print("\n" + "=" * 60)
    print("部署配置确认：")
    print(f"  数据库: {database}")
    print(f"  用户名: {username}")
    print(f"  使用密码: {'是' if password else '否'}")
    print("=" * 60)
    
    confirm = input("\n确认开始部署？(y/n): ").strip().lower()
    if confirm != "y":
        print_info("部署已取消")
        return 0
    
    # 步骤1：备份数据库
    backup_success, backup_file = backup_database(username, password, database)
    if not backup_success:
        confirm = input("\n备份失败，是否继续？(y/n): ").strip().lower()
        if confirm != "y":
            print_info("部署已取消")
            return 1
    
    # 步骤2：执行数据库迁移
    print_step(2, "执行数据库迁移")
    
    # 2.1 创建新表
    tables_file = SCRIPTS_DIR / "cpl_system_tables.sql"
    if not execute_sql_file(tables_file, username, password, database):
        print_error("创建新表失败，部署终止")
        return 1
    
    # 2.2 修改现有表
    alter_file = SCRIPTS_DIR / "alter_postback_conversions_table.sql"
    if not execute_sql_file(alter_file, username, password, database):
        print_error("修改现有表失败，部署终止")
        return 1
    
    # 步骤3：验证表结构
    verify_tables(username, password, database)
    
    # 完成
    print("\n" + "=" * 60)
    print_success("数据库迁移完成！")
    print("=" * 60)
    print("\n下一步操作：")
    print("1. 重启应用服务")
    print("2. 运行测试脚本: python scripts/test_cpl_system.py")
    print("3. 访问系统，测试功能")
    print("\n备份文件位置:", backup_file if backup_success else "无")
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n部署已中断")
        sys.exit(1)
    except Exception as e:
        print_error(f"部署过程出错: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

