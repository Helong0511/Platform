"""
任务结果注册表
用于统一管理所有定时任务的执行结果获取函数
"""
from typing import Dict, Callable, Optional
import logging
import re

from app.scheduler_module.task_config import TASK_CONFIGS

logger = logging.getLogger(__name__)


def _validate_module_path(module_path: str) -> bool:
    """
    验证模块路径是否安全（白名单验证）
    
    只允许导入 app. 开头的模块，防止代码注入攻击
    
    Args:
        module_path: 模块路径
        
    Returns:
        如果路径安全返回 True，否则返回 False
    """
    if not module_path:
        return False
    
    # 只允许导入 app. 开头的模块（应用内部模块）
    if not module_path.startswith('app.'):
        logger.warning(f"拒绝导入非应用模块: {module_path}（只允许导入 app. 开头的模块）")
        return False
    
    # 验证路径格式（只允许字母、数字、点、下划线）
    if not re.match(r'^[a-zA-Z0-9_.]+$', module_path):
        logger.warning(f"模块路径格式无效: {module_path}（包含非法字符）")
        return False
    
    # 禁止相对导入（..）
    if '..' in module_path:
        logger.warning(f"拒绝相对导入: {module_path}")
        return False
    
    return True

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
    
    registered_count = 0
    failed_count = 0
    
    for config_key, config in TASK_CONFIGS.items():
        try:
            task_name = config["task_name"]
            result_getter_module = config["result_getter_module"]
            result_getter_function = config["result_getter_function"]
            
            # ====== 安全验证：验证模块路径 ======
            if not _validate_module_path(result_getter_module):
                logger.error(
                    f"任务结果获取模块路径验证失败: '{result_getter_module}' (任务: '{task_name}') - 安全策略拒绝"
                )
                failed_count += 1
                continue

            # 验证函数名格式
            if not re.match(r'^[a-zA-Z0-9_]+$', result_getter_function):
                logger.error(
                    f"任务结果获取函数名格式无效: '{result_getter_function}' (任务: '{task_name}') - 只允许字母、数字、下划线"
                )
                failed_count += 1
                continue

            # 动态导入结果获取函数（已通过安全验证）
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

