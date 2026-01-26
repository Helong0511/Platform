/**
 * CSRF Token 工具函数
 * 提供统一的 CSRF token 获取、存储和管理功能
 * 
 * 存储策略：
 * - 使用 localStorage 存储CSRF令牌（实现跨标签页同步）
 * - 使用 sessionStorage 作为临时缓存（快速读取）
 * - localStorage 的 storage 事件会自动触发跨标签页同步
 */
import axios from 'axios';
import { logger } from './logger';

// 跨标签页同步的标记，避免循环触发
let isUpdatingFromStorage = false;

/**
 * 初始化跨标签页的CSRF令牌同步机制
 * 当其他标签页更新CSRF令牌时，当前标签页也会自动更新
 */
export const initCsrfTokenSync = () => {
  // 监听storage事件，实现跨标签页同步
  window.addEventListener('storage', (e) => {
    if (e.key === 'csrf_token' && e.newValue) {
      isUpdatingFromStorage = true;
      const oldToken = localStorage.getItem('csrf_token');
      if (oldToken !== e.newValue) {
        // 同步到 localStorage 和 sessionStorage
        localStorage.setItem('csrf_token', e.newValue);
        sessionStorage.setItem('csrf_token', e.newValue);
        logger.info('从其他标签页同步了新的 CSRF token');
      }
      isUpdatingFromStorage = false;
    }
  });

  // 初始化时，从 localStorage 同步到 sessionStorage（如果存在）
  const localStorageToken = localStorage.getItem('csrf_token');
  if (localStorageToken) {
    const sessionStorageToken = sessionStorage.getItem('csrf_token');
    if (!sessionStorageToken || sessionStorageToken !== localStorageToken) {
      sessionStorage.setItem('csrf_token', localStorageToken);
      logger.debug('从 localStorage 同步 CSRF token 到 sessionStorage');
    }
  }

  logger.debug('已初始化 CSRF token 跨标签页同步机制');
};

/**
 * 从响应头中提取 CSRF token
 * @param {Object} headers - 响应头对象
 * @returns {string|null} CSRF token，如果不存在则返回 null
 */
export const extractCsrfTokenFromHeaders = (headers) => {
  if (!headers) return null;
  return headers['x-csrf-token'] || headers['X-CSRF-Token'] || null;
};

/**
 * 从响应对象中提取并保存 CSRF token
 * 同时保存到 localStorage 和 sessionStorage
 * @param {Object} response - Axios 响应对象或错误响应对象
 * @returns {string|null} 提取到的 CSRF token，如果不存在则返回 null
 */
export const extractAndSaveCsrfToken = (response) => {
  const headers = response?.headers || response?.response?.headers;
  const csrfToken = extractCsrfTokenFromHeaders(headers);

  if (csrfToken) {
    const oldToken = localStorage.getItem('csrf_token');
    // 只有当令牌发生变化时才更新，避免不必要的storage事件
    if (oldToken !== csrfToken) {
      // 同时保存到 localStorage 和 sessionStorage
      localStorage.setItem('csrf_token', csrfToken);
      sessionStorage.setItem('csrf_token', csrfToken);
      // 如果不是从storage事件触发的更新，记录日志
      if (!isUpdatingFromStorage) {
        logger.debug('已从响应头提取并保存 CSRF token');
      }
    }
  }

  return csrfToken;
};

/**
 * 从存储中获取 CSRF token
 * 优先从 sessionStorage 读取（更快），如果不存在则从 localStorage 读取
 * @returns {string|null} CSRF token，如果不存在则返回 null
 */
export const getCsrfToken = () => {
  // 优先从 sessionStorage 读取
  let token = sessionStorage.getItem('csrf_token');
  if (!token) {
    // 如果 sessionStorage 中没有，尝试从 localStorage 读取
    token = localStorage.getItem('csrf_token');
    if (token) {
      // 同步到 sessionStorage
      sessionStorage.setItem('csrf_token', token);
    }
  }
  return token;
};

