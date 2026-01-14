/**
 * 定时任务管理 API
 * 已统一使用 request 函数，保持代码一致性
 * 包含特殊逻辑：URL编码、任务触发、锁释放等
 */
import { request, normalizePaginatedResponse, normalizeResponse, extractErrorMessage, ensureCsrfToken, handleError, refreshCsrfTokenBeforeRequest } from '../utils/api';
import { ElMessage } from 'element-plus';
import { getSuccessMessage } from '../utils/messages';
import { logger } from '../utils/logger';
import axios from 'axios'; // 保留用于特殊场景（URL编码、任务触发等）

/**
 * 获取定时任务列表
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页条数
 * @param {boolean} [params.is_active] - 是否启用筛选
 * @param {boolean} [params.is_running] - 是否运行中筛选
 * @param {string} [params.task_name] - 任务名称搜索
 * @returns {Promise<Object>} 定时任务列表数据
 */
export const getScheduledTasks = async (params) => {
  return request({
    url: '/api/v1/scheduled-tasks/',
    method: 'get',
    params
  }, { paginated: true });
};

/**
 * 获取定时任务详情
 * @param {string} taskName - 任务名称
 * @returns {Promise<Object>} 定时任务详情
 */
export const getScheduledTask = async (taskName) => {
  // 对任务名称进行 URL 编码，确保中文路径正确传输
  const encodedTaskName = encodeURIComponent(taskName);
  
  return request({
    url: `/api/v1/scheduled-tasks/${encodedTaskName}`,
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 创建定时任务
 * @param {Object} data - 任务数据
 * @param {string} data.task_name - 任务名称
 * @param {string} data.cron_expression - Cron表达式
 * @param {string} [data.description] - 任务描述
 * @param {string} [data.function_path] - 函数路径
 * @param {boolean} [data.is_active] - 是否启用
 * @returns {Promise<Object>} 创建后的定时任务
 */
export const createScheduledTask = async (data) => {
  // 在保存前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  
  const result = await request({
    url: '/api/v1/scheduled-tasks/',
    method: 'post',
    data
  }, { returnDataOnly: true });
  
  ElMessage.success(getSuccessMessage('TASK_CREATE_SUCCESS'));
  return result;
};

/**
 * 更新定时任务
 * @param {string} taskName - 任务名称
 * @param {Object} data - 更新数据
 * @param {string} [data.task_name] - 任务名称（修改时需要）
 * @param {boolean} [data.is_active] - 是否启用
 * @param {string} [data.description] - 任务描述
 * @param {string} [data.cron_expression] - Cron表达式
 * @param {string} [data.function_path] - 函数路径
 * @returns {Promise<Object>} 更新后的定时任务
 */
export const updateScheduledTask = async (taskName, data) => {
  try {
    // 在保存前刷新CSRF令牌，确保使用最新的令牌
    await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
    
    // 对任务名称进行 URL 编码，确保中文路径正确传输
    const encodedTaskName = encodeURIComponent(taskName);
    const result = await request({
      url: `/api/v1/scheduled-tasks/${encodedTaskName}`,
      method: 'patch',
      data
    }, { returnDataOnly: true });
    
    ElMessage.success(getSuccessMessage('TASK_UPDATE_SUCCESS'));
    return result;
  } catch (error) {
    // request函数已经处理了CSRF token的重试
    // 如果仍然失败，说明token确实有问题
    const errorMsg = extractErrorMessage(error);
    
    // 如果是CSRF相关错误，提供更友好的提示
    if (error.response?.status === 403) {
      const errorDetail = error.response?.data?.detail || errorMsg;
      if (errorDetail && (errorDetail.includes('CSRF') || errorDetail.includes('csrf') || errorDetail.includes('令牌'))) {
        ElMessage.error('安全验证失败，请刷新页面后重试');
        // 清除旧的token，强制用户刷新页面
        sessionStorage.removeItem('csrf_token');
      } else {
        handleError(error);
      }
    } else {
      handleError(error);
    }
    throw error;
  }
};

/**
 * 手动触发定时任务
 * @param {string} taskName - 任务名称
 * @param {Object} params - 可选参数 { start_date?: string, end_date?: string }
 * @returns {Promise<Object>} 触发结果
 */
export const triggerScheduledTask = async (taskName, params = {}) => {
  // 在触发前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  
  const encodedTaskName = encodeURIComponent(taskName);
  const result = await request({
    url: `/api/v1/scheduled-tasks/${encodedTaskName}/trigger`,
    method: 'post',
    data: Object.keys(params).length > 0 ? params : undefined  // 如果有参数才发送body
  }, { returnDataOnly: true });
  
  ElMessage.success(getSuccessMessage('TASK_TRIGGER_SUCCESS'));
  return result;
};

/**
 * 释放任务锁（紧急操作）
 * @param {string} taskName - 任务名称
 * @returns {Promise<Object>} 操作结果
 */
export const releaseTaskLock = async (taskName) => {
  // 在操作前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  
  // 对任务名称进行 URL 编码，确保中文路径正确传输
  const encodedTaskName = encodeURIComponent(taskName);
  const result = await request({
    url: `/api/v1/scheduled-tasks/${encodedTaskName}/release-lock`,
    method: 'post'
  }, { returnDataOnly: true });
  
  ElMessage.success(getSuccessMessage('TASK_LOCK_RELEASED'));
  return result;
};

