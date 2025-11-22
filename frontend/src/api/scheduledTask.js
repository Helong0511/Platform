import axios from 'axios';
import { normalizePaginatedResponse, normalizeResponse, extractErrorMessage, isErrorHandled } from '../utils/api';
import { ElMessage } from 'element-plus';
import { getSuccessMessage } from '../utils/messages';
import { logger } from '../utils/logger';

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
  try {
    const response = await axios.get('/api/v1/scheduled-tasks/', { params });
    return normalizePaginatedResponse(response);
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

/**
 * 获取定时任务详情
 * @param {string} taskName - 任务名称
 * @returns {Promise<Object>} 定时任务详情
 */
export const getScheduledTask = async (taskName) => {
  try {
    // 对任务名称进行 URL 编码，确保中文路径正确传输
    const encodedTaskName = encodeURIComponent(taskName);
    const response = await axios.get(`/api/v1/scheduled-tasks/${encodedTaskName}`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
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
  try {
    const response = await axios.post('/api/v1/scheduled-tasks/', data);
    ElMessage.success(getSuccessMessage('TASK_CREATE_SUCCESS'));
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
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
    // 在发送PATCH请求前，先发送一个GET请求来获取最新的CSRF token
    // 这样可以确保token是最新的，避免token过期或不匹配的问题
    try {
      await axios.get('/api/v1/scheduled-tasks/', {
        timeout: 5000,
        validateStatus: () => true // 接受任何状态码，因为我们只是为了获取CSRF token
      });
      // 等待一小段时间，确保响应拦截器已经处理完响应头
      await new Promise(resolve => setTimeout(resolve, 150));
    } catch (tokenError) {
      // 即使获取token失败，也继续尝试，因为axios拦截器可能会自动处理
      logger.warn(`[updateScheduledTask] 获取CSRF token时出错，但继续尝试: ${tokenError.message}`);
    }
    
    // 检查CSRF token是否存在
    const csrfToken = sessionStorage.getItem('csrf_token');
    if (!csrfToken) {
      logger.error(`[updateScheduledTask] CSRF令牌缺失，无法更新任务 ${taskName}`);
      ElMessage.error('CSRF令牌缺失，请刷新页面后重试');
      throw new Error('CSRF令牌缺失，请刷新页面后重试');
    }
    
    // 对任务名称进行 URL 编码，确保中文路径正确传输
    const encodedTaskName = encodeURIComponent(taskName);
    const response = await axios.patch(`/api/v1/scheduled-tasks/${encodedTaskName}`, data);
    ElMessage.success(getSuccessMessage('TASK_UPDATE_SUCCESS'));
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    // axios拦截器应该已经处理了CSRF token的重试
    // 如果仍然失败，说明token确实有问题
    if (isErrorHandled(error)) {
      throw error;
    }
    
    const errorMsg = extractErrorMessage(error);
    
    // 如果是CSRF相关错误，提供更友好的提示
    if (error.response?.status === 403) {
      const errorDetail = error.response?.data?.detail || errorMsg;
      if (errorDetail && (errorDetail.includes('CSRF') || errorDetail.includes('csrf') || errorDetail.includes('令牌'))) {
        ElMessage.error('安全验证失败，请刷新页面后重试');
        // 清除旧的token，强制用户刷新页面
        sessionStorage.removeItem('csrf_token');
      } else {
        ElMessage.error(errorMsg || '安全验证失败，请刷新页面后重试');
      }
    } else {
      ElMessage.error(errorMsg);
    }
    throw error;
  }
};

/**
 * 手动触发定时任务
 * @param {string} taskName - 任务名称
 * @returns {Promise<Object>} 触发结果
 */
export const triggerScheduledTask = async (taskName) => {
  try {
    // 对任务名称进行 URL 编码，确保中文路径正确传输
    const encodedTaskName = encodeURIComponent(taskName);
    const response = await axios.post(`/api/v1/scheduled-tasks/${encodedTaskName}/trigger`);
    ElMessage.success(getSuccessMessage('TASK_TRIGGER_SUCCESS'));
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

/**
 * 释放任务锁（紧急操作）
 * @param {string} taskName - 任务名称
 * @returns {Promise<Object>} 操作结果
 */
export const releaseTaskLock = async (taskName) => {
  try {
    // 对任务名称进行 URL 编码，确保中文路径正确传输
    const encodedTaskName = encodeURIComponent(taskName);
    const response = await axios.post(`/api/v1/scheduled-tasks/${encodedTaskName}/release-lock`);
    ElMessage.success(getSuccessMessage('TASK_LOCK_RELEASED'));
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

