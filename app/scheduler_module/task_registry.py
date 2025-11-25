"""
任务注册表
将数据库中的任务名称映射到实际的任务函数
"""
from typing import Dict, Callable, Optional, Any
import logging

logger = logging.getLogger(__name__)

# 任务注册表：任务名称 -> 任务函数
TASK_REGISTRY: Dict[str, Callable[..., Any]] = {}


def register_task_function(
        task_name: str,
        task_func: Callable[..., Any]
) -> None:
    """
    注册任务函数到注册表
    
    Args:
        task_name: 任务名称（与数据库中的 task_name 对应）
        task_func: 任务函数（可以是同步或异步函数）
        
    Raises:
        ValueError: 如果 task_name 已存在且 task_func 不同
    """
    if task_name in TASK_REGISTRY:
        existing_func = TASK_REGISTRY[task_name]
        if existing_func is not task_func:
            logger.warning(
                f"任务 '{task_name}' 已注册，将覆盖原有函数 "
                f"({existing_func.__name__} -> {task_func.__name__})"
            )

    TASK_REGISTRY[task_name] = task_func
    logger.debug(
        f"任务函数已注册: '{task_name}' -> {task_func.__name__}"
    )


def get_task_function(task_name: str) -> Optional[Callable[..., Any]]:
    """
    从注册表获取任务函数
    
    Args:
        task_name: 任务名称
        
    Returns:
        任务函数，如果不存在返回 None
    """
    return TASK_REGISTRY.get(task_name)


def get_task_function_by_name_or_path(
        task_name: str,
        function_path: Optional[str] = None
) -> Optional[Callable[..., Any]]:
    """
    获取任务函数（优先使用 function_path，否则从注册表查找）
    
    这是统一的函数获取逻辑，用于避免代码重复
    
    Args:
        task_name: 任务名称
        function_path: 函数路径（可选，如果提供则优先使用）
        
    Returns:
        任务函数，如果不存在返回 None
    """
    task_func = None

    # 优先使用 function_path（如果指定）
    if function_path:
        task_func = load_function_by_path(function_path)
        if task_func:
            logger.debug(f"任务 '{task_name}' 使用函数路径加载: {function_path}")

    # 如果 function_path 未指定或加载失败，从注册表查找
    if task_func is None:
        task_func = get_task_function(task_name)
        if task_func:
            logger.debug(f"任务 '{task_name}' 从注册表加载")

    return task_func


def load_function_by_path(function_path: str) -> Optional[Callable[..., Any]]:
    """
    根据函数路径动态加载函数
    
    Args:
        function_path: 函数完整路径，格式：module.path.function_name
                     例如：app.scheduler_module.tasks.simple_task.simple_info_task
        
    Returns:
        函数对象，如果加载失败返回 None
    """
    try:
        # 分割模块路径和函数名
        parts = function_path.rsplit('.', 1)
        if len(parts) != 2:
            logger.error(f"函数路径格式错误: {function_path}，应为 'module.path.function_name'")
            return None

        module_path, function_name = parts

        # 动态导入模块
        module = __import__(module_path, fromlist=[function_name])

        # 获取函数
        if hasattr(module, function_name):
            func = getattr(module, function_name)
            if callable(func):
                logger.info(f"成功加载函数: {function_path}")
                return func
            else:
                logger.error(f"'{function_path}' 不是可调用对象")
                return None
        else:
            logger.error(f"模块 '{module_path}' 中不存在函数 '{function_name}'")
            return None

    except ImportError as e:
        logger.error(f"导入模块失败: {function_path}, 错误: {e}")
        return None
    except Exception as e:
        logger.error(f"加载函数失败: {function_path}, 错误: {e}", exc_info=True)
        return None


def get_task_function_info(task_name: str, function_path: Optional[str] = None) -> Optional[dict[str, str]]:
    """
    获取任务函数信息（函数名和模块路径）
    
    Args:
        task_name: 任务名称
        function_path: 函数路径（可选，如果提供则优先使用）
        
    Returns:
        包含 function_name 和 function_module 的字典，如果任务不存在返回 None
    """
    # 使用统一的函数获取逻辑
    task_func = get_task_function_by_name_or_path(task_name, function_path)

    if task_func is None:
        return None

    # 获取函数名
    function_name = task_func.__name__

    # 获取模块路径
    module = getattr(task_func, '__module__', None)
    function_module = module if module else "未知模块"

    return {
        "function_name": function_name,
        "function_module": function_module
    }


def get_all_registered_tasks() -> Dict[str, Callable[..., Any]]:
    """
    获取所有已注册的任务
    
    Returns:
        任务名称到任务函数的字典（副本，修改不会影响原注册表）
    """
    return TASK_REGISTRY.copy()


# 自动注册所有可用的任务函数
def auto_register_tasks() -> None:
    """自动注册所有任务函数"""
    
    # 导入任务名称常量
    from app.scheduler_module.task_names import (
        TQT_API_TASK_NAME,
        SKYMOBI_API_TASK_NAME,
        ARCHIVE_DATA_TASK_NAME,
        CLEANUP_SESSIONS_TASK_NAME,
        CLEANUP_LOGS_TASK_NAME,
        TBSJ_API_TASK_NAME,
    )
    
    # 注册数据归档任务
    from app.scheduler_module.tasks.archive_old_data import archive_old_ad_data
    register_task_function(ARCHIVE_DATA_TASK_NAME, archive_old_ad_data)

    # 注册清理过期会话和黑名单记录任务（使用 cleanup_expired_sessions，功能更完整）
    from app.scheduler_module.tasks.cleanup_expired_sessions import cleanup_expired_sessions
    register_task_function(CLEANUP_SESSIONS_TASK_NAME, cleanup_expired_sessions)

    # 注册清理旧日志任务
    from app.scheduler_module.tasks.cleanup_old_logs import cleanup_old_audit_logs
    from app.core.config import settings
    
    # 创建包装函数，使用配置中的参数
    async def cleanup_old_logs_wrapper():
        """清理旧日志任务的包装函数，使用配置中的参数"""
        return await cleanup_old_audit_logs(
            days=settings.AUDIT_LOG_RETENTION_DAYS,
            archive=settings.AUDIT_LOG_ARCHIVE
        )
    
    register_task_function(CLEANUP_LOGS_TASK_NAME, cleanup_old_logs_wrapper)

    # 注册 TQT API获取数据 任务
    from app.scheduler_module.tasks.tqt_task import tqt_api_task
    register_task_function(TQT_API_TASK_NAME, tqt_api_task)
    
    # 注册 Skymobi API获取数据 任务
    from app.scheduler_module.tasks.skymobi_task import skymobi_api_task
    register_task_function(SKYMOBI_API_TASK_NAME, skymobi_api_task)

    # 注册 yangyangdeyi API获取数据 任务
    from app.scheduler_module.tasks.tbsj_task import tbsj_api_task
    register_task_function(TBSJ_API_TASK_NAME, tbsj_api_task)