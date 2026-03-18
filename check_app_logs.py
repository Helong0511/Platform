#!/usr/bin/env python3
"""
检查应用启动日志
"""
from pathlib import Path

print("=" * 80)
print("检查应用启动日志")
print("=" * 80)

# 检查 app.log 的最后 100 行
print("\n[步骤 1] 检查 app.log 的最后 100 行...")
app_log = Path('/data/Platform/logs/app.log')

if app_log.exists():
    with open(app_log, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"  日志文件总行数: {len(lines)}")
    print(f"  最后 100 行：")
    print("=" * 80)
    for line in lines[-100:]:
        print(line.rstrip())
    print("=" * 80)
else:
    print("  ❌ 日志文件不存在")

# 检查是否有其他日志文件
print("\n[步骤 2] 检查其他日志文件...")
logs_dir = Path('/data/Platform/logs')

if logs_dir.exists():
    log_files = list(logs_dir.glob('*.log'))
    print(f"  发现 {len(log_files)} 个日志文件：")
    for log_file in log_files:
        size = log_file.stat().st_size
        print(f"    {log_file.name}: {size} bytes")
else:
    print("  ❌ 日志目录不存在")

# 检查 error.log
print("\n[步骤 3] 检查 error.log...")
error_log = Path('/data/Platform/logs/error.log')

if error_log.exists():
    with open(error_log, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if content.strip():
        print(f"  error.log 内容：")
        print(content)
    else:
        print(f"  ✅ error.log 为空")
else:
    print("  ❌ error.log 不存在")

# 检查 gunicorn_error.log
print("\n[步骤 4] 检查 gunicorn_error.log...")
gunicorn_error_log = Path('/data/Platform/logs/gunicorn_error.log')

if gunicorn_error_log.exists():
    with open(gunicorn_error_log, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if content.strip():
        print(f"  gunicorn_error.log 内容：")
        print(content)
    else:
        print(f"  ✅ gunicorn_error.log 为空")
else:
    print("  ❌ gunicorn_error.log 不存在")

print("\n" + "=" * 80)
print("日志检查完成")
print("=" * 80)
