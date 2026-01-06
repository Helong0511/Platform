"""
定时任务管理API端点
提供定时任务的查看和管理功能，包括：
- 获取定时任务列表
- 获取定时任务详情
- 创建新的定时任务
- 编辑定时任务（支持完整编辑，包括任务名称、Cron表达式、描述、函数路径等）
- 启用/禁用定时任务
- 手动触发定时任务
- 重新加载任务配置
- 释放任务锁
- 仅管理员可访问
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, Path, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func
from typing import Optional
import logging
import asyncio
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.security import require_admin
from app.core.validation import validate_cron_expression, sanitize_input
from app.core.audit_log import log_create, log_update, log_delete, log_activate, log_deactivate
from app.core.exceptions import raise_api_exception
from app.core.errors import ErrorCode
from app.models.models import User, ScheduledTask
from app.core.utils import get_app_now_naive
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.scheduler_module.task_registry import get_task_function_info
from pydantic import BaseModel, field_validator, Field

# 创建路由实例
router = APIRouter()
# 获取日志记录器
logger = logging.getLogger(__name__)

# 常量
from app.core.constants import MAX_TASK_NAME_LENGTH, QUERY_TIMEOUT, MAX_PAGE_SIZE
MAX_DESCRIPTION_LENGTH = 500
MAX_FUNCTION_PATH_LENGTH = 255

# ====== Schema 定义 ======
from app.schemas.base import BaseSchema


class ScheduledTaskResponse(BaseSchema):
    """定时任务响应模型"""
    id: int
    task_name: str
    last_run_time: Optional[datetime] = None
    is_running: bool
    last_run_pid: Optional[int] = None
    last_run_host: Optional[str] = None
    run_count: int
    success_count: int
    error_count: int
    last_error: Optional[str] = None
    is_active: bool
    cron_expression: Optional[str] = None
    description: Optional[str] = None
    function_name: Optional[str] = None  # 执行函数名称
    function_module: Optional[str] = None  # 函数所在模块路径
    function_path: Optional[str] = None  # 执行函数路径（数据库字段）
    created_at: datetime
    updated_at: datetime


class ScheduledTaskUpdate(BaseModel):
    """定时任务更新模型（仅支持启用/禁用）"""
    is_active: bool


# ====== API 端点 ======
@router.get(
    "/",
    response_model=PaginatedResponseBaseSchema[list[ScheduledTaskResponse]],
    summary="获取定时任务列表"
)
async def get_scheduled_tasks(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
        is_active: Optional[bool] = Query(None, description="是否启用过滤"),
        is_running: Optional[bool] = Query(None, description="是否运行中过滤"),
        task_name: Optional[str] = Query(None, description="任务名称搜索", max_length=MAX_TASK_NAME_LENGTH)
):
    """
    获取定时任务列表（已重构使用服务层）
    - 仅管理员可访问
    - 支持分页和过滤
    """
    # 使用服务层（业务逻辑在ScheduledTaskService中）
    from app.core.dependencies import get_scheduled_task_service
    from app.services.scheduled_task_service import ScheduledTaskService
    
    task_service: ScheduledTaskService = await get_scheduled_task_service(db)
    
    try:
        # 调用服务层获取定时任务列表（服务层会处理查询、过滤、分页、超时保护等）
        tasks, total = await task_service.get_scheduled_tasks(
            page=page,
            page_size=page_size,
            is_active=is_active,
            is_running=is_running,
            task_name=task_name
        )

        # 转换为响应模型，并添加函数信息
        task_list = []
        for task in tasks:
            try:
                task_dict = ScheduledTaskResponse.model_validate(task).model_dump()
                # 获取函数信息（优先使用 function_path）
                # 如果获取函数信息失败，不影响任务列表的返回
                try:
                    func_info = get_task_function_info(task.task_name, task.function_path)
                    if func_info:
                        task_dict["function_name"] = func_info["function_name"]
                        task_dict["function_module"] = func_info["function_module"]
                except Exception as func_err:
                    # 获取函数信息失败，记录警告但不影响任务列表
                    logger.warning(f"获取任务 {task.task_name} 的函数信息失败: {func_err}")
                task_list.append(ScheduledTaskResponse(**task_dict))
            except Exception as task_err:
                # 单个任务转换失败，记录错误但继续处理其他任务
                logger.error(f"转换任务 {task.task_name if hasattr(task, 'task_name') else '未知'} 失败: {task_err}", exc_info=True)
                # 尝试使用基本字段构建响应
                try:
                    task_dict = {
                        "id": task.id,
                        "task_name": task.task_name,
                        "last_run_time": task.last_run_time,
                        "is_running": task.is_running,
                        "last_run_pid": task.last_run_pid,
                        "last_run_host": task.last_run_host,
                        "run_count": task.run_count,
                        "success_count": task.success_count,
                        "error_count": task.error_count,
                        "last_error": task.last_error,
                        "is_active": task.is_active,
                        "cron_expression": task.cron_expression,
                        "description": task.description,
                        "function_path": task.function_path,
                        "created_at": task.created_at,
                        "updated_at": task.updated_at
                    }
                    task_list.append(ScheduledTaskResponse(**task_dict))
                except Exception:
                    # 如果基本字段也失败，跳过这个任务
                    logger.error(f"无法构建任务 {task.id} 的响应，跳过该任务")
                    continue

        return PaginatedResponseBaseSchema.success(
            data=task_list,
            total=total,
            page=page,
            page_size=page_size
        )

    except Exception as e:
        logger.error(f"获取定时任务列表失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取定时任务列表失败：{str(e)}"
        )


@router.get(
    "/{task_name}",
    response_model=ResponseBaseSchema[ScheduledTaskResponse],
    summary="获取定时任务详情"
)
async def get_scheduled_task(
        task_name: str = Path(..., description="任务名称", max_length=MAX_TASK_NAME_LENGTH),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取定时任务详情（已重构使用服务层）
    - 仅管理员可访问
    """
    # 使用服务层（业务逻辑在ScheduledTaskService中）
    from app.core.dependencies import get_scheduled_task_service
    from app.services.scheduled_task_service import ScheduledTaskService
    
    task_service: ScheduledTaskService = await get_scheduled_task_service(db)
    
    try:
        # 调用服务层获取定时任务详情（服务层会处理查询和验证）
        task = await task_service.get_scheduled_task_by_name(task_name)

        if not task:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="定时任务不存在"
            )

        # 转换为响应模型并添加函数信息
        task_dict = ScheduledTaskResponse.model_validate(task).model_dump()
        func_info = get_task_function_info(task.task_name, task.function_path)
        if func_info:
            task_dict["function_name"] = func_info["function_name"]
            task_dict["function_module"] = func_info["function_module"]

        return ResponseBaseSchema.success(data=ScheduledTaskResponse(**task_dict))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取定时任务详情失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取定时任务详情失败：{str(e)}"
        )


