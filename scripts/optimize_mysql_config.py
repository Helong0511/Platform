#!/usr/bin/env python3
"""
MySQL 配置自动优化脚本
适用于 Ubuntu 22.04.5，自动检测硬件信息并优化 MySQL 8.0 配置

功能：
1. 自动检测 CPU 核心数和内存大小
2. 检查当前 MySQL 配置
3. 根据硬件资源自动计算最优配置
4. 备份原配置文件
5. 应用优化后的配置
6. 提供回滚功能

使用方法：
    sudo python3 scripts/optimize_mysql_config.py
    sudo python3 scripts/optimize_mysql_config.py --apply
    sudo python3 scripts/optimize_mysql_config.py --rollback
"""

import os
import sys
import shutil
import subprocess
import argparse
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, Optional

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_info(msg: str):
    """打印信息"""
    print(f"{Colors.CYAN}[INFO]{Colors.RESET} {msg}")


def print_success(msg: str):
    """打印成功信息"""
    print(f"{Colors.GREEN}[SUCCESS]{Colors.RESET} {msg}")


def print_warning(msg: str):
    """打印警告信息"""
    print(f"{Colors.YELLOW}[WARNING]{Colors.RESET} {msg}")


def print_error(msg: str):
    """打印错误信息"""
    print(f"{Colors.RED}[ERROR]{Colors.RESET} {msg}")


def print_section(title: str):
    """打印章节标题"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")


def run_command(cmd: list, check: bool = True) -> Tuple[int, str, str]:
    """
    执行系统命令
    
    Args:
        cmd: 命令列表
        check: 是否检查返回码
        
    Returns:
        (返回码, 标准输出, 标准错误)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        if check and result.returncode != 0:
            print_error(f"命令执行失败: {' '.join(cmd)}")
            print_error(f"错误信息: {result.stderr}")
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        print_error(f"命令执行超时: {' '.join(cmd)}")
        return -1, "", "命令执行超时"
    except Exception as e:
        print_error(f"执行命令时出错: {e}")
        return -1, "", str(e)


def get_cpu_info() -> Dict[str, any]:
    """获取 CPU 信息"""
    cpu_info = {}
    
    # CPU 核心数
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            cpu_info['cores'] = cpuinfo.count('processor')
            cpu_info['physical_cores'] = len(set(
                re.findall(r'physical id\s+:\s+(\d+)', cpuinfo)
            ))
    except Exception as e:
        print_warning(f"无法读取 CPU 信息: {e}")
        cpu_info['cores'] = 2  # 默认值
        cpu_info['physical_cores'] = 1
    
    # CPU 型号
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('model name'):
                    cpu_info['model'] = line.split(':', 1)[1].strip()
                    break
    except:
        cpu_info['model'] = "Unknown"
    
    return cpu_info


def get_memory_info() -> Dict[str, any]:
    """获取内存信息（单位：MB）"""
    memory_info = {}
    
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = f.read()
            
            # 总内存（KB）
            total_match = re.search(r'MemTotal:\s+(\d+)\s+kB', meminfo)
            if total_match:
                total_kb = int(total_match.group(1))
                memory_info['total_mb'] = total_kb // 1024
                memory_info['total_gb'] = round(total_kb / (1024 * 1024), 2)
            
            # 可用内存（KB）
            available_match = re.search(r'MemAvailable:\s+(\d+)\s+kB', meminfo)
            if available_match:
                available_kb = int(available_match.group(1))
                memory_info['available_mb'] = available_kb // 1024
                memory_info['available_gb'] = round(available_kb / (1024 * 1024), 2)
            
            # 已用内存
            if 'total_mb' in memory_info and 'available_mb' in memory_info:
                memory_info['used_mb'] = memory_info['total_mb'] - memory_info['available_mb']
                memory_info['used_gb'] = round(memory_info['used_mb'] / 1024, 2)
            
    except Exception as e:
        print_warning(f"无法读取内存信息: {e}")
        memory_info['total_gb'] = 4  # 默认值
        memory_info['total_mb'] = 4096
    
    return memory_info


