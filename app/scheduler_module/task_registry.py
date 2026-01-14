<<<<<<< HEAD
"""
任务注册表
将数据库中的任务名称映射到实际的任务函数
"""
import re
from typing import Dict, Callable, Optional, Any
import logging

from app.scheduler_module.task_config import TASK_CONFIGS
from app.core.config import settings

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


def load_function_by_path(function_path: str) -> Optional[Callable[..., Any]]:
    """
    根据函数路径动态加载函数
    
    安全特性：
    - 只允许导入 app. 开头的模块（应用内部模块）
    - 验证模块路径格式，防止代码注入
    - 禁止相对导入
    
    Args:
        function_path: 函数完整路径，格式：module.path.function_name
                     例如：app.scheduler_module.tasks.simple_task.simple_info_task
        
    Returns:
        函数对象，如果加载失败返回 None
    """
    if not function_path:
        logger.error("函数路径为空")
        return None
        
    try:
        # 分割模块路径和函数名
        parts = function_path.rsplit('.', 1)
        if len(parts) != 2:
            logger.error(f"函数路径格式错误: {function_path}，应为 'module.path.function_name'")
            return None

        module_path, function_name = parts

        # ====== 安全验证：验证模块路径 ======
        if not _validate_module_path(module_path):
            logger.error(f"模块路径验证失败: {module_path}（安全策略拒绝）")
            return None

        # 验证函数名格式（只允许字母、数字、下划线）
        if not re.match(r'^[a-zA-Z0-9_]+$', function_name):
            logger.error(f"函数名格式无效: {function_name}（只允许字母、数字、下划线）")
            return None

        # 动态导入模块（已通过安全验证）
        try:
            module = __import__(module_path, fromlist=[function_name])
        except ImportError as import_err:
            # 尝试更详细的错误信息
            logger.error(f"导入模块失败: {function_path}, 模块路径: {module_path}, 错误: {import_err}")
            return None

        # 获取函数
        if hasattr(module, function_name):
            func = getattr(module, function_name)
            if callable(func):
                logger.info(f"成功加载函数: {function_path}")
                return func
            else:
                logger.error(f"'{function_path}' 不是可调用对象，类型: {type(func)}")
                return None
        else:
            # 列出模块中可用的属性，帮助调试
            available_attrs = [attr for attr in dir(module) if not attr.startswith('_')]
            logger.error(
                f"模块 '{module_path}' 中不存在函数 '{function_name}'。"
                f"可用属性: {', '.join(available_attrs[:20])}"  # 只显示前20个
            )
            return None

    except ImportError as e:
        logger.error(f"导入模块失败: {function_path}, 错误: {e}", exc_info=True)
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
        # 如果无法找到函数，记录警告信息（但不抛出异常，避免影响任务列表显示）
        if function_path:
            logger.warning(
                f"无法找到任务 '{task_name}' 的函数（function_path: {function_path}）。"
                f"请检查：1. 函数路径是否正确 2. 函数是否已正确导入 3. 任务是否已注册"
            )
        else:
            logger.warning(
                f"无法找到任务 '{task_name}' 的函数（未提供 function_path，且注册表中不存在）。"
                f"请检查：1. 任务是否已注册 2. 任务名称是否正确"
            )
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
    """
    自动注册所有任务函数
    从 task_config.py 统一配置文件读取所有任务配置并自动注册
    """
    
    registered_count = 0
    failed_count = 0
    
    for config_key, config in TASK_CONFIGS.items():
        try:
            task_name = config["task_name"]
            task_module = config["task_module"]
            task_function = config["task_function"]
            wrapper = config.get("wrapper", False)
            
            # ====== 安全验证：验证模块路径 ======
            if not _validate_module_path(task_module):
                logger.error(
                    f"任务模块路径验证失败: '{task_module}' (任务: '{task_name}') - 安全策略拒绝"
                )
                failed_count += 1
                continue

            # 验证函数名格式
            if not re.match(r'^[a-zA-Z0-9_]+$', task_function):
                logger.error(
                    f"任务函数名格式无效: '{task_function}' (任务: '{task_name}') - 只允许字母、数字、下划线"
                )
                failed_count += 1
                continue

            # 动态导入任务模块和函数（已通过安全验证）
            try:
                module = __import__(task_module, fromlist=[task_function])
            except ImportError as import_err:
                logger.error(
                    f"无法导入任务模块 '{task_module}' (任务: '{task_name}'): {import_err}",
                    exc_info=True
                )
                failed_count += 1
                continue
                
            if not hasattr(module, task_function):
                # 列出模块中可用的属性，帮助调试
                available_attrs = [attr for attr in dir(module) if not attr.startswith('_')]
                logger.error(
                    f"任务模块 '{task_module}' 中不存在函数 '{task_function}' (任务: '{task_name}')。"
                    f"可用属性: {', '.join(available_attrs[:20])}"
                )
                failed_count += 1
                continue
                
            task_func = getattr(module, task_function)
            if not callable(task_func):
                logger.error(
                    f"任务模块 '{task_module}' 中的 '{task_function}' 不是可调用对象 (任务: '{task_name}')，类型: {type(task_func)}"
                )
                failed_count += 1
                continue
            
            # 特殊处理：清理旧日志任务需要包装函数
            if wrapper and task_name == "清理旧日志":
                # 创建包装函数，使用配置中的参数（使用默认参数避免闭包问题）
                async def cleanup_old_logs_wrapper(func=task_func, days=settings.AUDIT_LOG_RETENTION_DAYS, archive=settings.AUDIT_LOG_ARCHIVE):
                    """清理旧日志任务的包装函数，使用配置中的参数"""
                    return await func(days=days, archive=archive)
                register_task_function(task_name, cleanup_old_logs_wrapper)
            else:
                register_task_function(task_name, task_func)
            
            registered_count += 1
            logger.debug(f"已注册任务: {task_name}")
            
        except KeyError as e:
            logger.error(f"任务配置 '{config_key}' 缺少必要字段: {e}")
            failed_count += 1
        except Exception as e:
            logger.error(f"注册任务 '{config_key}' 失败: {e}", exc_info=True)
            failed_count += 1
    
