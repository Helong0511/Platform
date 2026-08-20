/**
 * 组合式函数 - 定时任务操作：启停/立即执行
 * @file composables/useScheduledTaskActions.js
 *
 * 运行中任务禁止切换启用状态；触发后轮询至结束，刷新「最后错误/结果」列。
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

const TRIGGER_POLL_INTERVAL_MS = 2000;
const TRIGGER_POLL_MAX_MS = 5 * 60 * 1000;

/**
 * 定时任务行操作：启停、手动触发、释放锁。
 */
export function useScheduledTaskActions({ fetchTasks, tasks }) {
  const triggerDialogVisible = ref(false);
  const currentTriggerTask = ref(null);
  const triggerParams = ref({ start_date: '', end_date: '' });
  const triggerPollTimers = new Map();

  const scheduleRefresh = (ms = 800) => {
    // 触发后尽快拉取，使 is_running 反映到「正在运行」与禁用启用开关
    setTimeout(() => fetchTasks(true), ms);
  };

  const stopTriggerPoll = (taskName) => {
    const timer = triggerPollTimers.get(taskName);
    if (timer != null) {
      clearInterval(timer);
      triggerPollTimers.delete(taskName);
    }
  };

  /**
   * 手动触发后轮询列表，直到任务结束（is_running=false）或超时，
   * 以便「最后错误」列展示本次执行结果摘要。
   */
  const pollUntilTaskFinished = (taskName) => {
    if (!taskName) return;
    stopTriggerPoll(taskName);
    const startedAt = Date.now();
    const timer = setInterval(async () => {
      try {
        await fetchTasks(true);
        const rows = Array.isArray(tasks?.value) ? tasks.value : [];
        const row = rows.find((item) => item?.task_name === taskName);
        const finished = row ? !isTaskRunning(row) : Date.now() - startedAt > 15000;
        if (finished || Date.now() - startedAt >= TRIGGER_POLL_MAX_MS) {
          stopTriggerPoll(taskName);
        }
      } catch {
        if (Date.now() - startedAt >= TRIGGER_POLL_MAX_MS) {
          stopTriggerPoll(taskName);
        }
      }
    }, TRIGGER_POLL_INTERVAL_MS);
    triggerPollTimers.set(taskName, timer);
    // 立即刷一次，再进入轮询
    scheduleRefresh(300);
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
      ElMessage.success('任务已触发，正在后台执行；完成后结果会显示在「最后结果」列');
      // 乐观更新：立即显示运行中并禁用启用开关
      task.is_running = true;
      pollUntilTaskFinished(task.task_name);
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
      const taskName = currentTriggerTask.value?.task_name;
      await triggerScheduledTask(taskName, params);
      ElMessage.success('任务已触发，正在后台执行；完成后结果会显示在「最后结果」列');
      if (task) task.is_running = true;
      triggerDialogVisible.value = false;
      pollUntilTaskFinished(taskName);
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
      stopTriggerPoll(task.task_name);
      scheduleRefresh(1000);
    } catch (error) {
      if (error !== 'cancel' && !isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
    }
  };

  // 标准数据维度设置
  const standardReportTypeDialogVisible = ref(false);
  const currentStandardReportTypeTask = ref(null);
  const standardReportTypeForm = ref({ standard_report_type: null });

  const REPORT_TYPE_LABELS = {
    country: '国家',
    cross: '交叉（国家+广告单元）',
    unit: '广告单元',
    daily: '日报',
  };

  const handleSetStandardReportType = (task) => {
    currentStandardReportTypeTask.value = task;
    standardReportTypeForm.value = {
      standard_report_type: task.standard_report_type || null,
    };
    standardReportTypeDialogVisible.value = true;
  };

  const confirmStandardReportType = async () => {
    const task = currentStandardReportTypeTask.value;
    if (!task) return;
    try {
      await updateScheduledTask(task.task_name, {
        standard_report_type: standardReportTypeForm.value.standard_report_type,
      });
      ElMessage.success('标准数据维度已更新');
      standardReportTypeDialogVisible.value = false;
      fetchTasks(true);
    } catch (error) {
      if (!isErrorHandled(error)) {
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
    standardReportTypeDialogVisible,
    currentStandardReportTypeTask,
    standardReportTypeForm,
    handleSetStandardReportType,
    confirmStandardReportType,
  };
}
