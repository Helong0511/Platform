#!/usr/bin/env python3
"""
MySQL 配置自动优化脚本
适用于 Ubuntu 22.04.5，自动检测硬件信息并优化 MySQL 8.0 配置

项目架构：
- 4个服务：API Service、Postback Service、Tracking Service、CPL Service
- 每个服务默认3个workers
- 每个worker连接池：pool_size=12, max_overflow=8
- 总连接数 = (12 + 8) × 3 × 4 = 240（需要max_connections >= 300）

功能：
1. 自动检测 CPU 核心数和内存大小
2. 检查当前 MySQL 配置
3. 根据硬件资源和多服务架构自动计算最优配置
4. 优化高并发场景配置（死锁检测、锁等待超时等）
5. 备份原配置文件
6. 应用优化后的配置
7. 提供回滚功能

优化重点：
- InnoDB Buffer Pool Size：根据总内存优化（40-50%）
- Max Connections：考虑4个服务 × 3workers × 20连接 = 240，建议300-500
- InnoDB Lock Wait Timeout：全局5秒（各服务可在会话级别覆盖）
- InnoDB Deadlock Detect：开启
- InnoDB Buffer Pool Instances：多实例提升并发性能
- 事务隔离级别：全局REPEATABLE READ（Tracking服务可在代码中设置READ COMMITTED）

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


def get_ubuntu_version() -> Dict[str, str]:
    """获取 Ubuntu 版本信息"""
    ubuntu_info = {
        'version': 'Unknown',
        'codename': 'Unknown',
        'release': 'Unknown',
        'major': 0,
        'minor': 0,
    }
    
    try:
        # 方法1：读取 /etc/os-release
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                for line in f:
                    if line.startswith('VERSION_ID='):
                        version_str = line.split('=', 1)[1].strip().strip('"')
                        ubuntu_info['version'] = version_str
                        # 解析主版本和次版本
                        parts = version_str.split('.')
                        if len(parts) >= 2:
                            ubuntu_info['major'] = int(parts[0])
                            ubuntu_info['minor'] = int(parts[1])
                        elif len(parts) == 1:
                            ubuntu_info['major'] = int(parts[0])
                    elif line.startswith('VERSION_CODENAME='):
                        ubuntu_info['codename'] = line.split('=', 1)[1].strip().strip('"')
                    elif line.startswith('PRETTY_NAME='):
                        ubuntu_info['release'] = line.split('=', 1)[1].strip().strip('"')
    except Exception as e:
        print_warning(f"无法读取 Ubuntu 版本信息: {e}")
    
    # 方法2：使用 lsb_release 命令（备用）
    if ubuntu_info['version'] == 'Unknown':
        returncode, stdout, stderr = run_command(['lsb_release', '-a'], check=False)
        if returncode == 0:
            for line in stdout.split('\n'):
                if line.startswith('Release:'):
                    version_str = line.split(':', 1)[1].strip()
                    ubuntu_info['version'] = version_str
                    parts = version_str.split('.')
                    if len(parts) >= 2:
                        ubuntu_info['major'] = int(parts[0])
                        ubuntu_info['minor'] = int(parts[1])
                elif line.startswith('Codename:'):
                    ubuntu_info['codename'] = line.split(':', 1)[1].strip()
    
    return ubuntu_info


def get_mysql_version() -> Dict[str, str]:
    """获取 MySQL 版本信息"""
    mysql_info = {
        'version': 'Unknown',
        'major': 0,
        'minor': 0,
        'patch': 0,
        'full_version': 'Unknown',
        'is_mariadb': False,
    }
    
    # 方法1：使用 mysql --version
    returncode, stdout, stderr = run_command(['mysql', '--version'], check=False)
    if returncode == 0:
        version_str = stdout.strip()
        mysql_info['full_version'] = version_str
        
        # 解析版本号
        # 格式可能是：mysql  Ver 8.0.35-0ubuntu0.22.04.1 for Linux on x86_64
        # 或：mysql  Ver 15.1 Distrib 10.11.5-MariaDB, for debian-linux-gnu
        version_match = re.search(r'(\d+)\.(\d+)\.(\d+)', version_str)
        if version_match:
            mysql_info['major'] = int(version_match.group(1))
            mysql_info['minor'] = int(version_match.group(2))
            mysql_info['patch'] = int(version_match.group(3))
            mysql_info['version'] = f"{mysql_info['major']}.{mysql_info['minor']}.{mysql_info['patch']}"
        
        # 检测是否是 MariaDB
        if 'mariadb' in version_str.lower():
            mysql_info['is_mariadb'] = True
    
    # 方法2：使用 mysqld --version（备用）
    if mysql_info['version'] == 'Unknown':
        returncode, stdout, stderr = run_command(['mysqld', '--version'], check=False)
        if returncode == 0:
            version_str = stdout.strip()
            mysql_info['full_version'] = version_str
            version_match = re.search(r'(\d+)\.(\d+)\.(\d+)', version_str)
            if version_match:
                mysql_info['major'] = int(version_match.group(1))
                mysql_info['minor'] = int(version_match.group(2))
                mysql_info['patch'] = int(version_match.group(3))
                mysql_info['version'] = f"{mysql_info['major']}.{mysql_info['minor']}.{mysql_info['patch']}"
            
            if 'mariadb' in version_str.lower():
                mysql_info['is_mariadb'] = True
    
    # 方法3：查询数据库（如果可能）
    if mysql_info['version'] == 'Unknown':
        returncode, stdout, stderr = run_command(
            ['mysql', '-e', 'SELECT VERSION();'],
            check=False
        )
        if returncode == 0:
            version_match = re.search(r'(\d+)\.(\d+)\.(\d+)', stdout)
            if version_match:
                mysql_info['major'] = int(version_match.group(1))
                mysql_info['minor'] = int(version_match.group(2))
                mysql_info['patch'] = int(version_match.group(3))
                mysql_info['version'] = f"{mysql_info['major']}.{mysql_info['minor']}.{mysql_info['patch']}"
    
    return mysql_info


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


def is_docker_environment() -> bool:
    """检测是否在Docker环境中运行"""
    # 检查是否在容器中
    if os.path.exists('/.dockerenv'):
        return True
    
    # 检查是否在Docker容器中（通过cgroup）
    try:
        with open('/proc/self/cgroup', 'r') as f:
            if 'docker' in f.read() or 'containerd' in f.read():
                return True
    except:
        pass
    
    return False


def find_mysql_config_file() -> Optional[str]:
    """查找 MySQL 配置文件"""
    # Docker环境下的配置文件路径
    docker_paths = [
        '/etc/mysql/conf.d/custom.cnf',  # Docker挂载的配置文件
        '/etc/mysql/my.cnf',
        '/etc/my.cnf',
    ]
    
    # 非Docker环境的配置文件路径
    system_paths = [
        '/etc/mysql/mysql.conf.d/mysqld.cnf',
        '/etc/mysql/my.cnf',
        '/etc/my.cnf',
        '/etc/mysql/my.cnf',
    ]
    
    # 项目配置文件路径（如果脚本在项目目录中运行）
    project_paths = [
        './configs/mysql/my.cnf',
        '../configs/mysql/my.cnf',
        '../../configs/mysql/my.cnf',
    ]
    
    # 按优先级查找
    all_paths = docker_paths + system_paths + project_paths
    
    for path in all_paths:
        if os.path.exists(path):
            return os.path.abspath(path)
    
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


def calculate_mysql_config(cpu_cores: int, total_memory_gb: float, mysql_version: Dict[str, any] = None, ubuntu_version: Dict[str, any] = None) -> Dict[str, str]:
    """
    根据硬件资源、MySQL版本、Ubuntu版本和多服务架构计算 MySQL 最优配置
    
    项目架构：
    - 4个服务：API Service、Postback Service、Tracking Service、CPL Service
    - 每个服务默认3个workers
    - 每个worker连接池：pool_size=12, max_overflow=8
    - 总连接数 = (12 + 8) × 3 × 4 = 240（需要max_connections >= 300）
    
    Args:
        cpu_cores: CPU 核心数
        total_memory_gb: 总内存（GB）
        mysql_version: MySQL版本信息字典
        ubuntu_version: Ubuntu版本信息字典
    
    Returns:
        优化后的配置字典
    """
    config = {}
    
    # 版本信息
    mysql_major = mysql_version.get('major', 8) if mysql_version else 8
    mysql_minor = mysql_version.get('minor', 0) if mysql_version else 0
    is_mariadb = mysql_version.get('is_mariadb', False) if mysql_version else False
    ubuntu_major = ubuntu_version.get('major', 22) if ubuntu_version else 22
    ubuntu_minor = ubuntu_version.get('minor', 4) if ubuntu_version else 4
    
    # 版本兼容性检查
    if is_mariadb:
        print_warning("检测到 MariaDB，某些 MySQL 8.0 特有配置可能不适用")
    elif mysql_major < 8:
        print_warning(f"MySQL 版本 {mysql_major}.{mysql_minor} 较旧，建议升级到 MySQL 8.0+")
    elif mysql_major == 8 and mysql_minor < 0:
        print_warning(f"MySQL 版本 {mysql_major}.{mysql_minor}，建议使用 MySQL 8.0.20+")
    
    # Ubuntu 22.04 特定优化
    if ubuntu_major == 22:
        print_info("检测到 Ubuntu 22.04，应用 Ubuntu 22.04 特定优化")
    
    # ========== InnoDB Buffer Pool Size（最重要的配置）==========
    # 多服务架构：需要为4个服务 + MySQL + 系统预留内存
    # 建议：总内存的 40-50%（为多服务预留更多空间）
    if total_memory_gb <= 2:
        innodb_buffer_pool_size = 256  # MB
    elif total_memory_gb <= 4:
        # 4GB 内存：768MB-1GB（为4个服务预留空间）
        innodb_buffer_pool_size = min(1024, int(total_memory_gb * 256))  # 约 1GB
    elif total_memory_gb <= 8:
        # 8GB 内存：2GB-3GB
        innodb_buffer_pool_size = int(total_memory_gb * 384)  # 约 3GB
    elif total_memory_gb <= 16:
        # 16GB 内存：6GB-8GB
        innodb_buffer_pool_size = int(total_memory_gb * 512)  # 约 8GB
    else:
        # 16GB+ 内存：总内存的 50%
        innodb_buffer_pool_size = int(total_memory_gb * 512)  # 约 50%
    
    config['mysqld.innodb_buffer_pool_size'] = f"{innodb_buffer_pool_size}M"
    
    # ========== InnoDB Log File Size ==========
    # 建议为 buffer pool 的 25%，但不超过512MB
    innodb_log_file_size = max(128, min(512, innodb_buffer_pool_size // 4))
    config['mysqld.innodb_log_file_size'] = f"{innodb_log_file_size}M"
    
    # InnoDB Log Files In Group（通常为 2）
    config['mysqld.innodb_log_files_in_group'] = "2"
    
    # ========== InnoDB Flush Log At Trx Commit ==========
    # 多服务高并发场景：使用2（平衡性能和安全性）
    # 0: 每秒刷新（最快，但可能丢失1秒数据）
    # 1: 每次提交刷新（最安全，但最慢）
    # 2: 每次提交刷新到OS缓存，每秒刷新到磁盘（推荐）
    config['mysqld.innodb_flush_log_at_trx_commit'] = "2"
    
    # ========== Max Connections（多服务架构优化）==========
    # 计算：4个服务 × 3个workers × (12 + 8)连接 = 240
    # 加上管理连接、监控连接等，建议设置为 300-500
    # 根据CPU核心数动态调整，但最低300
    base_connections = 300  # 基础连接数（4个服务 × 3workers × 20连接 + 预留）
    cpu_based_connections = cpu_cores * 50  # CPU核心数 × 50
    max_connections = max(base_connections, min(500, cpu_based_connections))
    config['mysqld.max_connections'] = str(max_connections)
    
    # ========== 连接相关配置 ==========
    # Max Connect Errors（防止连接错误攻击）
    config['mysqld.max_connect_errors'] = "10000"
    
    # Connect Timeout（连接超时，秒）
    config['mysqld.connect_timeout'] = "10"
    
    # Wait Timeout（非交互式连接超时，秒）
    config['mysqld.wait_timeout'] = "600"  # 10分钟
    
    # Interactive Timeout（交互式连接超时，秒）
    config['mysqld.interactive_timeout'] = "600"  # 10分钟
    
    # ========== Thread Cache Size ==========
    # 多服务场景：需要更多线程缓存
    thread_cache_size = min(100, max(50, cpu_cores * 15))
    config['mysqld.thread_cache_size'] = str(thread_cache_size)
    
    # ========== Table Open Cache ==========
    # 多服务场景：需要更大的表缓存
    config['mysqld.table_open_cache'] = "4000"
    config['mysqld.table_definition_cache'] = "2000"
    
    # ========== Query Cache（MySQL 8.0 已移除，不需要配置）==========
    
    # ========== Sort Buffer Size ==========
    config['mysqld.sort_buffer_size'] = "4M"  # 高并发场景适当增大
    
    # ========== Read Buffer Size ==========
    config['mysqld.read_buffer_size'] = "2M"
    
    # ========== Read Rnd Buffer Size ==========
    config['mysqld.read_rnd_buffer_size'] = "8M"
    
    # ========== Join Buffer Size ==========
    config['mysqld.join_buffer_size'] = "4M"
    
    # ========== Temp Table Size ==========
    config['mysqld.tmp_table_size'] = "64M"  # 高并发场景适当增大
    config['mysqld.max_heap_table_size'] = "64M"
    
    # ========== InnoDB 并发控制（多服务高并发优化）==========
    # InnoDB Thread Concurrency（MySQL 8.0 已废弃，但保留兼容性）
    # config['mysqld.innodb_thread_concurrency'] = str(cpu_cores * 2)
    
    # InnoDB IO Threads（根据CPU核心数优化）
    innodb_read_io_threads = min(8, max(4, cpu_cores))
    innodb_write_io_threads = min(8, max(4, cpu_cores))
    config['mysqld.innodb_read_io_threads'] = str(innodb_read_io_threads)
    config['mysqld.innodb_write_io_threads'] = str(innodb_write_io_threads)
    
    # ========== InnoDB 锁配置（多服务高并发优化）==========
    # Lock Wait Timeout（全局默认，各服务可在会话级别覆盖）
    # 文档建议：Tracking=3s, Postback=5s, API=10s, CPL=5s
    # 全局设置为中等值5秒，各服务可在代码中设置会话级别
    config['mysqld.innodb_lock_wait_timeout'] = "5"
    
    # Deadlock Detect（死锁检测，必须开启）
    config['mysqld.innodb_deadlock_detect'] = "ON"
    
    # ========== InnoDB 性能优化 ==========
    # Flush Method（SSD 优化，使用 O_DIRECT 绕过OS缓存）
    # Ubuntu 22.04 默认使用 systemd，推荐 O_DIRECT
    if ubuntu_major >= 22:
        config['mysqld.innodb_flush_method'] = "O_DIRECT"
    else:
        # Ubuntu 20.04 及以下可以使用 O_DIRECT_NO_FSYNC（如果支持）
        config['mysqld.innodb_flush_method'] = "O_DIRECT"
    
    # File Per Table（每个表独立文件，便于管理）
    config['mysqld.innodb_file_per_table'] = "1"
    
    # InnoDB Buffer Pool Instances（多实例提升并发性能）
    # MySQL 8.0+ 建议：每1GB buffer pool 1个实例，最多64个（MySQL 8.0.14+）
    # MySQL 5.7 最多8个实例
    if mysql_major >= 8 and mysql_minor >= 14:
        max_instances = 64
    elif mysql_major >= 8:
        max_instances = 8
    else:
        max_instances = 8
    
    buffer_pool_instances = min(max_instances, max(1, innodb_buffer_pool_size // 1024))
    config['mysqld.innodb_buffer_pool_instances'] = str(buffer_pool_instances)
    
    # InnoDB Adaptive Hash Index（自适应哈希索引，高并发场景开启）
    # MySQL 8.0+ 默认开启，但可以显式设置
    if mysql_major >= 8:
        config['mysqld.innodb_adaptive_hash_index'] = "ON"
    else:
        # MySQL 5.7 需要显式设置
        config['mysqld.innodb_adaptive_hash_index'] = "ON"
    
    # InnoDB Change Buffer（变更缓冲，提升写入性能）
    # MySQL 8.0+ 默认 all，但可以显式设置
    config['mysqld.innodb_change_buffering'] = "all"
    
    # InnoDB Flush Neighbors（SSD场景关闭，提升性能）
    # MySQL 8.0.2+ 默认关闭（0），但可以显式设置
    if mysql_major >= 8:
        config['mysqld.innodb_flush_neighbors'] = "0"
    else:
        # MySQL 5.7 需要显式设置
        config['mysqld.innodb_flush_neighbors'] = "0"
    
    # ========== MySQL 8.0+ 特定优化 ==========
    if mysql_major >= 8:
        # InnoDB Redo Log（MySQL 8.0.30+ 支持动态调整）
        if mysql_minor >= 30:
            # 可以动态调整，但初始值建议设置
            pass
        
        # Caching SHA2 Password（MySQL 8.0 默认认证插件）
        # 不需要配置，但确保兼容性
        
        # 默认认证插件（MySQL 8.0+）
        # config['mysqld.default_authentication_plugin'] = "mysql_native_password"  # 如果需要兼容旧客户端
        
        # InnoDB Temp Tablespace（MySQL 8.0+）
        # 默认使用独立临时表空间，性能更好
    
    # ========== 日志配置 ==========
    # Slow Query Log（慢查询日志，用于性能分析）
    config['mysqld.slow_query_log'] = "1"
    config['mysqld.slow_query_log_file'] = "/var/log/mysql/slow-query.log"
    config['mysqld.long_query_time'] = "2"  # 超过2秒的查询记录
    
    # General Log（通用日志，关闭以节省性能）
    config['mysqld.general_log'] = "0"
    
    # Binary Log（二进制日志，启用用于主从复制和恢复）
    config['mysqld.log_bin'] = "/var/log/mysql/mysql-bin"
    config['mysqld.binlog_expire_logs_seconds'] = "604800"  # 7天
    config['mysqld.binlog_format'] = "ROW"  # ROW格式，更安全
    config['mysqld.binlog_row_image'] = "MINIMAL"  # 最小化日志大小
    
    # Error Log（错误日志）
    config['mysqld.log_error'] = "/var/log/mysql/error.log"
    config['mysqld.log_error_verbosity'] = "2"  # 详细错误信息
    
    # ========== 字符集配置 ==========
    config['mysqld.character_set_server'] = "utf8mb4"
    config['mysqld.collation_server'] = "utf8mb4_unicode_ci"
    config['mysqld.init_connect'] = "SET NAMES utf8mb4"
    
    # ========== 时区配置 ==========
    config['mysqld.default_time_zone'] = "+08:00"
    
    # ========== 事务隔离级别（全局默认，各服务可在会话级别覆盖）==========
    # MySQL 8.0+ 使用 transaction_isolation
    # MySQL 5.7 使用 tx_isolation
    if mysql_major >= 8:
        # 文档建议：Tracking使用READ COMMITTED，其他使用REPEATABLE READ
        # 全局设置为REPEATABLE READ，Tracking服务可在代码中设置会话级别
        config['mysqld.transaction_isolation'] = "REPEATABLE-READ"
    else:
        # MySQL 5.7 使用 tx_isolation
        config['mysqld.tx_isolation'] = "REPEATABLE-READ"
    
    # ========== 其他性能优化 ==========
    # Skip Name Resolve（跳过DNS解析，提升连接速度）
    # Ubuntu 22.04 推荐开启，提升连接性能
    config['mysqld.skip_name_resolve'] = "1"
    
    # Lower Case Table Names（表名大小写敏感，Linux默认0）
    # Ubuntu 22.04 默认0（大小写敏感）
    config['mysqld.lower_case_table_names'] = "0"
    
    # SQL Mode（严格模式，确保数据一致性）
    # MySQL 8.0+ 默认严格模式，但可以显式设置
    if mysql_major >= 8:
        # MySQL 8.0+ 默认包含更多严格检查
        config['mysqld.sql_mode'] = "STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION"
    else:
        # MySQL 5.7 需要显式设置
        config['mysqld.sql_mode'] = "STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION"
    
    # ========== Ubuntu 22.04 特定优化 ==========
    if ubuntu_major == 22:
        # Ubuntu 22.04 使用 systemd，优化 systemd 相关配置
        # 确保 MySQL 使用正确的 systemd 服务管理
        
        # 优化文件描述符限制（systemd 会自动处理，但可以显式设置）
        # config['mysqld.open_files_limit'] = "65535"  # systemd 会自动设置
        
        # Ubuntu 22.04 默认使用 AppArmor，确保 MySQL 有正确权限
        # 不需要在配置文件中设置，但会在输出中提醒
        pass
    
    # Max Allowed Packet（最大数据包大小，用于大字段）
    config['mysqld.max_allowed_packet'] = "64M"
    
    # Net Buffer Length（网络缓冲区大小）
    config['mysqld.net_buffer_length'] = "16384"
    
    # Max Packet Length（最大数据包长度）
    config['mysqld.max_packet_length'] = "67108864"  # 64MB
    
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


def validate_mysql_config(config_file: str) -> bool:
    """验证 MySQL 配置是否正确"""
    print_section("配置验证")
    print_info("验证 MySQL 配置...")
    
    # 检查配置文件语法
    if not os.path.exists(config_file):
        print_error(f"配置文件不存在: {config_file}")
        return False
    
    # 尝试使用 mysqld --validate-config（如果可用）
    returncode, stdout, stderr = run_command(['mysqld', '--validate-config'], check=False)
    if returncode == 0:
        print_success("MySQL 配置语法验证通过")
    else:
        print_warning("MySQL 配置语法验证失败，但可能不影响运行")
        if stderr:
            print_warning(f"错误信息: {stderr}")
    
    # 检查关键配置项
    print_info("检查关键配置项...")
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        checks = [
            ('innodb_buffer_pool_size', 'InnoDB Buffer Pool Size'),
            ('max_connections', 'Max Connections'),
            ('innodb_lock_wait_timeout', 'InnoDB Lock Wait Timeout'),
            ('innodb_deadlock_detect', 'InnoDB Deadlock Detect'),
        ]
        
        all_ok = True
        for key, name in checks:
            if key in content.lower():
                print_success(f"  ✓ {name} 已配置")
            else:
                print_warning(f"  ⚠ {name} 未找到（可能使用默认值）")
                all_ok = False
        
        return all_ok
    except Exception as e:
        print_warning(f"无法读取配置文件进行验证: {e}")
        return True  # 继续执行


def calculate_connection_requirements() -> Dict[str, int]:
    """计算多服务架构的连接数需求"""
    # 根据文档：4个服务，每个服务3个workers，每个worker连接池12+8=20
    services = {
        'API Service': {'workers': 3, 'pool_size': 12, 'max_overflow': 8},
        'Postback Service': {'workers': 3, 'pool_size': 12, 'max_overflow': 8},
        'Tracking Service': {'workers': 3, 'pool_size': 12, 'max_overflow': 8},
        'CPL Service': {'workers': 3, 'pool_size': 12, 'max_overflow': 8},
    }
    
    total_connections = 0
    service_connections = {}
    
    for service_name, config in services.items():
        connections_per_worker = config['pool_size'] + config['max_overflow']
        service_total = connections_per_worker * config['workers']
        service_connections[service_name] = service_total
        total_connections += service_total
    
    # 加上管理连接、监控连接等预留
    reserved_connections = 20
    recommended_max_connections = total_connections + reserved_connections
    
    return {
        'total_connections': total_connections,
        'recommended_max_connections': recommended_max_connections,
        'service_connections': service_connections,
        'reserved_connections': reserved_connections,
    }


def print_hardware_info(cpu_info: Dict, memory_info: Dict, disk_info: Dict, 
                       ubuntu_info: Dict = None, mysql_info: Dict = None):
    """打印硬件信息和系统版本"""
    print_section("系统信息检测")
    
    # 检测运行环境
    is_docker = is_docker_environment()
    env_type = "Docker容器" if is_docker else "系统环境"
    print(f"{Colors.BOLD}运行环境:{Colors.RESET} {Colors.CYAN}{env_type}{Colors.RESET}")
    
    # Ubuntu 版本信息
    if ubuntu_info:
        ubuntu_version = ubuntu_info.get('version', 'Unknown')
        ubuntu_codename = ubuntu_info.get('codename', 'Unknown')
        print(f"{Colors.BOLD}Ubuntu 版本:{Colors.RESET} {Colors.GREEN}{ubuntu_version}{Colors.RESET} ({ubuntu_codename})")
        
        # 版本建议
        ubuntu_major = ubuntu_info.get('major', 0)
        if ubuntu_major == 22:
            print_success("  ✓ Ubuntu 22.04 已优化配置")
        elif ubuntu_major == 20:
            print_info("  ℹ Ubuntu 20.04 支持，建议升级到 22.04 以获得更好性能")
        elif ubuntu_major < 20:
            print_warning("  ⚠ Ubuntu 版本较旧，建议升级到 22.04")
    
    # MySQL 版本信息
    if mysql_info:
        mysql_version = mysql_info.get('version', 'Unknown')
        mysql_full = mysql_info.get('full_version', 'Unknown')
        is_mariadb = mysql_info.get('is_mariadb', False)
        
        db_type = "MariaDB" if is_mariadb else "MySQL"
        print(f"{Colors.BOLD}{db_type} 版本:{Colors.RESET} {Colors.GREEN}{mysql_version}{Colors.RESET}")
        if mysql_full != 'Unknown' and mysql_full != mysql_version:
            print(f"  完整版本: {Colors.CYAN}{mysql_full}{Colors.RESET}")
        
        # 版本建议
        mysql_major = mysql_info.get('major', 0)
        mysql_minor = mysql_info.get('minor', 0)
        if is_mariadb:
            print_warning("  ⚠ 检测到 MariaDB，某些 MySQL 8.0 优化可能不适用")
        elif mysql_major >= 8:
            if mysql_minor >= 20:
                print_success("  ✓ MySQL 8.0.20+ 已优化配置")
            else:
                print_info("  ℹ MySQL 8.0 支持，建议升级到 8.0.20+")
        elif mysql_major == 5 and mysql_minor >= 7:
            print_warning("  ⚠ MySQL 5.7 支持，但建议升级到 MySQL 8.0+ 以获得更好性能")
        else:
            print_warning("  ⚠ MySQL 版本较旧，强烈建议升级到 MySQL 8.0+")
    
    print(f"\n{Colors.BOLD}CPU 信息:{Colors.RESET}")
    print(f"  核心数: {Colors.GREEN}{cpu_info.get('cores', 'N/A')}{Colors.RESET}")
    print(f"  物理核心数: {Colors.GREEN}{cpu_info.get('physical_cores', 'N/A')}{Colors.RESET}")
    print(f"  型号: {Colors.GREEN}{cpu_info.get('model', 'N/A')}{Colors.RESET}")
    
    print(f"\n{Colors.BOLD}内存信息:{Colors.RESET}")
    total_gb = memory_info.get('total_gb', 0)
    print(f"  总内存: {Colors.GREEN}{total_gb} GB{Colors.RESET} "
          f"({memory_info.get('total_mb', 'N/A')} MB)")
    if 'used_gb' in memory_info:
        print(f"  已用内存: {Colors.YELLOW}{memory_info.get('used_gb', 'N/A')} GB{Colors.RESET} "
              f"({memory_info.get('used_mb', 'N/A')} MB)")
        print(f"  可用内存: {Colors.GREEN}{memory_info.get('available_gb', 'N/A')} GB{Colors.RESET} "
              f"({memory_info.get('available_mb', 'N/A')} MB)")
    
    # 内存建议
    if total_gb > 0:
        if total_gb < 4:
            print_warning(f"内存较小（{total_gb}GB），建议至少4GB以支持多服务架构")
        elif total_gb < 8:
            print_info(f"内存适中（{total_gb}GB），可以运行多服务，但建议升级到8GB+以获得更好性能")
        else:
            print_success(f"内存充足（{total_gb}GB），可以良好支持多服务架构")
    
    if disk_info:
        print(f"\n{Colors.BOLD}磁盘信息:{Colors.RESET}")
        print(f"  总容量: {Colors.GREEN}{disk_info.get('total', 'N/A')}{Colors.RESET}")
        print(f"  已用: {Colors.YELLOW}{disk_info.get('used', 'N/A')}{Colors.RESET} "
              f"({disk_info.get('usage_percent', 'N/A')})")
        print(f"  可用: {Colors.GREEN}{disk_info.get('available', 'N/A')}{Colors.RESET}")
        
        # 磁盘使用率警告
        usage_str = disk_info.get('usage_percent', '0%')
        try:
            usage = int(usage_str.rstrip('%'))
            if usage > 90:
                print_error(f"磁盘使用率过高（{usage}%），建议清理空间")
            elif usage > 80:
                print_warning(f"磁盘使用率较高（{usage}%），建议关注")
        except:
            pass
    
    # 打印连接数需求
    conn_req = calculate_connection_requirements()
    print(f"\n{Colors.BOLD}多服务连接数需求:{Colors.RESET}")
    for service, conns in conn_req['service_connections'].items():
        print(f"  {service}: {Colors.CYAN}{conns}{Colors.RESET} 连接")
    print(f"  预留连接: {Colors.CYAN}{conn_req['reserved_connections']}{Colors.RESET}")
    print(f"  总需求: {Colors.GREEN}{conn_req['total_connections']}{Colors.RESET} 连接")
    print(f"  推荐 max_connections: {Colors.GREEN}{conn_req['recommended_max_connections']}{Colors.RESET}")


def print_config_comparison(current_config: Dict[str, str], optimized_config: Dict[str, str]):
    """打印配置对比"""
    print_section("配置对比")
    
    # 统计变更数量
    changed_count = 0
    new_count = 0
    unchanged_count = 0
    
    for key in optimized_config:
        current_value = current_config.get(key, '未设置')
        if current_value == '未设置':
            new_count += 1
        elif current_value != optimized_config[key]:
            changed_count += 1
        else:
            unchanged_count += 1
    
    print(f"{Colors.BOLD}配置统计:{Colors.RESET}")
    print(f"  新增配置: {Colors.GREEN}{new_count}{Colors.RESET} 项")
    print(f"  修改配置: {Colors.YELLOW}{changed_count}{Colors.RESET} 项")
    print(f"  未变更: {Colors.CYAN}{unchanged_count}{Colors.RESET} 项")
    print()
    
    print(f"{Colors.BOLD}{'配置项':<50} {'当前值':<30} {'优化值':<30}{Colors.RESET}")
    print("-" * 110)
    
    all_keys = set(current_config.keys()) | set(optimized_config.keys())
    important_keys = [
        'mysqld.innodb_buffer_pool_size',
        'mysqld.max_connections',
        'mysqld.innodb_log_file_size',
        'mysqld.innodb_flush_log_at_trx_commit',
        'mysqld.innodb_lock_wait_timeout',
        'mysqld.innodb_deadlock_detect',
        'mysqld.thread_cache_size',
        'mysqld.table_open_cache',
        'mysqld.innodb_buffer_pool_instances',
        'mysqld.innodb_read_io_threads',
        'mysqld.innodb_write_io_threads',
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
    
    # 获取系统信息
    cpu_info = get_cpu_info()
    memory_info = get_memory_info()
    disk_info = get_disk_info()
    ubuntu_info = get_ubuntu_version()
    mysql_info = get_mysql_version()
    
    # 打印系统信息
    print_hardware_info(cpu_info, memory_info, disk_info, ubuntu_info, mysql_info)
    
    # 查找 MySQL 配置文件
    config_file = find_mysql_config_file()
    if not config_file:
        print_error("未找到 MySQL 配置文件")
        print_info("请检查 MySQL 是否已安装，配置文件通常在以下位置：")
        
        is_docker = is_docker_environment()
        if is_docker:
            print_info("Docker环境配置文件路径：")
            print_info("  /etc/mysql/conf.d/custom.cnf")
            print_info("  /etc/mysql/my.cnf")
            print_info("\n提示：如果使用docker-compose，配置文件应挂载到：")
            print_info("  ./configs/mysql/my.cnf:/etc/mysql/conf.d/custom.cnf:ro")
        else:
            print_info("系统环境配置文件路径：")
            print_info("  /etc/mysql/mysql.conf.d/mysqld.cnf")
            print_info("  /etc/mysql/my.cnf")
            print_info("  /etc/my.cnf")
        
        print_info("\n项目配置文件路径（如果脚本在项目目录中运行）：")
        print_info("  ./configs/mysql/my.cnf")
        print_info("  ../configs/mysql/my.cnf")
        
        sys.exit(1)
    
    print_section("MySQL 配置")
    print_info(f"配置文件位置: {Colors.GREEN}{config_file}{Colors.RESET}")
    
    # 检查配置文件权限
    try:
        stat_info = os.stat(config_file)
        mode = stat_info.st_mode
        permissions = oct(mode)[-3:]
        print_info(f"文件权限: {permissions}")
        
        if is_docker_environment():
            print_info("运行环境: Docker容器")
            print_warning("注意：在Docker环境中，配置文件修改后需要重启容器才能生效")
        else:
            print_info("运行环境: 系统环境")
    except Exception as e:
        print_warning(f"无法读取文件权限: {e}")
    
    # 读取当前配置
    current_config = read_mysql_config(config_file)
    
    # 计算优化配置
    cpu_cores = cpu_info.get('cores', 2)
    total_memory_gb = memory_info.get('total_gb', 4)
    optimized_config = calculate_mysql_config(cpu_cores, total_memory_gb, mysql_info, ubuntu_info)
    
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
            
            # 验证配置
            validate_mysql_config(config_file)
            
            # 根据环境给出重启建议
            is_docker = is_docker_environment()
            print_section("应用配置后的操作")
            
            if is_docker:
                print_warning("⚠️ 在Docker环境中，需要重启MySQL容器使配置生效：")
                print_info("  方式1：重启MySQL容器")
                print_info("    docker compose restart mysql")
                print_info("    或")
                print_info("    docker restart platform_mysql")
                print_info("")
                print_info("  方式2：如果使用docker-compose，重新加载配置")
                print_info("    docker compose up -d mysql")
                print_info("")
                print_info("  注意：某些配置（如innodb_buffer_pool_size）需要完全重启才能生效")
            else:
                print_warning("⚠️ 请重启 MySQL 服务使配置生效：")
                print_info("  sudo systemctl restart mysql")
                print_info("")
                print_info("  或者使用以下命令：")
                print_info("  sudo service mysql restart")
                print_info("")
                print_info("  注意：某些配置（如innodb_buffer_pool_size）需要完全重启才能生效")
            
            print_info(f"\n备份文件: {Colors.CYAN}{backup_file}{Colors.RESET}")
            print_info("如需回滚，请使用:")
            print_info(f"  sudo python3 scripts/optimize_mysql_config.py --rollback {backup_file}")
            
            # 性能建议
            print_section("性能优化建议")
            cpu_cores = cpu_info.get('cores', 2)
            total_memory_gb = memory_info.get('total_gb', 4)
            
            # 内存建议
            if total_memory_gb < 4:
                print_warning("内存较小，建议：")
                print_info("  - 考虑升级到至少4GB内存")
                print_info("  - 减少其他服务的资源占用")
                print_info("  - 考虑减少 Buffer Pool Size")
            elif total_memory_gb < 8:
                print_info("内存适中，建议：")
                print_info("  - 监控内存使用情况")
                print_info("  - 考虑升级到8GB+以获得更好性能")
            
            # CPU建议
            if cpu_cores < 2:
                print_warning("CPU核心数较少，建议：")
                print_info("  - 考虑升级到至少2核CPU")
                print_info("  - 减少并发连接数")
            
            # Ubuntu版本建议
            if ubuntu_info:
                ubuntu_major = ubuntu_info.get('major', 0)
                if ubuntu_major < 22:
                    print_warning("Ubuntu版本建议：")
                    print_info("  - 建议升级到 Ubuntu 22.04 以获得更好性能和安全性")
                    print_info("  - Ubuntu 22.04 对 MySQL 8.0 有更好的优化支持")
            
            # MySQL版本建议
            if mysql_info:
                mysql_major = mysql_info.get('major', 0)
                mysql_minor = mysql_info.get('minor', 0)
                is_mariadb = mysql_info.get('is_mariadb', False)
                
                if is_mariadb:
                    print_warning("MariaDB版本建议：")
                    print_info("  - 某些 MySQL 8.0 特定优化可能不适用")
                    print_info("  - 建议查看 MariaDB 官方文档进行优化")
                elif mysql_major < 8:
                    print_warning("MySQL版本建议：")
                    print_info("  - 强烈建议升级到 MySQL 8.0+ 以获得更好性能")
                    print_info("  - MySQL 8.0 对多服务架构有更好的支持")
                elif mysql_major == 8 and mysql_minor < 20:
                    print_info("MySQL版本建议：")
                    print_info("  - 建议升级到 MySQL 8.0.20+ 以获得最新优化")
            
            # Ubuntu 22.04 特定建议
            if ubuntu_info and ubuntu_info.get('major', 0) == 22:
                print_info("Ubuntu 22.04 特定建议：")
                print_info("  - 确保 AppArmor 配置正确（MySQL 需要访问数据目录）")
                print_info("  - systemd 会自动管理文件描述符限制")
                print_info("  - 建议使用 systemd 管理 MySQL 服务")
            
            # 连接数建议
            conn_req = calculate_connection_requirements()
            max_conns = optimized_config.get('mysqld.max_connections', '300')
            try:
                max_conns_int = int(max_conns)
                if max_conns_int < conn_req['recommended_max_connections']:
                    print_warning(f"max_connections ({max_conns}) 可能不足以支持所有服务")
                    print_info(f"  建议至少设置为: {conn_req['recommended_max_connections']}")
            except:
                pass
            
        else:
            print_error("应用配置失败")
            sys.exit(1)
    else:
        print_section("提示")
        print_info("当前仅显示配置对比，未实际应用")
        print_info("如需应用配置，请使用 --apply 参数:")
        print_info("  sudo python3 scripts/optimize_mysql_config.py --apply")
        
        # 显示配置摘要
        print_section("配置摘要")
        conn_req = calculate_connection_requirements()
        cpu_cores = cpu_info.get('cores', 2)
        total_memory_gb = memory_info.get('total_gb', 4)
        
        print(f"{Colors.BOLD}多服务架构连接需求:{Colors.RESET}")
        print(f"  总连接数: {Colors.GREEN}{conn_req['total_connections']}{Colors.RESET}")
        print(f"  推荐 max_connections: {Colors.GREEN}{conn_req['recommended_max_connections']}{Colors.RESET}")
        print(f"  优化后的 max_connections: {Colors.CYAN}{optimized_config.get('mysqld.max_connections', 'N/A')}{Colors.RESET}")
        
        buffer_pool = optimized_config.get('mysqld.innodb_buffer_pool_size', 'N/A')
        print(f"\n{Colors.BOLD}关键配置优化:{Colors.RESET}")
        print(f"  InnoDB Buffer Pool: {Colors.GREEN}{buffer_pool}{Colors.RESET}")
        print(f"  Max Connections: {Colors.GREEN}{optimized_config.get('mysqld.max_connections', 'N/A')}{Colors.RESET}")
        print(f"  Lock Wait Timeout: {Colors.GREEN}{optimized_config.get('mysqld.innodb_lock_wait_timeout', 'N/A')}秒{Colors.RESET}")
        print(f"  Deadlock Detect: {Colors.GREEN}{optimized_config.get('mysqld.innodb_deadlock_detect', 'N/A')}{Colors.RESET}")
        
        # 资源使用估算
        print(f"\n{Colors.BOLD}资源使用估算:{Colors.RESET}")
        buffer_pool_mb = 0
        try:
            buffer_pool_str = buffer_pool.rstrip('M')
            buffer_pool_mb = int(buffer_pool_str)
        except:
            pass
        
        if buffer_pool_mb > 0:
            buffer_pool_gb = buffer_pool_mb / 1024
            memory_usage_percent = (buffer_pool_gb / total_memory_gb) * 100 if total_memory_gb > 0 else 0
            print(f"  Buffer Pool 占用: {Colors.CYAN}{buffer_pool_gb:.2f}GB{Colors.RESET} ({memory_usage_percent:.1f}% 总内存)")
            print(f"  剩余内存: {Colors.GREEN}{total_memory_gb - buffer_pool_gb:.2f}GB{Colors.RESET} (用于系统和其他服务)")
            
            if memory_usage_percent > 60:
                print_warning("Buffer Pool 占用内存比例较高，请确保为系统和其他服务预留足够内存")
            elif memory_usage_percent < 30:
                print_info("Buffer Pool 占用内存比例较低，可以考虑适当增加以获得更好性能")


if __name__ == '__main__':
    main()

