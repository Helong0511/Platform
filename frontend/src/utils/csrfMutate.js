/**
 * 写操作前统一刷新 CSRF 令牌
 * @file utils/csrfMutate.js
 *
 * 封装 withCsrfMutate / prepareCsrfMutate，在 POST/PUT/DELETE 前自动刷新 CSRF。
 */
import { refreshCsrfTokenBeforeRequest, ensureCsrfToken } from './api';

/** 重导出：确保本地 CSRF 令牌可用 */
export { ensureCsrfToken };

/** 多数管理端写操作使用的轻量 GET 端点（用于刷新 CSRF） */
export const CSRF_REFRESH_DASHBOARD = '/api/v1/dashboard/stats';

/** 客户模块写操作前的 CSRF 刷新端点 */
export const CSRF_REFRESH_CLIENTS = '/api/v1/clients/?page_size=1';
/** 产品模块写操作前的 CSRF 刷新端点 */
export const CSRF_REFRESH_PRODUCTS = '/api/v1/products/?page_size=1';
/** 用户模块写操作前的 CSRF 刷新端点 */
export const CSRF_REFRESH_USERS = '/api/v1/users/stats';
/** 会话模块写操作前的 CSRF 刷新端点 */
export const CSRF_REFRESH_SESSIONS = '/api/v1/sessions/me/sessions';

/**
 * @param {string} [endpoint]
 * @returns {Promise<void>}
 */
export async function csrfBeforeMutate(endpoint = CSRF_REFRESH_DASHBOARD) {
  await refreshCsrfTokenBeforeRequest(endpoint);
}

/**
 * @param {() => Promise<T>} fn
 * @param {string} [endpoint]
 * @returns {Promise<T>}
 */
export async function withCsrfMutate(fn, endpoint = CSRF_REFRESH_DASHBOARD) {
  await csrfBeforeMutate(endpoint);
  return fn();
}

/**
 * 刷新 CSRF 并确保本地令牌可用（客户/用户等需双重校验的写操作）
 * @param {string} [endpoint]
 */
export async function prepareCsrfMutate(endpoint = CSRF_REFRESH_DASHBOARD) {
  await csrfBeforeMutate(endpoint);
  await ensureCsrfToken();
}

/**
 * 403 且为 CSRF 相关时提示并清除本地令牌
 * @returns {boolean} 是否已按 CSRF 错误处理
 */
export function handleCsrf403IfNeeded(error, { extractErrorMessage, handleError, ElMessage }) {
  const errorMsg = extractErrorMessage(error);
  if (error.response?.status !== 403) {
    return false;
  }
  const detail = error.response?.data?.detail || errorMsg;
  if (detail && /csrf|令牌/i.test(String(detail))) {
    ElMessage.error('安全验证失败，请刷新页面后重试');
    sessionStorage.removeItem('csrf_token');
    return true;
  }
  handleError(error);
  return true;
}
