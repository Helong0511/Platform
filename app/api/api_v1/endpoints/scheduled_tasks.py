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
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
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
from app.models.models import User, ScheduledTask
from app.core.utils import get_app_now_naive
from app.schemas.base import ResponseBaseSchema, PaginatedResponseBaseSchema
from app.scheduler_module.task_registry import get_task_function_info
from pydantic import BaseModel, field_validator, Field
from fastapi import Request

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
    获取定时任务列表
    - 仅管理员可访问
    - 支持分页和过滤
    """
    try:
        # 构建查询条件
        conditions = []
        if is_active is not None:
            conditions.append(ScheduledTask.is_active == is_active)
        if is_running is not None:
            conditions.append(ScheduledTask.is_running == is_running)
        # 构建查询
        query = select(ScheduledTask)
        
        # 任务名称搜索（优先使用全文搜索，回退到LIKE）
        if task_name:
            cleaned_task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
            if cleaned_task_name:
                from app.core.fulltext_search import search_with_fulltext
                query = await search_with_fulltext(
                    db=db,
                    model_class=ScheduledTask,
                    search_fields=["task_name", "description"],
                    search_term=cleaned_task_name,
                    base_query=query,
                    use_fulltext=True
                )
        
        # 其他过滤条件
        if conditions:
            query = query.where(and_(*conditions))

        # 排序：按ID降序（最新的任务ID最大）
        query = query.order_by(ScheduledTask.id.asc())

        # 获取总数
        count_query = select(func.count()).select_from(ScheduledTask)
        
        # 任务名称搜索（优先使用全文搜索，回退到LIKE）
        if task_name:
            cleaned_task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
            if cleaned_task_name:
                from app.core.fulltext_search import search_with_fulltext
                count_query = await search_with_fulltext(
                    db=db,
                    model_class=ScheduledTask,
                    search_fields=["task_name", "description"],
                    search_term=cleaned_task_name,
                    base_query=count_query,
                    use_fulltext=True
                )
        
        # 其他过滤条件
        if conditions:
            count_query = count_query.where(and_(*conditions))
        
        # 获取总数（添加超时保护）
        try:
            total_result = await asyncio.wait_for(
                db.execute(count_query),
                timeout=QUERY_TIMEOUT
            )
            total = total_result.scalar() or 0
        except asyncio.TimeoutError:
            logger.error("获取定时任务总数查询超时（30秒）")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="查询超时，请稍后重试"
            )

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # 执行查询（添加超时保护，避免长时间阻塞）
        try:
            result = await asyncio.wait_for(
                db.execute(query),
                timeout=QUERY_TIMEOUT
            )
            tasks = result.scalars().all()
        except asyncio.TimeoutError:
            logger.error("获取定时任务列表查询超时（30秒）")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="查询超时，请稍后重试"
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取定时任务列表失败"
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
    获取定时任务详情
    - 仅管理员可访问
    """
    try:
        # URL 解码（FastAPI 应该自动解码，但为了安全起见手动处理一次）
        from urllib.parse import unquote
        task_name = unquote(task_name)

        # 清理输入
        task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
        if not task_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="任务名称无效"
            )

        result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.task_name == task_name)
        )
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取定时任务详情失败"
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
    更新定时任务状态
    - 仅管理员可访问
    - 仅支持启用/禁用定时任务
    """
    try:
        # URL 解码（FastAPI 应该自动解码，但为了安全起见手动处理一次）
        from urllib.parse import unquote
        task_name = unquote(task_name)

        # 清理输入
        task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
        if not task_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="任务名称无效"
            )

        # 使用数据库锁获取任务记录（防止并发更新冲突）
        result = await db.execute(
            select(ScheduledTask)
            .where(ScheduledTask.task_name == task_name)
            .with_for_update(of=ScheduledTask)
        )
        task = result.scalar_one_or_none()

        if not task:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="定时任务不存在"
            )

        # 记录更新前的状态，用于判断是否需要重新注册任务
        old_is_active = task.is_active
        is_active_changed = (old_is_active != task_update.is_active)

        # 更新状态
        task.is_active = task_update.is_active
        task.updated_at = get_app_now_naive()

        await db.commit()
        await db.refresh(task)

        # 如果启用状态发生变化，需要重新注册任务或从调度器中移除
        if is_active_changed:
            from app.scheduler_module import get_scheduler
            from app.scheduler_module.task_registry import get_task_function_by_name_or_path
            from app.scheduler_module.scheduler import register_scheduled_task

            sched = get_scheduler()

            # 如果任务被禁用，从调度器中移除
            if not task.is_active:
                if sched.get_job(task.task_name):
                    sched.remove_job(task.task_name)
                    logger.info(f"任务 '{task.task_name}' 已禁用，已从调度器中移除")
            else:
                # 如果任务被启用，重新注册
                task_func = get_task_function_by_name_or_path(task.task_name, task.function_path)

                if task_func is None:
                    logger.warning(
                        f"任务 '{task.task_name}' 已启用，但未找到对应的任务函数 "
                        f"(function_path: {task.function_path})，无法注册到调度器"
                    )
                elif not task.cron_expression:
                    logger.warning(
                        f"任务 '{task.task_name}' 已启用，但没有设置 cron_expression，无法注册到调度器"
                    )
                else:
                    try:
                        register_scheduled_task(
                            task_name=task.task_name,
                            task_func=task_func,
                            cron_expression=task.cron_expression,
                            description=task.description or f"自动注册的任务: {task.task_name}"
                        )
                        logger.info(
                            f"任务 '{task.task_name}' 已重新注册到调度器 "
                            f"(Cron: {task.cron_expression}, 函数路径: {task.function_path or '注册表'}, 启用: {task.is_active})"
                        )
                    except Exception as e:
                        logger.error(
                            f"重新注册任务 '{task.task_name}' 失败: {e}",
                            exc_info=True
                        )

        logger.info(f"管理员 {current_user.username} 更新了定时任务状态: {task_name} (Active: {task.is_active})")

        # 在 commit 后，重新查询任务以确保对象是最新的
        await db.refresh(task)
        
        # 记录激活/禁用日志
        if is_active_changed:
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
        await db.rollback()
        logger.error(f"更新定时任务失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新定时任务失败"
        )


from pydantic import BaseModel, Field
from typing import Optional

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
    手动触发定时任务
    - 仅管理员可访问
    - 立即执行指定的定时任务
    """
    try:
        # URL 解码（FastAPI 应该自动解码，但为了安全起见手动处理一次）
        from urllib.parse import unquote
        task_name = unquote(task_name)

        # 清理输入
        task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
        if not task_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="任务名称无效"
            )

        # 检查任务是否存在
        result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.task_name == task_name)
        )
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="定时任务不存在"
            )

        if not task.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="定时任务未启用，无法触发"
            )

        # 导入调度器并触发任务
        from app.scheduler_module import get_scheduler
        from app.scheduler_module.task_registry import get_task_function_by_name_or_path
        from app.scheduler_module.scheduler import register_scheduled_task

        sched = get_scheduler()

        # 查找任务
        job = sched.get_job(task_name)
        if not job:
            # 任务未在调度器中注册，尝试自动重新注册
            logger.warning(f"任务 '{task_name}' 未在调度器中注册，尝试自动重新注册...")

            # 获取任务函数
            task_func = get_task_function_by_name_or_path(task_name, task.function_path)
            if task_func is None:
                available_jobs = [job.id for job in sched.get_jobs()]
                error_msg = (
                    f"任务 '{task_name}' 未在调度器中注册，且无法找到对应的任务函数。"
                    f"请检查 function_path: {task.function_path}"
                )
                if available_jobs:
                    error_msg += f" 已注册的任务: {', '.join(available_jobs)}"
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg
                )

            # 检查是否有 cron_expression
            if not task.cron_expression:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"任务 '{task_name}' 没有设置 cron_expression，无法注册到调度器"
                )

            # 尝试重新注册任务
            try:
                register_scheduled_task(
                    task_name=task_name,
                    task_func=task_func,
                    cron_expression=task.cron_expression,
                    description=task.description or f"自动注册的任务: {task_name}"
                )
                logger.info(f"任务 '{task_name}' 已自动重新注册到调度器")
                # 重新获取任务
                job = sched.get_job(task_name)
                if not job:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"任务 '{task_name}' 重新注册失败，请检查日志"
                    )
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"任务 '{task_name}' 重新注册失败（参数错误）: {str(e)}"
                )
            except Exception as e:
                logger.error(f"任务 '{task_name}' 重新注册失败: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"任务 '{task_name}' 重新注册失败: {str(e)}"
                )

        # 获取任务函数并手动执行
        # 手动触发时，应该跳过进程分配检查，直接执行
        from app.scheduler_module.task_registry import get_task_function_by_name_or_path
        from app.scheduler_module.scheduler import execute_task_with_lock
        import asyncio

        # 获取原始任务函数
        task_func = get_task_function_by_name_or_path(task_name, task.function_path)
        if task_func is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无法找到任务函数: {task.function_path}"
            )

        # 手动触发时，跳过进程分配检查（skip_process_check=True）
        async def trigger_task():
            try:
                logger.info(f"开始手动触发任务 '{task_name}'（跳过进程分配检查）")
                
                # 准备任务参数
                task_kwargs = {}
                if params:
                    if params.start_date:
                        task_kwargs['start_date'] = params.start_date
                    if params.end_date:
                        task_kwargs['end_date'] = params.end_date
                
                await execute_task_with_lock(
                    task_name=task_name,
                    task_func=task_func,
                    skip_process_check=True,
                    **task_kwargs  # 传递日期参数
                )
                logger.info(f"手动触发任务 '{task_name}' 已提交到执行队列")
            except Exception as e:
                logger.error(f"手动触发任务执行失败: {e}", exc_info=True)
                raise
        
        # 异步触发任务（不等待完成）
        asyncio.create_task(trigger_task())

        logger.info(f"管理员 {current_user.username} 手动触发了定时任务: {task_name}")

        # 注意：TRIGGER 操作不在白名单中，不记录日志

        return ResponseBaseSchema.success(
            data={"message": "任务已触发，正在后台执行"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"触发定时任务失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"触发定时任务失败: {str(e)}"
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
    重新加载定时任务配置
    - 从数据库重新读取任务配置并更新到调度器
    - 适用于直接在数据库中修改了 cron_expression 或 is_active 的情况
    - 仅管理员可访问
    """
    try:
        # URL 解码（FastAPI 应该自动解码，但为了安全起见手动处理一次）
        from urllib.parse import unquote
        task_name = unquote(task_name)

        # 清理输入
        task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
        if not task_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="任务名称无效"
            )

        # 从数据库读取最新配置
        result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.task_name == task_name)
        )
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="定时任务不存在"
            )

        from app.scheduler_module import get_scheduler
        from app.scheduler_module.task_registry import get_task_function_by_name_or_path
        from app.scheduler_module.scheduler import register_scheduled_task

        sched = get_scheduler()

        # 如果任务被禁用，从调度器中移除
        if not task.is_active:
            if sched.get_job(task_name):
                sched.remove_job(task_name)
                logger.info(f"任务 '{task_name}' 已禁用，已从调度器中移除")
            return ResponseBaseSchema.success(
                data={"message": f"任务 '{task_name}' 已禁用，已从调度器中移除"}
            )

        # 如果任务被启用，重新注册（使用统一的获取逻辑）
        task_func = get_task_function_by_name_or_path(task_name, task.function_path)
        if task_func is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"任务 '{task_name}' 未找到对应的任务函数（function_path: {task.function_path}），无法注册到调度器"
            )

        if not task.cron_expression:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"任务 '{task_name}' 没有设置 cron_expression，无法注册到调度器"
            )

        # 重新注册任务
        register_scheduled_task(
            task_name=task_name,
            task_func=task_func,
            cron_expression=task.cron_expression,
            description=task.description or f"自动注册的任务: {task_name}"
        )

        logger.info(
            f"管理员 {current_user.username} 重新加载了定时任务: {task_name} "
            f"(Cron: {task.cron_expression})"
        )

        return ResponseBaseSchema.success(
            data={
                "message": f"任务 '{task_name}' 已重新加载",
                "cron_expression": task.cron_expression,
                "is_active": task.is_active
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新加载定时任务失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新加载定时任务失败: {str(e)}"
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
    重新加载所有定时任务配置
    - 从数据库重新读取所有任务配置并更新到调度器
    - 适用于直接在数据库中修改了任务配置的情况
    - 仅管理员可访问
    """
    try:
        from app.scheduler_module import init_scheduled_tasks

        # 重新初始化所有任务（会从数据库重新读取）
        await init_scheduled_tasks()

        logger.info(f"管理员 {current_user.username} 重新加载了所有定时任务")

        return ResponseBaseSchema.success(
            data={"message": "所有定时任务已重新加载"}
        )

    except Exception as e:
        logger.error(f"重新加载所有定时任务失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新加载所有定时任务失败: {str(e)}"
        )


@router.get(
    "/queue-status",
    response_model=ResponseBaseSchema[dict],
    summary="获取任务队列状态",
    dependencies=[Depends(require_admin)]
)
async def get_task_queue_status(
    current_user: User = Depends(require_admin)
):
    """
    获取任务执行队列的当前状态
    
    返回信息包括：
    - current_running: 当前正在执行的任务数
    - max_concurrent: 最大并发任务数
    - queue_length: 队列中等待的任务数
    - running_tasks: 正在执行的任务名称列表
    - queued_tasks: 队列中等待的任务名称列表
    - queue_details: 队列详细信息（包含优先级和等待时间）
    
    仅管理员可访问
    """
    try:
        from app.scheduler_module.task_queue import get_task_queue
        
        queue = get_task_queue()
        status = await queue.get_queue_status()
        
        return ResponseBaseSchema(
            success=True,
            message="获取队列状态成功",
            data=status
        )
    except Exception as e:
        logger.error(f"获取任务队列状态失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务队列状态失败: {str(e)}"
        )


@router.get(
    "/scheduler-status",
    response_model=ResponseBaseSchema[dict],
    summary="获取调度器状态（诊断用）"
)
async def get_scheduler_status(
        current_user: User = Depends(require_admin)
):
    """
    获取调度器的详细状态信息，用于诊断定时任务是否正常运行
    - 仅管理员可访问
    - 显示调度器运行状态、已注册任务列表、下次执行时间等
    """
    try:
        from app.scheduler_module import get_scheduler
        import os
        
        sched = get_scheduler()
        worker_pid = os.getpid()
        
        # 获取所有已注册的任务
        jobs = sched.get_jobs()
        
        # 构建任务详情列表
        jobs_info = []
        for job in jobs:
            next_run_time = job.next_run_time
            next_run_str = next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z') if next_run_time else "未计划"
            
            jobs_info.append({
                'id': job.id,
                'name': job.name,
                'next_run_time': next_run_str,
                'trigger': str(job.trigger),
                'func': str(job.func) if hasattr(job, 'func') else 'N/A'
            })
        
        status_data = {
            'worker_pid': worker_pid,
            'scheduler_running': sched.running,
            'total_jobs': len(jobs),
            'jobs': jobs_info
        }
        
        return ResponseBaseSchema.success(data=status_data)
    except Exception as e:
        logger.error(f"获取调度器状态失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取调度器状态失败: {str(e)}"
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
    释放任务锁（紧急操作）
    - 仅管理员可访问
    - 用于任务异常中断导致锁未释放的情况
    - 使用数据库锁确保原子性操作
    """
    try:
        # URL 解码（FastAPI 应该自动解码，但为了安全起见手动处理一次）
        from urllib.parse import unquote
        task_name = unquote(task_name)

        # 清理输入
        task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
        if not task_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="任务名称无效"
            )

        # 使用数据库锁获取任务记录（防止并发冲突）
        result = await db.execute(
            select(ScheduledTask)
            .where(ScheduledTask.task_name == task_name)
            .with_for_update(of=ScheduledTask)
        )
        task = result.scalar_one_or_none()

        if not task:
            # 注意：不需要手动回滚事务，get_db 依赖会自动处理
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="定时任务不存在"
            )

        if not task.is_running:
            # 注意：不需要手动回滚事务，get_db 依赖会自动处理
            return ResponseBaseSchema.success(
                data={"message": "任务未在运行，无需释放锁"}
            )

        # 释放锁
        task.is_running = False
        task.updated_at = get_app_now_naive()
        task.last_error = "管理员手动释放锁"

        # 注意：不需要手动提交事务，get_db 依赖会自动处理

        logger.warning(f"管理员 {current_user.username} 手动释放了任务锁: {task_name}")

        return ResponseBaseSchema.success(
            data={"message": "任务锁已释放"}
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"释放任务锁失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="释放任务锁失败"
        )
