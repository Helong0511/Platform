"""
检查运行中的 Telegram Bot 实例

查看持有锁的进程和消息处理情况
"""
import os
import sys
import time
import logging
from pathlib import Path

# 设置日志配置
log_file = Path(__file__).parent.parent / "logs" / "check_bot.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 确保可以导入 app 模块
sys.path.insert(0, '.')

if __name__ == "__main__":
    print("=" * 80)
    print("🔍 检查运行中的 Bot 实例")
    print("=" * 80)
    
    try:
        # 1. 检查锁文件
        from app.core.telegram.file_lock import get_default_lock_path, _get_lock_pid, _is_process_running
        
        lock_path = get_default_lock_path()
        logger.info(f"锁文件路径: {lock_path}")
        
        if lock_path.exists():
            logger.info("✅ 锁文件存在")
            # 读取锁文件内容
            with open(lock_path, 'r') as f:
                lock_content = f.read()
            logger.info(f"锁文件内容:\n{lock_content}")
            
            # 获取锁文件中的 PID
            lock_pid = _get_lock_pid(lock_path)
            if lock_pid:
                logger.info(f"锁文件中的 PID: {lock_pid}")
                # 检查进程是否在运行
                is_running = _is_process_running(lock_pid)
                logger.info(f"进程 {lock_pid} 运行状态: {is_running}")
                
                if is_running:
                    # 查看进程详情
                    if os.name == 'posix':
                        import subprocess
                        result = subprocess.run(['ps', 'aux', '--forest'], capture_output=True, text=True)
                        logger.info("进程树:")
                        for line in result.stdout.split('\n'):
                            if str(lock_pid) in line:
                                logger.info(f"  {line.strip()}")
                else:
                    logger.warning("❌ 进程未运行，锁文件可能已过期")
        else:
            logger.warning("❌ 锁文件不存在")
        
        # 2. 检查共享状态
        from app.core.telegram.shared_state import get_shared_state
        shared_state = get_shared_state()
        logger.info(f"共享状态: {shared_state}")
        
        # 3. 检查日志中的消息处理
        app_log = Path(__file__).parent.parent / "logs" / "app.log"
        if app_log.exists():
            logger.info("检查最近的消息处理日志...")
            with open(app_log, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()[-100:]  # 读取最后 100 行
            
            # 过滤 Telegram 相关日志
            telegram_lines = []
            for line in lines:
                if any(keyword in line.lower() for keyword in ['telegram', 'bot', 'message', 'command', '轮询']):
                    telegram_lines.append(line)
            
            if telegram_lines:
                logger.info("最近的 Telegram 相关日志:")
                for line in telegram_lines[-20:]:  # 显示最后 20 行
                    logger.info(f"  {line.strip()}")
            else:
                logger.info("未找到 Telegram 相关日志")
        else:
            logger.warning("❌ app.log 文件不存在")
        
        # 4. 检查 gunicorn 服务状态
        if os.name == 'posix':
            import subprocess
            result = subprocess.run(['sudo', 'systemctl', 'status', 'Platform-backend.service'], capture_output=True, text=True)
            logger.info("Gunicorn 服务状态:")
            logger.info(result.stdout)
        
        # 5. 检查是否有 409 错误
        if app_log.exists():
            with open(app_log, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if '409' in content or 'Conflict' in content:
                logger.warning("⚠️  检测到 409 冲突错误")
                # 查找 409 错误的上下文
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if '409' in line or 'Conflict' in line:
                        start = max(0, i-5)
                        end = min(len(lines), i+5)
                        logger.warning("409 错误上下文:")
                        for j in range(start, end):
                            logger.warning(f"  {lines[j]}")
                        break
        
        print("\n" + "=" * 80)
        print("📋 检查结果汇总:")
        print("=" * 80)
        
        print(f"✅ 锁文件存在: {lock_path.exists()}")
        if lock_path.exists():
            print(f"✅ 锁文件 PID: {lock_pid}")
            print(f"✅ 进程运行状态: {_is_process_running(lock_pid) if lock_pid else 'N/A'}")
        print(f"✅ 共享状态: {shared_state}")
        print(f"✅ 日志文件存在: {app_log.exists()}")
        
        print("\n🔧 建议操作:")
        print("1. 确认只有一个 Bot 实例在运行")
        print("2. 检查网络连接和 Telegram API 访问")
        print("3. 验证 Bot 有发送消息的权限")
        print("4. 测试 /id 命令响应")
        print("5. 查看详细日志获取更多信息")
        
    except Exception as e:
        logger.error(f"检查过程中发生错误: {e}", exc_info=True)
        print(f"\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
