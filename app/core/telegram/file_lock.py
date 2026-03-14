"""
Telegram Bot 文件锁管理

提供跨平台的文件锁功能，确保多进程环境下只有一个进程启动 Bot
"""
import os
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 跨平台文件锁支持
HAS_FCNTL = False
HAS_MSVCRT = False

try:
    import fcntl  # Unix/Linux 文件锁
    HAS_FCNTL = True
except ImportError:
    # Windows 使用 msvcrt 实现文件锁
    try:
        import msvcrt
        HAS_MSVCRT = True
    except ImportError:
        logger.warning("无法导入文件锁模块（fcntl/msvcrt），文件锁功能将不可用")


# 全局锁状态
_bot_lock_file = None
_bot_lock_acquired = False


def _close_lock_file():
    """安全关闭锁文件"""
    global _bot_lock_file
    if _bot_lock_file:
        try:
            _bot_lock_file.close()
        except Exception:
            pass
        finally:
            _bot_lock_file = None


def acquire_bot_lock(lock_file_path: Optional[Path] = None, max_retries: int = 3) -> bool:
    """
    获取 Bot 启动锁（多进程环境）
    
    Args:
        lock_file_path: 锁文件路径（可选，默认使用 logs/telegram_bot.lock）
        max_retries: 最大重试次数
    
    Returns:
        bool: 是否成功获取锁
    """
    global _bot_lock_file, _bot_lock_acquired
    
    current_pid = os.getpid()
    
    if lock_file_path is None:
        lock_file_path = Path(__file__).parent.parent.parent / "logs" / "telegram_bot.lock"
    
    try:
        # 确保日志目录存在
        lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        retry_delay = 0.1  # 初始重试延迟
        for attempt in range(1, max_retries + 1):
            try:
                # 尝试打开锁文件（如果不存在则创建）
                _bot_lock_file = open(lock_file_path, 'w')
                
                # 跨平台获取锁
                if HAS_FCNTL:
                    # Unix/Linux: 使用 fcntl
                    try:
                        fcntl.flock(_bot_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        # 写入进程信息
                        _bot_lock_file.write(f"PID: {current_pid}\n")
                        _bot_lock_file.write(f"Timestamp: {time.time()}\n")
                        _bot_lock_file.flush()
                        _bot_lock_acquired = True
                        logger.info(f"[PID:{current_pid}] 成功获取 Telegram Bot 启动锁（fcntl，尝试 {attempt}/{max_retries}）")
                        return True
                    except (IOError, OSError) as e:
                        # 锁已被其他进程持有
                        _close_lock_file()
                        if attempt < max_retries:
                            logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（其他进程已启动），{retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # 指数退避
                        else:
                            logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（其他进程已启动）")
                        continue
                        
                elif HAS_MSVCRT:
                    # Windows: 使用 msvcrt
                    try:
                        msvcrt.locking(_bot_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                        # 写入进程信息
                        _bot_lock_file.write(f"PID: {current_pid}\n")
                        _bot_lock_file.write(f"Timestamp: {time.time()}\n")
                        _bot_lock_file.flush()
                        _bot_lock_acquired = True
                        logger.info(f"[PID:{current_pid}] 成功获取 Telegram Bot 启动锁（msvcrt，尝试 {attempt}/{max_retries}）")
                        return True
                    except (IOError, OSError) as e:
                        # 锁已被其他进程持有
                        _close_lock_file()
                        if attempt < max_retries:
                            logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（其他进程已启动），{retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（其他进程已启动）")
                        continue
                else:
                    # 没有文件锁支持，使用简单的文件存在性检查
                    lock_file_tmp = lock_file_path.with_suffix('.lock.tmp')
                    try:
                        # 创建临时文件
                        with open(lock_file_tmp, 'w') as f:
                            f.write(f"PID: {current_pid}\n")
                            f.write(f"Timestamp: {time.time()}\n")
                        
                        # 尝试原子重命名操作
                        lock_file_tmp.rename(lock_file_path)
                        _bot_lock_file = open(lock_file_path, 'r+')
                        _bot_lock_acquired = True
                        logger.info(f"[PID:{current_pid}] 成功获取 Telegram Bot 启动锁（原子重命名，尝试 {attempt}/{max_retries}）")
                        return True
                    except (IOError, OSError) as e:
                        # 重命名失败，说明其他进程已持有锁
                        try:
                            if lock_file_tmp.exists():
                                lock_file_tmp.unlink()
                        except:
                            pass
                        if attempt < max_retries:
                            logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（其他进程可能已启动），{retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（其他进程可能已启动）: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"[PID:{current_pid}] 获取 Telegram Bot 启动锁时发生错误（尝试 {attempt}/{max_retries}）: {e}")
                _close_lock_file()
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    return False
                    
    except Exception as e:
        logger.warning(f"[PID:{current_pid}] 获取 Telegram Bot 启动锁时发生错误：{e}")
        _close_lock_file()
        return False
    
    return False


def release_bot_lock():
    """释放 Bot 启动锁"""
    global _bot_lock_file, _bot_lock_acquired
    
    if _bot_lock_file and _bot_lock_acquired:
        current_pid = os.getpid()
        lock_file_path = None
        
        try:
            # 获取锁文件路径
            lock_file_path = Path(__file__).parent.parent.parent / "logs" / "telegram_bot.lock"
            logger.info(f"[PID:{current_pid}] 释放锁文件：{lock_file_path}")
            
            # 跨平台释放锁
            if HAS_FCNTL:
                # Unix/Linux: 使用 fcntl
                fcntl.flock(_bot_lock_file.fileno(), fcntl.LOCK_UN)
                logger.info(f"[PID:{current_pid}] 已释放 fcntl 锁")
            elif HAS_MSVCRT:
                # Windows: 使用 msvcrt
                msvcrt.locking(_bot_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                logger.info(f"[PID:{current_pid}] 已释放 msvcrt 锁")
            
            _bot_lock_file.close()
            logger.info(f"[PID:{current_pid}] 已关闭锁文件")
            
            # 删除锁文件（如果存在）
            if lock_file_path and lock_file_path.exists():
                try:
                    lock_file_path.unlink()
                    logger.info(f"[PID:{current_pid}] 已删除锁文件")
                except Exception as e:
                    logger.warning(f"[PID:{current_pid}] 删除锁文件时发生错误：{e}")
            
            # 重置锁状态
            _bot_lock_file = None
            _bot_lock_acquired = False
            
            logger.info(f"[PID:{current_pid}] 已释放 Telegram Bot 启动锁")
            
        except Exception as e:
            logger.warning(f"[PID:{current_pid}] 释放 Telegram Bot 启动锁时发生错误：{e}")
            # 确保文件被关闭
            try:
                if _bot_lock_file:
                    _bot_lock_file.close()
            except Exception as close_error:
                logger.warning(f"[PID:{current_pid}] 关闭锁文件时发生错误：{close_error}")
            # 尝试删除锁文件
            if lock_file_path and lock_file_path.exists():
                try:
                    lock_file_path.unlink()
                except Exception as unlink_error:
                    logger.warning(f"[PID:{current_pid}] 删除锁文件时发生错误：{unlink_error}")
            # 重置锁状态
            _bot_lock_file = None
            _bot_lock_acquired = False
    else:
        current_pid = os.getpid()
        logger.info(f"[PID:{current_pid}] 没有持有锁，无需释放")


def is_lock_held() -> bool:
    """
    检查当前进程是否持有锁
    
    Returns:
        bool: 是否持有锁
    """
    return _bot_lock_acquired and _bot_lock_file is not None