/**
 * 保存 CSRF token 到 sessionStorage
 * @param {string} token - CSRF token
 */
export const saveCsrfToken = (token) => {
  if (token) {
    const oldToken = sessionStorage.getItem('csrf_token');
    // 只有当令牌发生变化时才更新，避免不必要的storage事件
    if (oldToken !== token) {
      sessionStorage.setItem('csrf_token', token);
      // 如果不是从storage事件触发的更新，记录日志
      if (!isUpdatingFromStorage) {
        logger.debug('已保存 CSRF token');
      }
    }
  }
};

/**
 * 从响应头中获取 CSRF token（兼容多种响应格式）
 * @param {Object} responseOrError - Axios 响应对象或错误对象
 * @returns {string|null} CSRF token，如果不存在则返回 null
 */
export const getCsrfTokenFromResponse = (responseOrError) => {
  // 支持正常响应
  if (responseOrError?.headers) {
    return extractCsrfTokenFromHeaders(responseOrError.headers);
  }

  // 支持错误响应
  if (responseOrError?.response?.headers) {
    return extractCsrfTokenFromHeaders(responseOrError.response.headers);
  }

  return null;
};

/**
 * 初始化页面可见性变化时的CSRF令牌刷新机制
 * 当用户切换回标签页时，自动刷新CSRF令牌
 */
export const initPageVisibilityRefresh = () => {
  let lastRefreshTime = 0;
  const REFRESH_INTERVAL = 5 * 60 * 1000; // 5分钟

  document.addEventListener('visibilitychange', async () => {
    // 只有当页面变为可见时才刷新令牌
    if (document.visibilityState === 'visible') {
      const now = Date.now();
      // 距离上次刷新超过5分钟才刷新，避免频繁请求
      if (now - lastRefreshTime > REFRESH_INTERVAL) {
        try {
          logger.debug('页面变为可见，尝试刷新CSRF令牌');
          const newToken = await fetchCsrfTokenFromEndpoints();
          if (newToken) {
            lastRefreshTime = now;
            logger.info('页面可见性变化时刷新了CSRF令牌');
          }
        } catch (error) {
          // 刷新失败不影响使用，静默处理
          logger.debug('页面可见性变化时刷新CSRF令牌失败:', error);
        }
      }
    }
  });

  logger.debug('已初始化页面可见性变化时的CSRF令牌刷新机制');
};

/**
 * 尝试从多个端点获取 CSRF token
 * @param {Array<string>} endpoints - 要尝试的端点列表（可选，默认使用常用端点）
 * @returns {Promise<string|null>} CSRF token，如果获取失败则返回 null
 */
export const fetchCsrfTokenFromEndpoints = async (endpoints = null) => {
  const defaultEndpoints = [
    '/api/v1/users/stats',
    '/api/v1/dashboard/stats',
    '/api/v1/products/?page_size=1',
    '/api/v1/short-links/?page_size=1',
    '/api/v1/clients/?page_size=1'
  ];

  const endpointsToTry = endpoints || defaultEndpoints;

  for (const endpoint of endpointsToTry) {
    try {
      const response = await axios.get(endpoint);
      const csrfToken = extractAndSaveCsrfToken(response);
      if (csrfToken) {
        logger.info(`通过 GET 请求获取到新的 CSRF token: ${endpoint}`);
        return csrfToken;
      }
    } catch (error) {
      // 即使请求失败，响应头中也可能有 CSRF token
      const csrfToken = extractAndSaveCsrfToken(error);
      if (csrfToken) {
        logger.info(`从错误响应中获取到 CSRF token: ${endpoint}`);
        return csrfToken;
      }
      // 如果错误是 401，可能是认证问题，不应该继续
      if (error.response?.status === 401) {
        throw error;
      }
      continue;
    }
  }

  return null;
};

