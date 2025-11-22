"""
任务结果注册表
用于统一管理所有定时任务的执行结果获取函数
"""
from typing import Dict, Callable, Optional
import logging

logger = logging.getLogger(__name__)

# 任务结果获取函数注册表：任务名称 -> 结果获取函数
TASK_RESULT_REGISTRY: Dict[str, Callable[[str], Optional[str]]] = {}


def register_task_result_getter(
    task_name: str,
    get_result_func: Callable[[str], Optional[str]]
) -> None:
    """
    注册任务结果获取函数
    
    Args:
        task_name: 任务名称（与数据库中的 task_name 对应）
        get_result_func: 结果获取函数，接收 task_name 参数，返回结果字符串或 None
    """
    if task_name in TASK_RESULT_REGISTRY:
        logger.warning(f"任务 '{task_name}' 的结果获取函数已注册，将覆盖原有函数")
    
    TASK_RESULT_REGISTRY[task_name] = get_result_func
    logger.debug(f"任务结果获取函数已注册: '{task_name}'")


def get_task_result(task_name: str) -> Optional[str]:
    """
    从注册表获取任务执行结果
    
    Args:
        task_name: 任务名称
        
    Returns:
        任务执行结果字符串，如果不存在返回 None
    """
    get_result_func = TASK_RESULT_REGISTRY.get(task_name)
    if get_result_func:
        try:
            return get_result_func(task_name)
        except Exception as e:
            logger.debug(f"获取任务 '{task_name}' 的执行结果失败: {e}")
            return None
    return None


def auto_register_task_results() -> None:
    """
    自动注册所有任务的结果获取函数
    
    注册规则：
    1. 从 task_names.py 导入任务名称常量
    2. 从对应的任务模块导入 get_task_result 函数
    3. 使用任务名称常量注册结果获取函数
    
    添加新任务时：
    1. 在 task_names.py 中定义任务名称常量
    2. 在任务模块中实现 get_task_result 函数
    3. 在这里添加注册代码（参考下面的示例）
    """
    # 导入任务名称常量
    from app.scheduler_module.task_names import (
        TQT_API_TASK_NAME,
        SKYMOBI_API_TASK_NAME,
        ARCHIVE_DATA_TASK_NAME,
    )
    
    # ========== 注册 TQT API获取数据 任务的结果获取函数 ==========
    try:
        from app.scheduler_module.tasks.tqt_task import get_task_result as tqt_get_result
        register_task_result_getter(TQT_API_TASK_NAME, tqt_get_result)
        logger.debug(f"已注册任务结果获取函数: {TQT_API_TASK_NAME}")
    except ImportError as e:
        logger.warning(f"无法导入 TQT 任务结果获取函数: {e}")
    except Exception as e:
        logger.error(f"注册 TQT 任务结果获取函数失败: {e}")
    
    # ========== 注册 Skymobi API获取数据 任务的结果获取函数 ==========
    try:
        from app.scheduler_module.tasks.skymobi_task import get_task_result as skymobi_get_result
        register_task_result_getter(SKYMOBI_API_TASK_NAME, skymobi_get_result)
        logger.debug(f"已注册任务结果获取函数: {SKYMOBI_API_TASK_NAME}")
    except ImportError as e:
        logger.warning(f"无法导入 Skymobi 任务结果获取函数: {e}")
    except Exception as e:
        logger.error(f"注册 Skymobi 任务结果获取函数失败: {e}")
    
    # ========== 注册数据归档任务的结果获取函数 ==========
    try:
        from app.scheduler_module.tasks.archive_old_data import get_task_result as archive_get_result
        register_task_result_getter(ARCHIVE_DATA_TASK_NAME, archive_get_result)
        logger.debug(f"已注册任务结果获取函数: {ARCHIVE_DATA_TASK_NAME}")
    except ImportError as e:
        logger.warning(f"无法导入数据归档任务结果获取函数: {e}")
    except Exception as e:
        logger.error(f"注册数据归档任务结果获取函数失败: {e}")
    
    # ========== 在这里添加更多任务的结果获取函数注册 ==========
    # 示例：
    # from app.scheduler_module.task_names import NEW_TASK_NAME
    # try:
    #     from app.scheduler_module.tasks.new_task import get_task_result as new_task_get_result
    #     register_task_result_getter(NEW_TASK_NAME, new_task_get_result)
    #     logger.debug(f"已注册任务结果获取函数: {NEW_TASK_NAME}")
    # except ImportError as e:
    #     logger.warning(f"无法导入新任务结果获取函数: {e}")
    # except Exception as e:
    #     logger.error(f"注册新任务结果获取函数失败: {e}")

