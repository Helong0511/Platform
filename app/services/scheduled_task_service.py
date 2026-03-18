"""
定时任务管理服务层
封装定时任务查询和管理的业务逻辑
"""
import asyncio
import logging
import os
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import unquote

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import MAX_TASK_NAME_LENGTH, QUERY_TIMEOUT
from app.core.errors import ErrorCode
from app.core.exceptions import raise_api_exception
from app.core.fulltext_search import search_with_fulltext
from app.core.utils import get_app_now_naive
from app.core.validation import sanitize_input
from app.models.models import ScheduledTask, User
from app.scheduler_module import get_scheduler, init_scheduled_tasks
from app.scheduler_module.scheduler import register_scheduled_task, execute_task_with_lock
from app.scheduler_module.task_queue import get_task_queue
from app.scheduler_module.task_registry import get_task_function_by_name_or_path

logger = logging.getLogger(__name__)


class ScheduledTaskService:
    """定时任务服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_scheduled_tasks(
            self,
            page: int = 1,
            page_size: int = 10,
            is_active: Optional[bool] = None,
            is_running: Optional[bool] = None,
            task_name: Optional[str] = None
    ) -> Tuple[List[ScheduledTask], int]:
        """
        获取定时任务列表

        Args:
            page: 页码
            page_size: 每页数量
            is_active: 是否启用过滤
            is_running: 是否运行中过滤
            task_name: 任务名称搜索

        Returns:
            Tuple[List[ScheduledTask], int]: (任务列表, 总数)
        """
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
                query = await search_with_fulltext(
                    db=self.db,
                    model_class=ScheduledTask,
                    search_fields=["task_name", "description"],
                    search_term=cleaned_task_name,
                    base_query=query,
                    use_fulltext=True
                )

        # 其他过滤条件
        if conditions:
            query = query.where(and_(*conditions))

        # 排序：按ID升序（最新的任务ID最大）
        query = query.order_by(ScheduledTask.id.asc())

        # 获取总数
        count_query = select(func.count()).select_from(ScheduledTask)

        # 任务名称搜索（优先使用全文搜索，回退到LIKE）
        if task_name:
            cleaned_task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
            if cleaned_task_name:
                count_query = await search_with_fulltext(
                    db=self.db,
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
                self.db.execute(count_query),
                timeout=QUERY_TIMEOUT
            )
            total = total_result.scalar() or 0
        except asyncio.TimeoutError:
            logger.error("获取定时任务总数查询超时（30秒）")
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="查询超时，请稍后重试"
            )

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # 执行查询（添加超时保护，避免长时间阻塞）
        try:
            result = await asyncio.wait_for(
                self.db.execute(query),
                timeout=QUERY_TIMEOUT
            )
            tasks = result.scalars().all()
        except asyncio.TimeoutError:
            logger.error("获取定时任务列表查询超时（30秒）")
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail="查询超时，请稍后重试"
            )

        return tasks, total

    async def get_scheduled_task_by_name(self, task_name: str) -> Optional[ScheduledTask]:
        """
        获取定时任务详情

        Args:
            task_name: 任务名称

        Returns:
            Optional[ScheduledTask]: 任务对象，如果不存在则返回None
        """
        # URL 解码（FastAPI 应该自动解码，但为了安全起见手动处理一次）
        task_name = unquote(task_name)

        # 清理输入
        task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
        if not task_name:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="任务名称无效"
            )

        result = await self.db.execute(
            select(ScheduledTask).where(ScheduledTask.task_name == task_name)
        )
        return result.scalar_one_or_none()

    async def update_scheduled_task_status(
            self,
            task_name: str,
            is_active: bool,
            current_user: User
    ) -> ScheduledTask:
        """
        更新定时任务状态

        Args:
            task_name: 任务名称
            is_active: 是否启用
            current_user: 当前用户

        Returns:
            ScheduledTask: 更新后的任务对象
        """
        # URL 解码
        task_name = unquote(task_name)

        # 清理输入
        task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
        if not task_name:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="任务名称无效"
            )

        # 使用数据库锁获取任务记录（防止并发更新冲突）
        result = await self.db.execute(
            select(ScheduledTask)
            .where(ScheduledTask.task_name == task_name)
            .with_for_update(of=ScheduledTask)
        )
        task = result.scalar_one_or_none()

        if not task:
            await self.db.rollback()
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="定时任务不存在"
            )

        # 记录更新前的状态，用于判断是否需要重新注册任务
        old_is_active = task.is_active
        is_active_changed = (old_is_active != is_active)

        # 更新状态
        task.is_active = is_active
        task.updated_at = get_app_now_naive()

        try:
            await self.db.commit()
            await self.db.refresh(task)

            # 如果启用状态发生变化，需要重新注册任务或从调度器中移除
            if is_active_changed:
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

            return task
        except Exception as e:
            await self.db.rollback()
            logger.error(f"更新定时任务状态失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"更新定时任务状态失败: {str(e)}"
            )

    async def trigger_scheduled_task(
            self,
            task_name: str,
            params: Optional[Dict[str, Any]],
            current_user: User
    ) -> Dict[str, Any]:
        """
        手动触发定时任务

        Args:
            task_name: 任务名称
            params: 任务参数
            current_user: 当前用户

        Returns:
            Dict: 触发结果
        """
        # URL 解码
        task_name = unquote(task_name)

        # 清理输入
        task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
        if not task_name:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="任务名称无效"
            )

        # 检查任务是否存在
        result = await self.db.execute(
            select(ScheduledTask).where(ScheduledTask.task_name == task_name)
        )
        task = result.scalar_one_or_none()

        if not task:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="定时任务不存在"
            )

        if not task.is_active:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="定时任务未启用，无法触发"
            )

        # 导入调度器并触发任务
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
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=error_msg
                )

            # 检查是否有 cron_expression
            if not task.cron_expression:
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
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
                    raise_api_exception(
                        ErrorCode.OPERATION_FAILED,
                        detail=f"任务 '{task_name}' 重新注册失败，请检查日志"
                    )
            except ValueError as e:
                raise_api_exception(
                    ErrorCode.INVALID_PARAMETER,
                    detail=f"任务 '{task_name}' 重新注册失败（参数错误）: {str(e)}"
                )
            except Exception as e:
                logger.error(f"任务 '{task_name}' 重新注册失败: {e}", exc_info=True)
                raise_api_exception(
                    ErrorCode.OPERATION_FAILED,
                    detail=f"任务 '{task_name}' 重新注册失败: {str(e)}"
                )

        # 获取任务函数并手动执行
        task_func = get_task_function_by_name_or_path(task_name, task.function_path)
        if task_func is None:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"无法找到任务函数: {task.function_path}"
            )

        # 手动触发时，跳过进程分配检查（skip_process_check=True）
        async def trigger_task():
            try:
                logger.info(f"开始手动触发任务 '{task_name}'（跳过进程分配检查）")

                # 准备任务参数
                task_kwargs = {}
                if params:
                    if params.get('start_date'):
                        task_kwargs['start_date'] = params['start_date']
                    if params.get('end_date'):
                        task_kwargs['end_date'] = params['end_date']

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

        return {"message": "任务已触发，正在后台执行"}

    async def reload_scheduled_task(
            self,
            task_name: str,
            current_user: User
    ) -> Dict[str, Any]:
        """
        重新加载任务配置

        Args:
            task_name: 任务名称
            current_user: 当前用户

        Returns:
            Dict: 重新加载结果
        """
        # URL 解码
        task_name = unquote(task_name)

        # 清理输入
        task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
        if not task_name:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="任务名称无效"
            )

        # 从数据库读取最新配置
        result = await self.db.execute(
            select(ScheduledTask).where(ScheduledTask.task_name == task_name)
        )
        task = result.scalar_one_or_none()

        if not task:
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="定时任务不存在"
            )

        sched = get_scheduler()

        # 如果任务被禁用，从调度器中移除
        if not task.is_active:
            if sched.get_job(task_name):
                sched.remove_job(task_name)
                logger.info(f"任务 '{task_name}' 已禁用，已从调度器中移除")
            return {
                "message": f"任务 '{task_name}' 已禁用，已从调度器中移除"
            }

        # 如果任务被启用，重新注册（使用统一的获取逻辑）
        task_func = get_task_function_by_name_or_path(task_name, task.function_path)
        if task_func is None:
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"任务 '{task_name}' 未找到对应的任务函数（function_path: {task.function_path}），无法注册到调度器"
            )

        if not task.cron_expression:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
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

        return {
            "message": f"任务 '{task_name}' 已重新加载",
            "cron_expression": task.cron_expression,
            "is_active": task.is_active
        }

    async def reload_all_scheduled_tasks(self, current_user: User) -> Dict[str, Any]:
        """
        重新加载所有任务配置

        Args:
            current_user: 当前用户

        Returns:
            Dict: 重新加载结果
        """

        # 重新初始化所有任务（会从数据库重新读取）
        await init_scheduled_tasks()

        logger.info(f"管理员 {current_user.username} 重新加载了所有定时任务")

        return {"message": "所有定时任务已重新加载"}

    async def get_task_queue_status(self) -> Dict[str, Any]:
        """
        获取任务队列状态

        Returns:
            Dict: 队列状态信息
        """

        queue = get_task_queue()
        status = await queue.get_queue_status()

        return status

    async def get_scheduler_status(self) -> Dict[str, Any]:
        """
        获取调度器状态

        Returns:
            Dict: 调度器状态信息
        """

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

        return {
            'worker_pid': worker_pid,
            'scheduler_running': sched.running,
            'total_jobs': len(jobs),
            'jobs': jobs_info
        }

    async def release_task_lock(
            self,
            task_name: str,
            current_user: User
    ) -> Dict[str, Any]:
        """
        释放任务锁（紧急操作）

        Args:
            task_name: 任务名称
            current_user: 当前用户

        Returns:
            Dict: 释放结果
        """
        # URL 解码
        task_name = unquote(task_name)

        # 清理输入
        task_name = sanitize_input(task_name.strip(), max_length=MAX_TASK_NAME_LENGTH)
        if not task_name:
            raise_api_exception(
                ErrorCode.INVALID_PARAMETER,
                detail="任务名称无效"
            )

        # 使用数据库锁获取任务记录（防止并发冲突）
        result = await self.db.execute(
            select(ScheduledTask)
            .where(ScheduledTask.task_name == task_name)
            .with_for_update(of=ScheduledTask)
        )
        task = result.scalar_one_or_none()

        if not task:
            await self.db.rollback()
            raise_api_exception(
                ErrorCode.RESOURCE_NOT_FOUND,
                detail="定时任务不存在"
            )

        if not task.is_running:
            await self.db.rollback()
            return {"message": "任务未在运行，无需释放锁"}

        # 释放锁
        task.is_running = False
        task.updated_at = get_app_now_naive()
        task.last_error = "管理员手动释放锁"

        try:
            await self.db.commit()
            logger.warning(f"管理员 {current_user.username} 手动释放了任务锁: {task_name}")

            return {"message": "任务锁已释放"}
        except Exception as e:
            await self.db.rollback()
            logger.error(f"释放任务锁失败: {str(e)}", exc_info=True)
            raise_api_exception(
                ErrorCode.OPERATION_FAILED,
                detail=f"释放任务锁失败: {str(e)}"
            )