=======
"""
任务注册表
将数据库中的任务名称映射到实际的任务函数
"""
import re
from typing import Dict, Callable, Optional, Any
import logging

from app.scheduler_module.task_config import TASK_CONFIGS
from app.core.config import settings

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


def load_function_by_path(function_path: str) -> Optional[Callable[..., Any]]:
    """
    根据函数路径动态加载函数
    
    安全特性：
    - 只允许导入 app. 开头的模块（应用内部模块）
    - 验证模块路径格式，防止代码注入
    - 禁止相对导入
    
    Args:
        function_path: 函数完整路径，格式：module.path.function_name
                     例如：app.scheduler_module.tasks.simple_task.simple_info_task
        
    Returns:
        函数对象，如果加载失败返回 None
    """
    if not function_path:
        logger.error("函数路径为空")
        return None
        
    try:
        # 分割模块路径和函数名
        parts = function_path.rsplit('.', 1)
        if len(parts) != 2:
            logger.error(f"函数路径格式错误: {function_path}，应为 'module.path.function_name'")
            return None

        module_path, function_name = parts

        # ====== 安全验证：验证模块路径 ======
        if not _validate_module_path(module_path):
            logger.error(f"模块路径验证失败: {module_path}（安全策略拒绝）")
            return None

        # 验证函数名格式（只允许字母、数字、下划线）
        if not re.match(r'^[a-zA-Z0-9_]+$', function_name):
            logger.error(f"函数名格式无效: {function_name}（只允许字母、数字、下划线）")
            return None

        # 动态导入模块（已通过安全验证）
        try:
            module = __import__(module_path, fromlist=[function_name])
        except ImportError as import_err:
            # 尝试更详细的错误信息
            logger.error(f"导入模块失败: {function_path}, 模块路径: {module_path}, 错误: {import_err}")
            return None

        # 获取函数
        if hasattr(module, function_name):
            func = getattr(module, function_name)
            if callable(func):
                logger.info(f"成功加载函数: {function_path}")
                return func
            else:
                logger.error(f"'{function_path}' 不是可调用对象，类型: {type(func)}")
                return None
        else:
            # 列出模块中可用的属性，帮助调试
            available_attrs = [attr for attr in dir(module) if not attr.startswith('_')]
            logger.error(
                f"模块 '{module_path}' 中不存在函数 '{function_name}'。"
                f"可用属性: {', '.join(available_attrs[:20])}"  # 只显示前20个
            )
            return None

    except ImportError as e:
        logger.error(f"导入模块失败: {function_path}, 错误: {e}", exc_info=True)
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
        # 如果无法找到函数，记录警告信息（但不抛出异常，避免影响任务列表显示）
        if function_path:
            logger.warning(
                f"无法找到任务 '{task_name}' 的函数（function_path: {function_path}）。"
                f"请检查：1. 函数路径是否正确 2. 函数是否已正确导入 3. 任务是否已注册"
            )
        else:
            logger.warning(
                f"无法找到任务 '{task_name}' 的函数（未提供 function_path，且注册表中不存在）。"
                f"请检查：1. 任务是否已注册 2. 任务名称是否正确"
            )
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
    """
    自动注册所有任务函数
    从 task_config.py 统一配置文件读取所有任务配置并自动注册
    """
    
    registered_count = 0
    failed_count = 0
    
    for config_key, config in TASK_CONFIGS.items():
        try:
            task_name = config["task_name"]
            task_module = config["task_module"]
            task_function = config["task_function"]
            wrapper = config.get("wrapper", False)
            
            # ====== 安全验证：验证模块路径 ======
            if not _validate_module_path(task_module):
                logger.error(
                    f"任务模块路径验证失败: '{task_module}' (任务: '{task_name}') - 安全策略拒绝"
                )
                failed_count += 1
                continue

            # 验证函数名格式
            if not re.match(r'^[a-zA-Z0-9_]+$', task_function):
                logger.error(
                    f"任务函数名格式无效: '{task_function}' (任务: '{task_name}') - 只允许字母、数字、下划线"
                )
                failed_count += 1
                continue

            # 动态导入任务模块和函数（已通过安全验证）
            try:
                module = __import__(task_module, fromlist=[task_function])
            except ImportError as import_err:
                logger.error(
                    f"无法导入任务模块 '{task_module}' (任务: '{task_name}'): {import_err}",
                    exc_info=True
                )
                failed_count += 1
                continue
                
            if not hasattr(module, task_function):
                # 列出模块中可用的属性，帮助调试
                available_attrs = [attr for attr in dir(module) if not attr.startswith('_')]
                logger.error(
                    f"任务模块 '{task_module}' 中不存在函数 '{task_function}' (任务: '{task_name}')。"
                    f"可用属性: {', '.join(available_attrs[:20])}"
                )
                failed_count += 1
                continue
                
            task_func = getattr(module, task_function)
            if not callable(task_func):
                logger.error(
                    f"任务模块 '{task_module}' 中的 '{task_function}' 不是可调用对象 (任务: '{task_name}')，类型: {type(task_func)}"
                )
                failed_count += 1
                continue
            
            # 特殊处理：清理旧日志任务需要包装函数
            if wrapper and task_name == "清理旧日志":
                # 创建包装函数，使用配置中的参数（使用默认参数避免闭包问题）
                async def cleanup_old_logs_wrapper(func=task_func, days=settings.AUDIT_LOG_RETENTION_DAYS, archive=settings.AUDIT_LOG_ARCHIVE):
                    """清理旧日志任务的包装函数，使用配置中的参数"""
                    return await func(days=days, archive=archive)
                register_task_function(task_name, cleanup_old_logs_wrapper)
            else:
                register_task_function(task_name, task_func)
            
            registered_count += 1
            logger.debug(f"已注册任务: {task_name}")
            
        except KeyError as e:
            logger.error(f"任务配置 '{config_key}' 缺少必要字段: {e}")
            failed_count += 1
        except Exception as e:
            logger.error(f"注册任务 '{config_key}' 失败: {e}", exc_info=True)
            failed_count += 1
    
>>>>>>> 451fe37690182f08f5b8c5e7c77a028275228449
    logger.info(f"任务注册完成: 成功 {registered_count} 个, 失败 {failed_count} 个")