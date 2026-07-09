/**
 * 组合式函数 - 定时任务操作：启停/立即执行
 * @file composables/useScheduledTaskActions.js
 *
 * 运行中任务禁止切换启用状态；触发后立即刷新列表以展示「正在运行」。
 */
import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  updateScheduledTask,
  triggerScheduledTask,
  releaseTaskLock,
} from '../api/scheduled-task';
import { extractErrorMessage, isErrorHandled } from '../utils/api';
import { taskSupportsManualDateRange } from '../utils/cronValidate';
import { isTaskRunning } from '../utils/scheduledTaskStatus';

/**
 * 定时任务行操作：启停、手动触发、释放锁。
 */
export function useScheduledTaskActions({ fetchTasks }) {
  const triggerDialogVisible = ref(false);
  const currentTriggerTask = ref(null);
  const triggerParams = ref({ start_date: '', end_date: '' });

  const scheduleRefresh = (ms = 800) => {
    // 触发后尽快拉取，使 is_running 反映到「正在运行」与禁用启用开关
    setTimeout(() => fetchTasks(true), ms);
  };

  const handleToggleActive = async (task) => {
    const originalState = !task.is_active;
    // 运行中不允许切换启用（前端拦截；后端亦有校验）
    if (isTaskRunning(task)) {
      task.is_active = originalState;
      ElMessage.warning('任务正在运行，无法切换启用状态');
      return;
    }
    try {
      await updateScheduledTask(task.task_name, { is_active: task.is_active });
      fetchTasks(true);
    } catch (error) {
      task.is_active = originalState;
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    }
  };

  const handleTrigger = async (task) => {
    if (isTaskRunning(task)) {
      ElMessage.warning('任务正在运行，请勿重复触发');
      return;
    }
    if (taskSupportsManualDateRange(task)) {
      currentTriggerTask.value = task;
      triggerParams.value = { start_date: '', end_date: '' };
      triggerDialogVisible.value = true;
      return;
    }
    try {
      await ElMessageBox.confirm(`确定要手动触发任务 "${task.task_name}" 吗？`, '确认触发', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      });
      await triggerScheduledTask(task.task_name);
      ElMessage.success('任务已触发，正在后台执行');
      // 乐观更新：立即显示运行中并禁用启用开关
      task.is_running = true;
      scheduleRefresh();
    } catch (error) {
      if (error !== 'cancel' && !isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    }
  };

  const confirmTrigger = async () => {
    const task = currentTriggerTask.value;
    if (task && isTaskRunning(task)) {
      ElMessage.warning('任务正在运行，请勿重复触发');
      triggerDialogVisible.value = false;
      return;
    }
    try {
      const params = {};
      if (triggerParams.value.start_date) params.start_date = triggerParams.value.start_date;
      if (triggerParams.value.end_date) params.end_date = triggerParams.value.end_date;
      await triggerScheduledTask(currentTriggerTask.value.task_name, params);
      ElMessage.success('任务已触发，正在后台执行');
      if (task) task.is_running = true;
      triggerDialogVisible.value = false;
      scheduleRefresh();
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    }
  };

  const handleReleaseLock = async (task) => {
    try {
      await ElMessageBox.confirm(
        `确定要释放任务 "${task.task_name}" 的锁吗？\n\n注意：这是一个紧急操作，只有在任务异常卡死时才应使用。`,
        '确认释放锁',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning',
        },
      );
      await releaseTaskLock(task.task_name);
      ElMessage.success('任务锁已释放');
      scheduleRefresh(1000);
    } catch (error) {
      if (error !== 'cancel' && !isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    }
  };

  return {
    triggerDialogVisible,
    currentTriggerTask,
    triggerParams,
    handleToggleActive,
    handleTrigger,
    confirmTrigger,
    handleReleaseLock,
  };
}
