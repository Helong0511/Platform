"""
Telegram Bot 文件锁管理

提供跨平台的文件锁功能，确保多进程环境下只有一个进程启动 Bot
"""
import os
import stat
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


# 常量定义
DEFAULT_LOCK_FILE_NAME = "telegram_bot.lock"
LOCK_EXPIRE_SECONDS = 3600  # 锁文件过期时间：1小时


# 全局锁状态
_bot_lock_file = None
_bot_lock_acquired = False


def get_default_lock_path() -> Path:
    """获取默认的锁文件路径（项目根目录 logs/，与 app.log 一致）"""
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / DEFAULT_LOCK_FILE_NAME


def _is_lock_expired(lock_file_path: Path) -> bool:
    """检查锁文件是否已过期"""
    try:
        if not lock_file_path.exists():
            return False
        
        # 读取锁文件中的时间戳
        with open(lock_file_path, 'r') as f:
            content = f.read()
        
        # 解析时间戳
        timestamp = None
        for line in content.split('\n'):
            if line.startswith('Timestamp:'):
                try:
                    timestamp = float(line.split(':')[1].strip())
                    break
                except (IndexError, ValueError):
                    continue
        
        if timestamp is None:
            # 无法读取时间戳，检查文件修改时间
            file_mtime = lock_file_path.stat().st_mtime
            return (time.time() - file_mtime) > LOCK_EXPIRE_SECONDS
        
        return (time.time() - timestamp) > LOCK_EXPIRE_SECONDS
        
    except Exception as e:
        logger.warning(f"检查锁文件过期状态时出错：{e}")
        return False


def _get_lock_pid(lock_file_path: Path) -> Optional[int]:
    """获取锁文件中记录的PID"""
    try:
        if not lock_file_path.exists():
            return None
        
        with open(lock_file_path, 'r') as f:
            content = f.read()
        
        for line in content.split('\n'):
            if line.startswith('PID:'):
                try:
                    pid = int(line.split(':')[1].strip())
                    return pid
                except (IndexError, ValueError):
                    continue
        
        return None
    except Exception as e:
        logger.warning(f"读取锁文件PID时出错：{e}")
        return None


def _is_process_running(pid: int) -> bool:
    """检查进程是否正在运行"""
    try:
        # 不同平台的进程检查
        if os.name == 'posix':  # Unix/Linux
            os.kill(pid, 0)
            return True
        elif os.name == 'nt':  # Windows
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(1, 0, pid)
            if handle == 0:
                return False
            kernel32.CloseHandle(handle)
            return True
        return False
    except (OSError, ValueError):
        return False


def _cleanup_expired_lock(lock_file_path: Path):
    """清理过期的锁文件"""
    try:
        if lock_file_path.exists():
            lock_file_path.unlink()
            logger.info(f"已清理过期的锁文件：{lock_file_path}")
    except Exception as e:
        logger.warning(f"清理过期锁文件失败：{e}")


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


