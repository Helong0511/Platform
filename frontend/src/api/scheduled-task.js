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
export const getScheduledTasks = async (params, options = {}) =>
  request(
    {
      url: '/api/v1/scheduled-tasks/',
      method: 'get',
      params,
      signal: options.signal,
    },
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

/**
 * 获取 GAM 多账号完整配置。
 */
export const getGamSchedulerConfig = async (taskName) =>
  request(
    { url: scheduledTaskPath(taskName, 'gam-config'), method: 'get' },
    { returnDataOnly: true }
  );

/**
 * 保存 GAM 多账号完整配置。
 */
export const saveGamSchedulerConfig = async (taskName, data) => {
  const result = await withCsrfMutate(() =>
    request(
      {
        url: scheduledTaskPath(taskName, 'gam-config'),
        method: 'put',
        data,
      },
      { returnDataOnly: true }
    )
  );
  ElMessage.success('GAM 配置已保存');
  return result;
};

/**
 * 上传 GAM 服务账号密钥 JSON（保存到服务端 secrets 目录）。
 */
export const uploadGamCredentials = async (taskName, file, networkCode = null) => {
  const formData = new FormData();
  formData.append('file', file);
  if (networkCode) {
    formData.append('network_code', String(networkCode).trim());
  }
  const result = await withCsrfMutate(() =>
    request(
      {
        url: scheduledTaskPath(taskName, 'gam-secrets/upload'),
        method: 'post',
        data: formData,
      },
      { returnDataOnly: true, timeout: 60000 }
    )
  );
  ElMessage.success('密钥文件已上传');
  return result;
};

/**
 * 刷新指定 GAM 账号的报表类型（探测 Google API）。
 * @param {string} taskName
 * @param {{ account_key?: string, credentials_json?: string, application_name?: string }} account
 */
export const refreshGamReportTypes = async (taskName, account = {}) => {
  const payload = {};
  if (account?.account_key) payload.account_key = String(account.account_key).trim();
  if (account?.credentials_json) payload.credentials_json = String(account.credentials_json).trim();
  if (account?.application_name) payload.application_name = String(account.application_name).trim();
  const result = await withCsrfMutate(() =>
    request(
      {
        url: scheduledTaskPath(taskName, 'gam-report-types/refresh'),
        method: 'post',
        data: payload,
      },
      { returnDataOnly: true, timeout: 180000 }
    )
  );
  return result;
};