@router.patch(
    "/{task_name}",
    response_model=ResponseBaseSchema[ScheduledTaskResponse],
    summary="更新定时任务状态"
)
async def update_scheduled_task(
        request: Request,
        task_name: str = Path(..., description="任务名称", max_length=MAX_TASK_NAME_LENGTH),
        task_update: ScheduledTaskUpdate = Body(...),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    更新定时任务状态（已重构使用服务层）
    - 仅管理员可访问
    - 仅支持启用/禁用定时任务
    """
    # 使用服务层（业务逻辑在ScheduledTaskService中）
    from app.core.dependencies import get_scheduled_task_service
    from app.services.scheduled_task_service import ScheduledTaskService
    
    task_service: ScheduledTaskService = await get_scheduled_task_service(db)
    
    try:
        # 调用服务层更新定时任务状态（服务层会处理验证、更新、调度器注册等）
        task = await task_service.update_scheduled_task_status(
            task_name=task_name,
            is_active=task_update.is_active,
            current_user=current_user
        )

        # 记录激活/禁用日志
        old_is_active = task.is_active != task_update.is_active  # 检查状态是否改变
        if old_is_active:
            try:
                if task.is_active:
                    await log_activate(
                        db=db,
                        user=current_user,
                        resource_type="SCHEDULED_TASK",
                        resource_id=task.id,
                        resource_name=task.task_name,
                        request=request
                    )
                else:
                    await log_deactivate(
                        db=db,
                        user=current_user,
                        resource_type="SCHEDULED_TASK",
                        resource_id=task.id,
                        resource_name=task.task_name,
                        request=request
                    )
            except Exception as log_error:
                # 日志记录失败不应该影响主操作
                logger.warning(f"记录激活/禁用日志失败: {log_error}", exc_info=True)

        # 转换为响应模型并添加函数信息
        try:
            task_dict = ScheduledTaskResponse.model_validate(task).model_dump()
            func_info = get_task_function_info(task.task_name, task.function_path)
            if func_info:
                task_dict["function_name"] = func_info["function_name"]
                task_dict["function_module"] = func_info["function_module"]
        except Exception as dict_error:
            # 如果转换失败，使用基本字段构建响应
            logger.warning(f"转换任务响应模型失败: {dict_error}，使用基本字段", exc_info=True)
            task_dict = {
                "id": task.id,
                "task_name": task.task_name,
                "cron_expression": task.cron_expression,
                "description": task.description,
                "function_path": task.function_path,
                "is_active": task.is_active,
                "is_running": task.is_running,
                "last_run_time": task.last_run_time,
                "run_count": task.run_count,
                "success_count": task.success_count,
                "error_count": task.error_count,
                "last_error": task.last_error,
                "created_at": task.created_at,
                "updated_at": task.updated_at
            }

        return ResponseBaseSchema.success(data=ScheduledTaskResponse(**task_dict))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新定时任务失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"更新定时任务失败：{str(e)}"
        )


class TriggerTaskParams(BaseModel):
    """手动触发任务的参数"""
    start_date: Optional[str] = Field(None, description="起始日期 (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="结束日期 (YYYY-MM-DD)")

@router.post(
    "/{task_name}/trigger",
    response_model=ResponseBaseSchema[dict],
    summary="手动触发定时任务"
)
async def trigger_scheduled_task(
        request: Request,
        task_name: str = Path(..., description="任务名称", max_length=MAX_TASK_NAME_LENGTH),
        params: Optional[TriggerTaskParams] = Body(None, description="任务参数"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    手动触发定时任务（已重构使用服务层）
    - 仅管理员可访问
    - 立即执行指定的定时任务
    """
    # 使用服务层（业务逻辑在ScheduledTaskService中）
    from app.core.dependencies import get_scheduled_task_service
    from app.services.scheduled_task_service import ScheduledTaskService
    
    task_service: ScheduledTaskService = await get_scheduled_task_service(db)
    
    try:
        # 准备任务参数
        task_params = None
        if params:
            task_params = params.model_dump(exclude_unset=True)

        # 调用服务层手动触发定时任务（服务层会处理验证、注册、触发等）
        result = await task_service.trigger_scheduled_task(
            task_name=task_name,
            params=task_params,
            current_user=current_user
        )

        return ResponseBaseSchema.success(data=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"触发定时任务失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"触发定时任务失败：{str(e)}"
        )


@router.post(
    "/{task_name}/reload",
    response_model=ResponseBaseSchema[dict],
    summary="重新加载任务（从数据库重新读取配置）"
)
async def reload_scheduled_task(
        task_name: str = Path(..., description="任务名称", max_length=MAX_TASK_NAME_LENGTH),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    重新加载定时任务配置（已重构使用服务层）
    - 从数据库重新读取任务配置并更新到调度器
    - 适用于直接在数据库中修改了 cron_expression 或 is_active 的情况
    - 仅管理员可访问
    """
    # 使用服务层（业务逻辑在ScheduledTaskService中）
    from app.core.dependencies import get_scheduled_task_service
    from app.services.scheduled_task_service import ScheduledTaskService
    
    task_service: ScheduledTaskService = await get_scheduled_task_service(db)
    
    try:
        # 调用服务层重新加载定时任务（服务层会处理验证、注册等）
        result = await task_service.reload_scheduled_task(
            task_name=task_name,
            current_user=current_user
        )

        return ResponseBaseSchema.success(data=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新加载定时任务失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"重新加载定时任务失败：{str(e)}"
        )


@router.post(
    "/reload-all",
    response_model=ResponseBaseSchema[dict],
    summary="重新加载所有任务（从数据库重新读取所有任务配置）"
)
async def reload_all_scheduled_tasks(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    重新加载所有定时任务配置（已重构使用服务层）
    - 从数据库重新读取所有任务配置并更新到调度器
    - 适用于直接在数据库中修改了任务配置的情况
    - 仅管理员可访问
    """
    # 使用服务层（业务逻辑在ScheduledTaskService中）
    from app.core.dependencies import get_scheduled_task_service
    from app.services.scheduled_task_service import ScheduledTaskService
    
    task_service: ScheduledTaskService = await get_scheduled_task_service(db)
    
    try:
        # 调用服务层重新加载所有定时任务（服务层会处理初始化）
        result = await task_service.reload_all_scheduled_tasks(current_user)

        return ResponseBaseSchema.success(data=result)

    except Exception as e:
        logger.error(f"重新加载所有定时任务失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"重新加载所有定时任务失败：{str(e)}"
        )


@router.get(
    "/queue-status",
    response_model=ResponseBaseSchema[dict],
    summary="获取任务队列状态",
    dependencies=[Depends(require_admin)]
)
async def get_task_queue_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    获取任务执行队列的当前状态（已重构使用服务层）
    
    返回信息包括：
    - current_running: 当前正在执行的任务数
    - max_concurrent: 最大并发任务数
    - queue_length: 队列中等待的任务数
    - running_tasks: 正在执行的任务名称列表
    - queued_tasks: 队列中等待的任务名称列表
    - queue_details: 队列详细信息（包含优先级和等待时间）
    
    仅管理员可访问
    """
    # 使用服务层（业务逻辑在ScheduledTaskService中）
    from app.core.dependencies import get_scheduled_task_service
    from app.services.scheduled_task_service import ScheduledTaskService
    
    task_service: ScheduledTaskService = await get_scheduled_task_service(db)
    
    try:
        # 调用服务层获取任务队列状态（服务层会处理查询）
        status = await task_service.get_task_queue_status()
        
        return ResponseBaseSchema(
            success=True,
            message="获取队列状态成功",
            data=status
        )
    except Exception as e:
        logger.error(f"获取任务队列状态失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取任务队列状态失败：{str(e)}"
        )


@router.get(
    "/scheduler-status",
    response_model=ResponseBaseSchema[dict],
    summary="获取调度器状态（诊断用）"
)
async def get_scheduler_status(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    获取调度器的详细状态信息，用于诊断定时任务是否正常运行（已重构使用服务层）
    - 仅管理员可访问
    - 显示调度器运行状态、已注册任务列表、下次执行时间等
    """
    # 使用服务层（业务逻辑在ScheduledTaskService中）
    from app.core.dependencies import get_scheduled_task_service
    from app.services.scheduled_task_service import ScheduledTaskService
    
    task_service: ScheduledTaskService = await get_scheduled_task_service(db)
    
    try:
        # 调用服务层获取调度器状态（服务层会处理查询）
        status_data = await task_service.get_scheduler_status()
        
        return ResponseBaseSchema.success(data=status_data)
    except Exception as e:
        logger.error(f"获取调度器状态失败: {e}", exc_info=True)
        raise_api_exception(
            ErrorCode.OPERATION_FAILED,
            detail=f"获取调度器状态失败：{str(e)}"
        )


@router.post(
    "/{task_name}/release-lock",
    response_model=ResponseBaseSchema[dict],
    summary="释放任务锁（紧急操作）"
)
async def release_task_lock(
        task_name: str = Path(..., description="任务名称", max_length=MAX_TASK_NAME_LENGTH),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_admin)
):
    """
    释放任务锁（紧急操作，已重构使用服务层）
    - 仅管理员可访问
    - 用于任务异常中断导致锁未释放的情况
    - 使用数据库锁确保原子性操作
    """
    # 使用服务层（业务逻辑在ScheduledTaskService中）
    from app.core.dependencies import get_scheduled_task_service
    from app.services.scheduled_task_service import ScheduledTaskService
    
    task_service: ScheduledTaskService = await get_scheduled_task_service(db)
    
    try:
        # 调用服务层释放任务锁（服务层会处理验证、释放等）
        result = await task_service.release_task_lock(
            task_name=task_name,
            current_user=current_user
        )

        return ResponseBaseSchema.success(data=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"释放任务锁失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="释放任务锁失败"
        )
