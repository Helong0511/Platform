#!/usr/bin/env python3
"""
检查并清理 Telegram Bot 状态文件
"""
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, '/data/Platform')

print("=" * 80)
print("检查和清理 Telegram Bot 状态文件")
print("=" * 80)

# 1. 检查状态文件
print("\n[步骤 1] 检查状态文件...")
state_file = Path('/data/Platform/logs/telegram_bot_state.json')

if state_file.exists():
    print(f"  ✅ 状态文件存在: {state_file}")
    
    # 读取状态文件内容
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            import json
            state = json.load(f)
        print(f"  📋 状态文件内容：")
        for key, value in state.items():
            print(f"     {key}: {value}")
    except Exception as e:
        print(f"  ❌ 读取状态文件失败: {e}")
else:
    print(f"  ℹ️  状态文件不存在")

# 2. 检查锁文件
print("\n[步骤 2] 检查锁文件...")
lock_file = Path('/data/Platform/logs/telegram_bot.lock')

if lock_file.exists():
    print(f"  ⚠️  锁文件存在: {lock_file}")
    
    # 读取锁文件内容
    try:
        with open(lock_file, 'r') as f:
            content = f.read()
        print(f"  📋 锁文件内容：")
        print(content)
    except Exception as e:
        print(f"  ❌ 读取锁文件失败: {e}")
else:
    print(f"  ✅ 锁文件不存在")

# 3. 检查进程状态
print("\n[步骤 3] 检查进程状态...")
import re

# 检查状态文件中的 PID
if state_file.exists():
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            import json
            state = json.load(f)
        
        pid = state.get('current_pid')
        if pid:
            print(f"  状态文件中的 PID: {pid}")
            
            # 检查进程是否存在
            try:
                os.kill(pid, 0)
                print(f"  ✅ 进程 {pid} 正在运行")
            except OSError:
                print(f"  ❌ 进程 {pid} 未运行")
    except Exception as e:
        print(f"  ❌ 检查进程状态失败: {e}")

# 4. 清理过时的状态文件
print("\n[步骤 4] 清理过时的状态文件...")
if state_file.exists():
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            import json
            state = json.load(f)
        
        pid = state.get('current_pid')
        if pid:
            try:
                os.kill(pid, 0)
                print(f"  ⚠️  进程 {pid} 正在运行，不清理状态文件")
            except OSError:
                print(f"  ✅ 进程 {pid} 未运行，清理状态文件")
                state_file.unlink()
                print(f"  ✅ 状态文件已删除")
        else:
            print(f"  ✅ 状态文件中没有 PID，清理状态文件")
            state_file.unlink()
            print(f"  ✅ 状态文件已删除")
    except Exception as e:
        print(f"  ❌ 清理状态文件失败: {e}")

# 5. 清理锁文件
print("\n[步骤 5] 清理锁文件...")
if lock_file.exists():
    try:
        lock_file.unlink()
        print(f"  ✅ 锁文件已删除")
    except Exception as e:
        print(f"  ❌ 删除锁文件失败: {e}")

print("\n" + "=" * 80)
print("清理完成")
print("=" * 80)
print("\n建议:")
print("1. 重启应用以重新初始化 Telegram Bot")
print("2. 检查应用日志中的 Telegram 启动信息")
print("3. 测试 Telegram 机器人命令响应")
