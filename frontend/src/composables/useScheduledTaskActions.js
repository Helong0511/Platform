import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  updateScheduledTask,
  triggerScheduledTask,
  releaseTaskLock,
} from '../api/scheduled-task';
import { extractErrorMessage, isErrorHandled } from '../utils/api';
import { DATE_RELATED_TASK_NAMES } from '../utils/cronValidate';

/**
 * 定时任务行操作：启停、手动触发、释放锁。
 */
export function useScheduledTaskActions({ fetchTasks }) {
  const triggerDialogVisible = ref(false);
  const currentTriggerTask = ref(null);
  const triggerParams = ref({ start_date: '', end_date: '' });

  const scheduleRefresh = (ms = 2000) => {
    setTimeout(() => fetchTasks(), ms);
  };

  const handleToggleActive = async (task) => {
    const originalState = task.is_active;
    try {
      await updateScheduledTask(task.task_name, { is_active: task.is_active });
      fetchTasks();
    } catch (error) {
      task.is_active = originalState;
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    }
  };

  const handleTrigger = async (task) => {
    if (DATE_RELATED_TASK_NAMES.includes(task.task_name)) {
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
      scheduleRefresh();
    } catch (error) {
      if (error !== 'cancel' && !isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    }
  };

  const confirmTrigger = async () => {
    try {
      const params = {};
      if (triggerParams.value.start_date) params.start_date = triggerParams.value.start_date;
      if (triggerParams.value.end_date) params.end_date = triggerParams.value.end_date;
      await triggerScheduledTask(currentTriggerTask.value.task_name, params);
      ElMessage.success('任务已触发，正在后台执行');
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
