/**
 * 统一错误处理工具
 */
import { ElMessage } from 'element-plus';
import logger from './logger';

// 错误码映射
const ERROR_MESSAGES = {
  400: '请求参数错误',
  401: '未授权，请重新登录',
  403: '禁止访问',
  404: '资源不存在',
  409: '资源冲突',
  422: '数据验证失败',
  429: '请求过于频繁',
  500: '服务器内部错误',
  502: '网关错误',
  503: '服务不可用',
  504: '网关超时'
};

/**
 * 提取错误消息
 */
export const extractErrorMessage = (error) => {
  if (error?.response?.data?.detail) return error.response.data.detail;
  if (error?.response?.data?.message) return error.response.data.message;
  if (error?.message) return error.message;
  return '操作失败';
};

/**
 * 统一处理 API 错误
 */
export const handleApiError = (error, options = {}) => {
  const { showMessage = true, showLog = true } = options;
  
  const status = error?.response?.status;
  const message = extractErrorMessage(error);
  
  // 记录日志
  if (showLog) {
    logger.error('API 错误:', { status, message, error });
  }
  
  // 显示消息
  if (showMessage) {
    const defaultMessage = ERROR_MESSAGES[status] || message;
    ElMessage.error(defaultMessage);
  }
  
  // 特殊处理
  if (status === 401) {
    // 清除认证信息并跳转登录
    sessionStorage.removeItem('userInfo');
    window.location.href = '/login';
  }
  
  return message;
};

/**
 * 检查错误是否已处理
 */
export const isErrorHandled = (error) => {
  return error?.handled === true;
};

/**
 * 标记错误为已处理
 */
export const markErrorAsHandled = (error) => {
  if (error && typeof error === 'object') {
    error.handled = true;
  }
};

export default {
  extractErrorMessage,
  handleApiError,
  isErrorHandled,
  markErrorAsHandled
};
