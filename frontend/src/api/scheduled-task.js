/**
 * 定时任务管理 API
 * 包含特殊逻辑：URL编码、任务触发、锁释放等
 */
import { request, extractErrorMessage, handleError } from '../utils/api';
import { withCsrfMutate, handleCsrf403IfNeeded } from '../utils/csrfMutate';
import { scheduledTaskPath } from './helpers/scheduledTaskPaths';
import { ElMessage } from 'element-plus';
import { getSuccessMessage } from '../utils/messages';

/**
 * 分页获取定时任务列表。
 */
export const getScheduledTasks = async (params) =>
  request(
    { url: '/api/v1/scheduled-tasks/', method: 'get', params },
    { paginated: true }
  );

/**
 * 获取单条定时任务详情。
 */
export const getScheduledTask = async (taskName) =>
  request(
    { url: scheduledTaskPath(taskName), method: 'get' },
    { returnDataOnly: true }
  );

/**
 * 创建Scheduled Task。
 */
export const createScheduledTask = async (data) => {
  const result = await withCsrfMutate(() =>
    request(
      { url: '/api/v1/scheduled-tasks/', method: 'post', data },
      { returnDataOnly: true }
    )
  );
  ElMessage.success(getSuccessMessage('TASK_CREATE_SUCCESS'));
  return result;
};

/**
 * 更新Scheduled Task。
 */
export const updateScheduledTask = async (taskName, data) => {
  try {
    const result = await withCsrfMutate(() =>
      request(
        { url: scheduledTaskPath(taskName), method: 'patch', data },
        { returnDataOnly: true }
      )
    );
    ElMessage.success(getSuccessMessage('TASK_UPDATE_SUCCESS'));
    return result;
  } catch (error) {
    if (!handleCsrf403IfNeeded(error, { extractErrorMessage, handleError, ElMessage })) {
      handleError(error);
    }
    throw error;
  }
};

/**
 * triggerScheduledTask 接口。
 */
export const triggerScheduledTask = async (taskName, params = {}) => {
  const result = await withCsrfMutate(() =>
    request(
      {
        url: scheduledTaskPath(taskName, 'trigger'),
        method: 'post',
        data: Object.keys(params).length > 0 ? params : undefined
      },
      { returnDataOnly: true }
    )
  );
  ElMessage.success(getSuccessMessage('TASK_TRIGGER_SUCCESS'));
  return result;
};

/**
 * releaseTaskLock 接口。
 */
export const releaseTaskLock = async (taskName) => {
  const result = await withCsrfMutate(() =>
    request(
      { url: scheduledTaskPath(taskName, 'release-lock'), method: 'post' },
      { returnDataOnly: true }
    )
  );
  ElMessage.success(getSuccessMessage('TASK_LOCK_RELEASED'));
  return result;
};
