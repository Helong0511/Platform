#!/usr/bin/env python3
"""
检查服务器上应用和 Telegram 机器人的运行状态
"""
import os
import sys
import subprocess
from pathlib import Path

print("=" * 80)
print("服务器应用和 Telegram 机器人状态检查")
print("=" * 80)

# 1. 检查应用进程
print("\n[步骤 1] 检查应用进程...")
try:
    # 检查 Python 进程
    result = subprocess.run(
        ["ps", "aux", "|", "grep", "-E", "(uvicorn|gunicorn|python.*main.py)", "|", "grep", "-v", "grep"],
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.stdout.strip():
        print("  ✅ 发现应用进程：")
        print(result.stdout)
    else:
        print("  ❌ 未发现应用进程")
        print("  ⚠️  应用未运行，Telegram 机器人无法启动")
        sys.exit(1)
except Exception as e:
    print(f"  ❌ 检查进程失败: {e}")

# 2. 检查应用日志
print("\n[步骤 2] 检查应用日志...")
log_files = [
    "/data/Platform/logs/app.log",
    "/data/Platform/logs/gunicorn_error.log",
    "/data/Platform/logs/scheduler.log"
]

for log_file in log_files:
    if os.path.exists(log_file):
        print(f"  📄 日志文件存在: {log_file}")
        
        # 检查最近的 Telegram 相关日志
        try:
            result = subprocess.run(
                ["tail", "-n", "50", log_file, "|", "grep", "-i", "telegram"],
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.stdout.strip():
                print(f"  📋 最近的 Telegram 日志：")
                print(result.stdout)
            else:
                print(f"  ℹ️  未找到 Telegram 相关日志")
        except Exception as e:
            print(f"  ⚠️  读取日志失败: {e}")
    else:
        print(f"  ❌ 日志文件不存在: {log_file}")

# 3. 检查锁文件
print("\n[步骤 3] 检查锁文件状态...")
lock_file_path = Path("/data/Platform/logs/telegram_bot.lock")

if lock_file_path.exists():
    print(f"  ⚠️  锁文件存在: {lock_file_path}")
    try:
        with open(lock_file_path, 'r') as f:
            content = f.read()
        print(f"  📋 锁文件内容：")
        print(content)
        
        # 检查进程是否正在运行
        import re
        pid_match = re.search(r'PID:\s*(\d+)', content)
        if pid_match:
            pid = int(pid_match.group(1))
            print(f"  🔍 锁文件中的 PID: {pid}")
            
            # 检查进程是否正在运行
            try:
                os.kill(pid, 0)
                print(f"  ✅ 进程 {pid} 正在运行")
            except OSError:
                print(f"  ❌ 进程 {pid} 未运行，建议清理锁文件")
    except Exception as e:
        print(f"  ❌ 读取锁文件失败: {e}")
else:
    print(f"  ✅ 锁文件不存在")

# 4. 检查网络端口
print("\n[步骤 4] 检查网络端口...")
try:
    result = subprocess.run(
        ["netstat", "-tlnp", "|", "grep", ":8960"],
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.stdout.strip():
        print("  ✅ 发现监听端口 8960：")
        print(result.stdout)
    else:
        print("  ❌ 未发现监听端口 8960")
        print("  ⚠️  应用可能未正常运行")
except Exception as e:
    print(f"  ❌ 检查端口失败: {e}")

# 5. 检查 systemd 服务（如果使用）
print("\n[步骤 5] 检查 systemd 服务...")
try:
    result = subprocess.run(
        ["systemctl", "status", "platform_backend"],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("  ✅ platform_backend 服务正在运行")
        print(result.stdout)
    else:
        print("  ❌ platform_backend 服务未运行或不存在")
        print(result.stdout)
except Exception as e:
    print("  ℹ️  未使用 systemd 服务或检查失败")

print("\n" + "=" * 80)
print("状态检查完成")
print("=" * 80)

print("\n诊断建议：")
print("1. 如果应用进程未运行，请启动应用：")
print("   sudo systemctl start platform_backend")
print("   或：gunicorn -c gunicorn.conf.py app.main:app")
print("")
print("2. 如果锁文件存在但进程未运行，请清理锁文件：")
print("   rm /data/Platform/logs/telegram_bot.lock")
print("")
print("3. 检查应用日志，查看 Telegram 机器人启动信息：")
print("   tail -f /data/Platform/logs/app.log | grep -i telegram")
print("")
print("4. 测试 Telegram 机器人命令：")
print("   向 @Rx_Pay_Stat_Bot 发送 /start 命令")
