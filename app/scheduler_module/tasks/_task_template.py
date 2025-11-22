"""
定时任务模板
复制此文件并修改以创建新的定时任务

使用说明：
1. 在 task_names.py 中定义任务名称常量
2. 复制此文件，重命名为你的任务名称（如：my_new_task.py）
3. 修改任务函数名称和逻辑
4. 在 task_registry.py 中注册任务函数
5. 在 task_result_registry.py 中注册结果获取函数
6. 在数据库中创建对应的 scheduled_tasks 记录

最佳实践：
- 使用任务名称常量，不要硬编码字符串
- 使用 task_utils 中的工具函数，减少重复代码
- 使用 format_result_summary() 格式化结果摘要
"""
import logging
from app.scheduler_module.task_names import MY_NEW_TASK_NAME  # 在 task_names.py 中定义
from app.scheduler_module.task_utils import (
    log_task_start,
    log_task_result,
    log_task_error,
    format_result_summary,
)

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)

# 任务执行结果存储（用于保存到last_error字段）
# key: 任务名称, value: 执行结果信息
_task_results: dict[str, str] = {}


def get_task_result(task_name: str) -> str | None:
    """获取任务执行结果"""
    return _task_results.get(task_name)


def set_task_result(task_name: str, result: str) -> None:
    """设置任务执行结果"""
    _task_results[task_name] = result

# 注意：get_task_result 和 set_task_result 已从 task_utils 导入
# 如果任务模块需要独立的结果存储，可以取消下面的注释
# _task_results: dict[str, str] = {}
# 
# def get_task_result(task_name: str) -> str | None:
#     """获取任务执行结果"""
#     return _task_results.get(task_name)
# 
# def set_task_result(task_name: str, result: str) -> None:
#     """设置任务执行结果"""
#     _task_results[task_name] = result


async def my_new_task() -> None:
    """
    新定时任务主函数
    
    功能说明：
    在这里描述你的任务功能
    
    注意：
    - 这是异步函数，可以直接使用await
    - 所有数据库操作都在事务中执行，确保数据一致性
    - 使用 set_task_result() 保存执行结果，结果会显示在"最后错误"栏
    - 使用工具函数简化日志记录和结果格式化
    """
    # 记录任务开始执行的日志（使用工具函数）
    log_task_start(MY_NEW_TASK_NAME)

    try:
        # ============================================
        # 任务主逻辑开始
        # ============================================
        
        # 在这里编写你的任务逻辑
        # 例如：调用API、处理数据、清理文件等
        
        # 示例：模拟任务执行
        success_count = 0
        error_count = 0
        
        # 你的业务逻辑...
        # result = await some_operation()
        # if result:
        #     success_count += 1
        # else:
        #     error_count += 1
        
        # ============================================
        # 任务主逻辑结束
        # ============================================
        
        # 格式化任务执行结果（使用工具函数）
        result_summary = format_result_summary(
            success=success_count,
            error=error_count,
            # 如果有其他统计项，可以继续添加
            # processed=total_count,
            # inserted=inserted_count,
        )
        
        # 记录任务执行结果（使用工具函数）
        log_task_result(MY_NEW_TASK_NAME, result_summary, level="warning")
        
        # 保存执行结果到全局存储（用于保存到last_error字段）
        # 注意：使用任务名称常量，确保与数据库中的 task_name 一致
        set_task_result(MY_NEW_TASK_NAME, f"执行成功: {result_summary}")
        
    except Exception as e:
        # ========== 全局错误处理 ==========
        # 使用工具函数记录错误
        log_task_error(MY_NEW_TASK_NAME, str(e), exc_info=True)
        
        # 重新抛出异常，让定时任务调度器能够记录错误状态
        raise

