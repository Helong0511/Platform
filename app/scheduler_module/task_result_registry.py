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
    从 task_config.py 统一配置文件读取所有任务配置并自动注册
    
    添加新任务时：
    1. 在任务模块中实现 get_task_result 函数
    2. 在 task_config.py 中添加任务配置即可（无需修改此文件）
    """
    from app.scheduler_module.task_config import TASK_CONFIGS
    
    registered_count = 0
    failed_count = 0
    
    for config_key, config in TASK_CONFIGS.items():
        try:
            task_name = config["task_name"]
            result_getter_module = config["result_getter_module"]
            result_getter_function = config["result_getter_function"]
            
            # 动态导入结果获取函数
            module = __import__(result_getter_module, fromlist=[result_getter_function])
            get_result_func = getattr(module, result_getter_function)
            
            # 注册结果获取函数
            register_task_result_getter(task_name, get_result_func)
            registered_count += 1
            logger.debug(f"已注册任务结果获取函数: {task_name}")
            
        except KeyError as e:
            logger.error(f"任务配置 '{config_key}' 缺少必要字段: {e}")
            failed_count += 1
        except ImportError as e:
            logger.warning(f"无法导入任务结果获取函数模块 '{result_getter_module}': {e}")
            failed_count += 1
        except AttributeError as e:
            logger.error(f"任务模块 '{result_getter_module}' 中不存在函数 '{result_getter_function}': {e}")
            failed_count += 1
        except Exception as e:
            logger.error(f"注册任务结果获取函数 '{config_key}' 失败: {e}", exc_info=True)
            failed_count += 1
    
    logger.info(f"任务结果获取函数注册完成: 成功 {registered_count} 个, 失败 {failed_count} 个")

