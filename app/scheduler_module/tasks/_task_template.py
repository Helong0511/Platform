"""
定时任务模板
复制此文件并修改以创建新的定时任务

==========================================
使用说明（新版本 - 简化流程）：
==========================================

1. 复制此文件，重命名为你的任务名称（如：my_new_task.py）
2. 修改任务函数名称和逻辑
3. 在 task_config.py 中添加一行配置即可（无需修改其他文件）
4. 在数据库中创建对应的 scheduled_tasks 记录

==========================================
详细步骤：
==========================================

步骤 1：创建任务文件
- 复制此文件到 app/scheduler_module/tasks/my_new_task.py
- 修改任务函数名称（如：my_new_task）
- 实现任务逻辑

步骤 2：在 task_config.py 中添加配置
打开 app/scheduler_module/task_config.py，添加：

    "我的新任务": {
        "task_name": "我的新任务",
        "task_module": "app.scheduler_module.tasks.my_new_task",
        "task_function": "my_new_task",
        "result_getter_module": "app.scheduler_module.tasks.my_new_task",
        "result_getter_function": "get_task_result",
    },

步骤 3：完成！
系统会自动：
- 注册任务函数
- 注册结果获取函数
- 无需修改 task_registry.py 和 task_result_registry.py

==========================================
最佳实践：
==========================================

- 使用 set_task_result() 保存执行结果，结果会显示在"最后错误"栏
- 使用 try-except 捕获异常，确保错误信息被正确记录
- 在任务执行的关键步骤记录日志，便于排查问题
- 任务名称要与数据库中的 task_name 保持一致
"""
import logging
from datetime import datetime
from app.core.config import settings

# 注意：任务名称可以直接使用字符串，或从 task_names.py 导入常量
# 如果使用常量，需要在 task_names.py 中定义
# from app.scheduler_module.task_names import MY_NEW_TASK_NAME
MY_NEW_TASK_NAME = "我的新任务"  # 与 task_config.py 和数据库中的 task_name 保持一致

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
    - 任务名称要与 task_config.py 和数据库中的 task_name 保持一致
    """
    # 获取应用配置时区的当前时间（用于日志记录）
    from app.core.utils import get_app_now
    app_time = get_app_now()
    current_time_str = app_time.strftime("%Y-%m-%d %H:%M:%S")
    
    # 记录任务开始执行的日志
    logger.info(f"{MY_NEW_TASK_NAME} 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")
    logger.warning(f"[{MY_NEW_TASK_NAME}] 开始执行 - {current_time_str}（时区: {settings.TIMEZONE}）")
    
    try:
        # ============================================
        # 任务主逻辑开始
        # ============================================
        
        # 在这里编写你的任务逻辑
        # 例如：调用API、处理数据、清理文件等
        
        # 示例：模拟任务执行
        success_count = 0
        error_count = 0
        processed_count = 0
        
        # 你的业务逻辑...
        # result = await some_operation()
        # if result:
        #     success_count += 1
        # else:
        #     error_count += 1
        # processed_count += 1
        
        # ============================================
        # 任务主逻辑结束
        # ============================================
        
        # 格式化任务执行结果
        result_summary = (
            f"成功 {success_count} 条, "
            f"处理 {processed_count} 条, "
            f"错误 {error_count} 条"
        )
        
        # 记录任务执行结果
        logger.info(f"任务执行完成: {result_summary}")
        logger.warning(f"[定时任务执行] {result_summary}")
        
        # 保存执行结果到全局存储（用于保存到last_error字段）
        # 注意：使用任务名称，确保与 task_config.py 和数据库中的 task_name 一致
        set_task_result(MY_NEW_TASK_NAME, f"执行成功: {result_summary}")
        
    except Exception as e:
        # ========== 全局错误处理 ==========
        
        error_msg = f"{MY_NEW_TASK_NAME} 执行失败: {str(e)}"
        # 记录详细错误信息（包括完整的堆栈跟踪）
        logger.error(error_msg, exc_info=True)
        # 同时使用 logger.warning 确保即使日志级别设置为 WARNING 也能看到错误信息
        logger.warning(f"[{MY_NEW_TASK_NAME}] {error_msg}")
        
        # 保存错误结果到全局存储
        set_task_result(MY_NEW_TASK_NAME, error_msg)
        
        # 重新抛出异常，让定时任务调度器能够记录错误状态
        # 这样可以在数据库中标记任务执行失败，便于后续排查问题
        raise