def get_disk_info() -> Dict[str, any]:
    """获取磁盘信息"""
    disk_info = {}
    
    try:
        result = subprocess.run(
            ['df', '-h', '/'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 4:
                    disk_info['total'] = parts[1]
                    disk_info['used'] = parts[2]
                    disk_info['available'] = parts[3]
                    disk_info['usage_percent'] = parts[4]
    except Exception as e:
        print_warning(f"无法读取磁盘信息: {e}")
    
    return disk_info


def find_mysql_config_file() -> Optional[str]:
    """查找 MySQL 配置文件"""
    possible_paths = [
        '/etc/mysql/mysql.conf.d/mysqld.cnf',
        '/etc/mysql/my.cnf',
        '/etc/my.cnf',
        '/etc/mysql/my.cnf',
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None


def read_mysql_config(config_file: str) -> Dict[str, str]:
    """读取 MySQL 配置文件"""
    config = {}
    
    if not os.path.exists(config_file):
        return config
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            current_section = None
            for line in f:
                line = line.strip()
                
                # 跳过注释和空行
                if not line or line.startswith('#'):
                    continue
                
                # 处理节（section）
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1]
                    continue
                
                # 处理配置项
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 移除引号
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    full_key = f"{current_section}.{key}" if current_section else key
                    config[full_key] = value
    
    except Exception as e:
        print_error(f"读取配置文件失败: {e}")
    
    return config


def calculate_mysql_config(cpu_cores: int, total_memory_gb: float) -> Dict[str, str]:
    """
    根据硬件资源计算 MySQL 最优配置
    
    Args:
        cpu_cores: CPU 核心数
        total_memory_gb: 总内存（GB）
    
    Returns:
        优化后的配置字典
    """
    config = {}
    
    # InnoDB Buffer Pool Size（最重要的配置）
    # 对于 4GB 内存服务器，建议设置为总内存的 25-30%
    # 但需要为系统、MySQL 其他部分、Gunicorn workers 等预留空间
    if total_memory_gb <= 2:
        innodb_buffer_pool_size = 256  # MB
    elif total_memory_gb <= 4:
        # 4GB 内存：512MB-768MB（为系统和其他服务预留空间）
        innodb_buffer_pool_size = min(768, int(total_memory_gb * 128))  # 约 512MB
    elif total_memory_gb <= 8:
        innodb_buffer_pool_size = int(total_memory_gb * 128)  # 约 1GB
    else:
        innodb_buffer_pool_size = int(total_memory_gb * 100)  # 约 1GB/8GB
    
    config['mysqld.innodb_buffer_pool_size'] = f"{innodb_buffer_pool_size}M"
    
    # InnoDB Log File Size（建议为 buffer pool 的 25%）
    innodb_log_file_size = max(64, min(512, innodb_buffer_pool_size // 4))
    config['mysqld.innodb_log_file_size'] = f"{innodb_log_file_size}M"
    
    # InnoDB Log Files In Group（通常为 2）
    config['mysqld.innodb_log_files_in_group'] = "2"
    
    # InnoDB Flush Log At Trx Commit（性能优化）
    config['mysqld.innodb_flush_log_at_trx_commit'] = "2"  # 平衡性能和安全性
    
    # Max Connections（根据应用需求，3个worker × 20连接 = 60，加上其他连接）
    max_connections = max(100, min(200, cpu_cores * 30))
    config['mysqld.max_connections'] = str(max_connections)
    
    # Thread Cache Size
    config['mysqld.thread_cache_size'] = str(min(50, cpu_cores * 10))
    
    # Table Open Cache
    config['mysqld.table_open_cache'] = "2000"
    
    # Query Cache（MySQL 8.0 已移除，不需要配置）
    
    # Sort Buffer Size
    config['mysqld.sort_buffer_size'] = "2M"
    
    # Read Buffer Size
    config['mysqld.read_buffer_size'] = "1M"
    
    # Read Rnd Buffer Size
    config['mysqld.read_rnd_buffer_size'] = "4M"
    
    # Join Buffer Size
    config['mysqld.join_buffer_size'] = "2M"
    
    # Temp Table Size
    config['mysqld.tmp_table_size'] = "32M"
    config['mysqld.max_heap_table_size'] = "32M"
    
    # InnoDB Thread Concurrency（MySQL 8.0 已废弃，但保留兼容性）
    # config['mysqld.innodb_thread_concurrency'] = str(cpu_cores * 2)
    
    # InnoDB IO Threads
    config['mysqld.innodb_read_io_threads'] = str(min(4, cpu_cores))
    config['mysqld.innodb_write_io_threads'] = str(min(4, cpu_cores))
    
    # InnoDB Flush Method（SSD 优化）
    config['mysqld.innodb_flush_method'] = "O_DIRECT"
    
    # InnoDB File Per Table
    config['mysqld.innodb_file_per_table'] = "1"
    
    # Slow Query Log（可选，用于性能分析）
    config['mysqld.slow_query_log'] = "1"
    config['mysqld.slow_query_log_file'] = "/var/log/mysql/slow-query.log"
    config['mysqld.long_query_time'] = "2"
    
    # General Log（关闭以节省性能）
    config['mysqld.general_log'] = "0"
    
    # Binary Log（启用，用于主从复制和恢复）
    config['mysqld.log_bin'] = "/var/log/mysql/mysql-bin"
    config['mysqld.binlog_expire_logs_seconds'] = "604800"  # 7天
    
    # Character Set
    config['mysqld.character_set_server'] = "utf8mb4"
    config['mysqld.collation_server'] = "utf8mb4_unicode_ci"
    
    # Time Zone
    config['mysqld.default_time_zone'] = "+08:00"
    
    return config


def backup_config_file(config_file: str) -> Optional[str]:
    """备份配置文件"""
    if not os.path.exists(config_file):
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{config_file}.backup_{timestamp}"
    
    try:
        shutil.copy2(config_file, backup_file)
        print_success(f"配置文件已备份到: {backup_file}")
        return backup_file
    except Exception as e:
        print_error(f"备份配置文件失败: {e}")
        return None


def apply_mysql_config(config_file: str, optimized_config: Dict[str, str], current_config: Dict[str, str]) -> bool:
    """应用优化后的 MySQL 配置"""
    
    # 读取原文件内容
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print_error(f"读取配置文件失败: {e}")
        return False
    
    # 准备新配置内容
    new_lines = []
    current_section = None
    config_applied = set()  # 记录已应用的配置项
    
    for line in lines:
        original_line = line
        line_stripped = line.strip()
        
        # 保留注释和空行
        if not line_stripped or line_stripped.startswith('#'):
            new_lines.append(line)
            continue
        
        # 处理节（section）
        if line_stripped.startswith('[') and line_stripped.endswith(']'):
            current_section = line_stripped[1:-1]
            new_lines.append(line)
            continue
        
        # 处理配置项
        if '=' in line_stripped and not line_stripped.startswith('#'):
            key = line_stripped.split('=', 1)[0].strip()
            full_key = f"{current_section}.{key}" if current_section else key
            
            # 如果这个配置项需要优化
            if full_key in optimized_config:
                new_value = optimized_config[full_key]
                # 替换配置值
                new_line = f"{key} = {new_value}\n"
                new_lines.append(new_line)
                config_applied.add(full_key)
                print_info(f"更新配置: {full_key} = {new_value}")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    # 添加未在原文件中出现的新配置项
    for full_key, value in optimized_config.items():
        if full_key not in config_applied:
            section, key = full_key.split('.', 1) if '.' in full_key else (None, full_key)
            
            # 检查是否需要添加节
            if section and section not in [line.strip()[1:-1] for line in new_lines 
                                          if line.strip().startswith('[') and line.strip().endswith(']')]:
                new_lines.append(f"\n[{section}]\n")
            
            # 添加新配置项
            new_lines.append(f"{key} = {value}\n")
            print_info(f"添加新配置: {full_key} = {value}")
    
    # 写入新配置
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print_success(f"配置文件已更新: {config_file}")
        return True
    except Exception as e:
        print_error(f"写入配置文件失败: {e}")
        return False


def validate_mysql_config() -> bool:
    """验证 MySQL 配置是否正确"""
    print_info("验证 MySQL 配置...")
    
    returncode, stdout, stderr = run_command(['mysql', '--help'], check=False)
    if returncode != 0:
        print_warning("无法验证配置（MySQL 客户端不可用）")
        return True  # 假设配置正确
    
    # 尝试使用 mysqld --validate-config（如果可用）
    returncode, stdout, stderr = run_command(['mysqld', '--validate-config'], check=False)
    if returncode == 0:
        print_success("MySQL 配置验证通过")
        return True
    else:
        print_warning("MySQL 配置验证失败，但可能不影响运行")
        print_warning(f"错误信息: {stderr}")
        return True  # 继续执行，让用户手动验证


def print_hardware_info(cpu_info: Dict, memory_info: Dict, disk_info: Dict):
    """打印硬件信息"""
    print_section("硬件信息检测")
    
    print(f"{Colors.BOLD}CPU 信息:{Colors.RESET}")
    print(f"  核心数: {Colors.GREEN}{cpu_info.get('cores', 'N/A')}{Colors.RESET}")
    print(f"  物理核心数: {Colors.GREEN}{cpu_info.get('physical_cores', 'N/A')}{Colors.RESET}")
    print(f"  型号: {Colors.GREEN}{cpu_info.get('model', 'N/A')}{Colors.RESET}")
    
    print(f"\n{Colors.BOLD}内存信息:{Colors.RESET}")
    print(f"  总内存: {Colors.GREEN}{memory_info.get('total_gb', 'N/A')} GB{Colors.RESET} "
          f"({memory_info.get('total_mb', 'N/A')} MB)")
    if 'used_gb' in memory_info:
        print(f"  已用内存: {Colors.YELLOW}{memory_info.get('used_gb', 'N/A')} GB{Colors.RESET} "
              f"({memory_info.get('used_mb', 'N/A')} MB)")
        print(f"  可用内存: {Colors.GREEN}{memory_info.get('available_gb', 'N/A')} GB{Colors.RESET} "
              f"({memory_info.get('available_mb', 'N/A')} MB)")
    
    if disk_info:
        print(f"\n{Colors.BOLD}磁盘信息:{Colors.RESET}")
        print(f"  总容量: {Colors.GREEN}{disk_info.get('total', 'N/A')}{Colors.RESET}")
        print(f"  已用: {Colors.YELLOW}{disk_info.get('used', 'N/A')}{Colors.RESET} "
              f"({disk_info.get('usage_percent', 'N/A')})")
        print(f"  可用: {Colors.GREEN}{disk_info.get('available', 'N/A')}{Colors.RESET}")


def print_config_comparison(current_config: Dict[str, str], optimized_config: Dict[str, str]):
    """打印配置对比"""
    print_section("配置对比")
    
    print(f"{Colors.BOLD}{'配置项':<50} {'当前值':<30} {'优化值':<30}{Colors.RESET}")
    print("-" * 110)
    
    all_keys = set(current_config.keys()) | set(optimized_config.keys())
    important_keys = [
        'mysqld.innodb_buffer_pool_size',
        'mysqld.max_connections',
        'mysqld.innodb_log_file_size',
        'mysqld.innodb_flush_log_at_trx_commit',
        'mysqld.thread_cache_size',
        'mysqld.table_open_cache',
    ]
    
    # 先显示重要配置
    for key in important_keys:
        if key in optimized_config:
            current_value = current_config.get(key, '未设置')
            optimized_value = optimized_config[key]
            
            if current_value != optimized_value:
                print(f"{Colors.YELLOW}{key:<50}{Colors.RESET} {current_value:<30} "
                      f"{Colors.GREEN}{optimized_value:<30}{Colors.RESET}")
            else:
                print(f"{key:<50} {current_value:<30} {Colors.CYAN}{optimized_value:<30}{Colors.RESET}")
    
    # 显示其他配置
    for key in sorted(all_keys - set(important_keys)):
        if key in optimized_config:
            current_value = current_config.get(key, '未设置')
            optimized_value = optimized_config[key]
            
            if current_value != optimized_value:
                print(f"{Colors.YELLOW}{key:<50}{Colors.RESET} {current_value:<30} "
                      f"{Colors.GREEN}{optimized_value:<30}{Colors.RESET}")


def main():
    parser = argparse.ArgumentParser(
        description='MySQL 配置自动优化脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 仅检查配置（不应用）
  sudo python3 scripts/optimize_mysql_config.py
  
  # 应用优化配置
  sudo python3 scripts/optimize_mysql_config.py --apply
  
  # 回滚到备份配置
  sudo python3 scripts/optimize_mysql_config.py --rollback
        """
    )
    parser.add_argument('--apply', action='store_true', help='应用优化后的配置')
    parser.add_argument('--rollback', type=str, metavar='BACKUP_FILE', help='回滚到指定的备份文件')
    
    args = parser.parse_args()
    
    # 检查 root 权限
    if os.geteuid() != 0:
        print_error("此脚本需要 root 权限，请使用 sudo 运行")
        sys.exit(1)
    
    # 获取硬件信息
    cpu_info = get_cpu_info()
    memory_info = get_memory_info()
    disk_info = get_disk_info()
    
    # 打印硬件信息
    print_hardware_info(cpu_info, memory_info, disk_info)
    
    # 查找 MySQL 配置文件
    config_file = find_mysql_config_file()
    if not config_file:
        print_error("未找到 MySQL 配置文件")
        print_info("请检查 MySQL 是否已安装，配置文件通常在以下位置：")
        print_info("  /etc/mysql/mysql.conf.d/mysqld.cnf")
        print_info("  /etc/mysql/my.cnf")
        sys.exit(1)
    
    print_section("MySQL 配置")
    print_info(f"配置文件位置: {config_file}")
    
    # 读取当前配置
    current_config = read_mysql_config(config_file)
    
    # 计算优化配置
    cpu_cores = cpu_info.get('cores', 2)
    total_memory_gb = memory_info.get('total_gb', 4)
    optimized_config = calculate_mysql_config(cpu_cores, total_memory_gb)
    
    # 打印配置对比
    print_config_comparison(current_config, optimized_config)
    
    # 处理回滚
    if args.rollback:
        if not os.path.exists(args.rollback):
            print_error(f"备份文件不存在: {args.rollback}")
            sys.exit(1)
        
        print_section("回滚配置")
        try:
            shutil.copy2(args.rollback, config_file)
            print_success(f"已回滚到备份文件: {args.rollback}")
            print_info("请重启 MySQL 服务使配置生效: sudo systemctl restart mysql")
        except Exception as e:
            print_error(f"回滚失败: {e}")
            sys.exit(1)
        return
    
    # 应用配置
    if args.apply:
        print_section("应用配置")
        
        # 备份原配置
        backup_file = backup_config_file(config_file)
        if not backup_file:
            print_error("备份失败，取消应用配置")
            sys.exit(1)
        
        # 应用新配置
        if apply_mysql_config(config_file, optimized_config, current_config):
            print_success("配置已应用")
            print_warning("请重启 MySQL 服务使配置生效:")
            print_info("  sudo systemctl restart mysql")
            print_info(f"备份文件: {backup_file}")
            print_info("如需回滚，请使用:")
            print_info(f"  sudo python3 scripts/optimize_mysql_config.py --rollback {backup_file}")
            
            # 验证配置
            validate_mysql_config()
        else:
            print_error("应用配置失败")
            sys.exit(1)
    else:
        print_section("提示")
        print_info("当前仅显示配置对比，未实际应用")
        print_info("如需应用配置，请使用 --apply 参数:")
        print_info("  sudo python3 scripts/optimize_mysql_config.py --apply")


if __name__ == '__main__':
    main()

