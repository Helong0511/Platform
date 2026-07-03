/**
 * 定时任务相关常量
 */

/** Google Ad Manager 拉数定时任务（与后端 task_names.GAM_API_TASK_NAME 一致） */
export const GAM_SCHEDULED_TASK_NAME = 'Google API获取数据';

/**
 * 是否支持 GAM 多账号配置页
 * @param {{ task_name?: string, supports_gam_scheduler_config?: boolean }} task
 */
export function isGamSchedulerTask(task) {
  if (!task) return false;
  if (task.supports_gam_scheduler_config) return true;
  return task.task_name === GAM_SCHEDULED_TASK_NAME;
}