def acquire_bot_lock(lock_file_path: Optional[Path] = None, max_retries: int = 15) -> bool:
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
        lock_file_path = get_default_lock_path()
    
    try:
        # 确保日志目录存在
        lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 检查是否有过期的锁文件需要清理
        if lock_file_path.exists():
            # 检查锁文件是否过期
            if _is_lock_expired(lock_file_path):
                logger.info(f"[PID:{current_pid}] 检测到过期的锁文件，正在清理...")
                _cleanup_expired_lock(lock_file_path)
            else:
                # 检查锁文件对应的进程是否正在运行
                lock_pid = _get_lock_pid(lock_file_path)
                if lock_pid and not _is_process_running(lock_pid):
                    logger.info(f"[PID:{current_pid}] 检测到锁文件对应的进程（PID:{lock_pid}）已停止，正在清理锁文件...")
                    _cleanup_expired_lock(lock_file_path)
                else:
                    # 锁文件存在且进程正在运行
                    logger.info(f"[PID:{current_pid}] 检测到锁文件已存在，其他进程可能已启动 Bot")
                    return False
        
        # 额外的安全检查：尝试删除可能存在的锁文件
        # 这是为了防止锁文件被永久占用
        try:
            if lock_file_path.exists():
                logger.warning(f"[PID:{current_pid}] 锁文件仍然存在，尝试强制清理...")
                _cleanup_expired_lock(lock_file_path)
        except Exception as e:
            logger.warning(f"[PID:{current_pid}] 强制清理锁文件失败：{e}")
        
        retry_delay = 0.5  # 初始重试延迟
        for attempt in range(1, max_retries + 1):
            try:
                # 尝试创建锁文件（使用独占模式）
                # 先检查文件是否存在，避免竞争条件
                if lock_file_path.exists():
                    # 再次检查进程状态
                    lock_pid = _get_lock_pid(lock_file_path)
                    if lock_pid and not _is_process_running(lock_pid):
                        logger.info(f"[PID:{current_pid}] 检测到锁文件对应的进程（PID:{lock_pid}）已停止，正在清理锁文件...")
                        _cleanup_expired_lock(lock_file_path)
                    else:
                        logger.info(f"[PID:{current_pid}] 锁文件已存在（尝试 {attempt}/{max_retries}），其他进程已启动")
                        return False
                
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
                        _bot_lock_file.write(f"Hostname: {os.uname().nodename if hasattr(os, 'uname') else 'unknown'}\n")
                        _bot_lock_file.flush()
                        os.fsync(_bot_lock_file.fileno())  # 确保写入磁盘
                        _bot_lock_acquired = True
                        logger.info(f"[PID:{current_pid}] 成功获取 Telegram Bot 启动锁（fcntl，尝试 {attempt}/{max_retries}）")
                        return True
                    except (IOError, OSError) as e:
                        # 锁已被其他进程持有
                        _close_lock_file()
                        if attempt < max_retries:
                            logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（其他进程已启动），{retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                            retry_delay *= 1.5  # 指数退避
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
                        _bot_lock_file.write(f"Hostname: {os.environ.get('COMPUTERNAME', 'unknown')}\n")
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
                            retry_delay *= 1.5
                        else:
                            logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（其他进程已启动）")
                        continue
                else:
                    # 没有文件锁支持，使用简单的文件存在性检查
                    lock_file_tmp = lock_file_path.with_suffix('.lock.tmp')
                    try:
                        # 再次检查目标文件是否存在
                        if lock_file_path.exists():
                            # 检查进程状态
                            lock_pid = _get_lock_pid(lock_file_path)
                            if lock_pid and not _is_process_running(lock_pid):
                                logger.info(f"[PID:{current_pid}] 检测到锁文件对应的进程（PID:{lock_pid}）已停止，正在清理锁文件...")
                                _cleanup_expired_lock(lock_file_path)
                            else:
                                logger.info(f"[PID:{current_pid}] 锁文件已存在（尝试 {attempt}/{max_retries}），其他进程已启动")
                                if lock_file_tmp.exists():
                                    lock_file_tmp.unlink()
                                return False
                        
                        # 创建临时文件
                        with open(lock_file_tmp, 'w') as f:
                            f.write(f"PID: {current_pid}\n")
                            f.write(f"Timestamp: {time.time()}\n")
                            f.write(f"Hostname: {os.uname().nodename if hasattr(os, 'uname') else 'unknown'}\n")
                        
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
                            retry_delay *= 1.5
                        else:
                            logger.info(f"[PID:{current_pid}] 无法获取 Telegram Bot 启动锁（其他进程可能已启动）: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"[PID:{current_pid}] 获取 Telegram Bot 启动锁时发生错误（尝试 {attempt}/{max_retries}）: {e}")
                _close_lock_file()
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
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
            lock_file_path = get_default_lock_path()
            logger.info(f"[PID:{current_pid}] 释放锁文件：{lock_file_path}")
            
            # 跨平台释放锁
            if HAS_FCNTL:
                # Unix/Linux: 使用 fcntl
                try:
                    fcntl.flock(_bot_lock_file.fileno(), fcntl.LOCK_UN)
                    logger.info(f"[PID:{current_pid}] 已释放 fcntl 锁")
                except Exception as lock_error:
                    logger.warning(f"[PID:{current_pid}] 释放 fcntl 锁时发生错误：{lock_error}")
            elif HAS_MSVCRT:
                # Windows: 使用 msvcrt
                try:
                    msvcrt.locking(_bot_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    logger.info(f"[PID:{current_pid}] 已释放 msvcrt 锁")
                except Exception as lock_error:
                    logger.warning(f"[PID:{current_pid}] 释放 msvcrt 锁时发生错误：{lock_error}")
            
            # 关闭锁文件
            try:
                _bot_lock_file.close()
                logger.info(f"[PID:{current_pid}] 已关闭锁文件")
            except Exception as close_error:
                logger.warning(f"[PID:{current_pid}] 关闭锁文件时发生错误：{close_error}")
            
            # 删除锁文件（如果存在）
            if lock_file_path and lock_file_path.exists():
                try:
                    lock_file_path.unlink()
                    logger.info(f"[PID:{current_pid}] 已删除锁文件")
                except Exception as e:
                    logger.warning(f"[PID:{current_pid}] 删除锁文件时发生错误：{e}")
                    # 尝试强制删除
                    try:
                        os.chmod(lock_file_path, stat.S_IWRITE)
                        lock_file_path.unlink()
                        logger.info(f"[PID:{current_pid}] 已强制删除锁文件")
                    except Exception as force_error:
                        logger.warning(f"[PID:{current_pid}] 强制删除锁文件时发生错误：{force_error}")
            
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
                    # 尝试强制删除
                    try:
                        os.chmod(lock_file_path, stat.S_IWRITE)
                        lock_file_path.unlink()
                    except Exception as force_error:
                        logger.warning(f"[PID:{current_pid}] 强制删除锁文件时发生错误：{force_error}")
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
