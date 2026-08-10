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
// 防抖标记，避免多个标签页同时刷新令牌
let isRefreshingToken = false;
// 令牌刷新锁（使用localStorage实现跨标签页锁）
const TOKEN_REFRESH_LOCK_KEY = 'csrf_token_refresh_lock';
const TOKEN_REFRESH_LOCK_TIMEOUT = 5000; // 5秒锁超时

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
      // 更新令牌时间戳
      localStorage.setItem('csrf_token_updated_at', Date.now().toString());
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
    const oldSession = sessionStorage.getItem('csrf_token');
    const oldLocal = localStorage.getItem('csrf_token');
    if (oldSession !== token || oldLocal !== token) {
      sessionStorage.setItem('csrf_token', token);
      if (!isUpdatingFromStorage) {
        localStorage.setItem('csrf_token', token);
        localStorage.setItem('csrf_token_updated_at', String(Date.now()));
      }
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
 * 检查CSRF令牌是否需要刷新
 * 如果令牌不存在或已过期，返回true
 * @returns {boolean} 是否需要刷新令牌
 */
export const shouldRefreshCsrfToken = () => {
  const token = getCsrfToken();

  // 如果没有令牌，需要刷新
  if (!token) {
    logger.debug('CSRF令牌不存在，需要刷新');
    return true;
  }

  // 检查令牌的最后更新时间（存储在localStorage中）
  const lastUpdateTime = localStorage.getItem('csrf_token_updated_at');
  if (!lastUpdateTime) {
    logger.debug('CSRF令牌没有更新时间，需要刷新');
    return true;
  }

  // 计算令牌已存在的时间（毫秒）
  const now = Date.now();
  const tokenAge = now - parseInt(lastUpdateTime);

  // 如果令牌已存在超过50分钟（接近1小时过期时间），建议刷新
  const TOKEN_REFRESH_THRESHOLD = 50 * 60 * 1000; // 50分钟
  if (tokenAge > TOKEN_REFRESH_THRESHOLD) {
    logger.debug(`CSRF令牌已存在 ${Math.floor(tokenAge / 60000)} 分钟，建议刷新`);
    return true;
  }

  return false;
};

/**
 * 初始化页面加载时的CSRF令牌检查
 * 如果令牌需要刷新，自动刷新令牌
 */
export const initPageLoadCsrfCheck = () => {
  // 检查是否需要刷新令牌
  if (shouldRefreshCsrfToken()) {
    logger.info('页面加载时检测到CSRF令牌需要刷新，正在获取新令牌...');

    // 异步获取新令牌（不阻塞页面加载）
    fetchCsrfTokenFromEndpoints().then((newToken) => {
      if (newToken) {
        logger.info('页面加载时成功刷新了CSRF令牌');
        // 更新令牌时间戳
        localStorage.setItem('csrf_token_updated_at', Date.now().toString());
      }
    }).catch((error) => {
      logger.debug('页面加载时刷新CSRF令牌失败:', error);
      // 失败不影响页面加载，静默处理
    });
  } else {
    logger.debug('页面加载时CSRF令牌有效，无需刷新');
  }
};

/**
 * 初始化页面可见性变化时的CSRF令牌刷新机制
 * 当用户切换回标签页时，自动刷新CSRF令牌
 * 改进：减少刷新频率，避免多个标签页同时刷新
 */
export const initPageVisibilityRefresh = () => {
  let lastRefreshTime = 0;
  const REFRESH_INTERVAL = 10 * 60 * 1000; // 10分钟（从5分钟增加到10分钟）

  document.addEventListener('visibilitychange', async () => {
    // 只有当页面变为可见时才刷新令牌
    if (document.visibilityState === 'visible') {
      const now = Date.now();
      // 距离上次刷新超过10分钟才刷新，避免频繁请求
      if (now - lastRefreshTime > REFRESH_INTERVAL) {
        try {
          // 检查令牌是否需要刷新（避免不必要的请求）
          if (!shouldRefreshCsrfToken()) {
            logger.debug('页面变为可见，但CSRF令牌仍然有效，无需刷新');
            return;
          }

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
 * 清除本地 CSRF 令牌（退出登录 / 角色切换时调用）
 * 避免管理员会话残留的探测请求在客户登录后触发「需要管理员权限」提示
 */
export const clearCsrfToken = () => {
  try {
    sessionStorage.removeItem('csrf_token');
    localStorage.removeItem('csrf_token');
    localStorage.removeItem('csrf_token_updated_at');
  } catch (e) {
    logger.warn('清除 CSRF 令牌失败:', e);
  }
};

/**
 * CSRF 探测用 GET 端点。
 * - 须对未登录 / 任意登录角色可用，禁止仅管理员接口
 * - 优先 /health：未登录刷新登录页时不再因 /users/me 刷 401 控制台噪声
 */
const CSRF_PROBE_ENDPOINTS = [
  '/api/v1/health',
  '/api/v1/users/me',
  '/api/v1/dashboard/stats',
  // 勿加入仅管理员接口（如 /users/stats）；角色切换后探测失败会误报「需要管理员权限」
];

/**
 * 当前是否明显处于「未登录浏览登录页」：此时只需公开端点即可换 CSRF。
 */
function shouldUsePublicCsrfProbeOnly() {
  try {
    const path = window.location?.pathname || '';
    if (path !== '/login' && path !== '/') {
      return false;
    }
    // 本地无有效登录痕迹时，避免探测需登录的接口
    const userInfo = sessionStorage.getItem('userInfo');
    return !userInfo;
  } catch {
    return true;
  }
}

/**
 * 尝试从多个端点获取 CSRF token
 * 改进：添加令牌刷新锁，避免多个标签页同时刷新
 * @param {Array<string>} endpoints - 要尝试的端点列表（可选，默认使用常用端点）
 * @returns {Promise<string|null>} CSRF token，如果获取失败则返回 null
 */
export const fetchCsrfTokenFromEndpoints = async (endpoints = null) => {
  // 检查是否正在刷新令牌（防抖）
  if (isRefreshingToken) {
    logger.debug('CSRF令牌正在刷新中，跳过重复请求');
    return getCsrfToken();
  }

  // 尝试获取刷新锁
  const lockAcquired = acquireTokenRefreshLock();
  if (!lockAcquired) {
    logger.debug('其他标签页正在刷新CSRF令牌，等待刷新完成');
    // 等待一小段时间，然后检查是否有新令牌
    await new Promise(resolve => setTimeout(resolve, 200));
    return getCsrfToken();
  }

  isRefreshingToken = true;

  try {
    const endpointsToTry = endpoints
      || (shouldUsePublicCsrfProbeOnly()
        ? ['/api/v1/health']
        : CSRF_PROBE_ENDPOINTS);

    for (const endpoint of endpointsToTry) {
      try {
        // skipErrorMessage：探测失败（含历史误配的管理员接口）不弹权限错误
        const response = await axios.get(endpoint, {
          skipErrorMessage: true,
          skipRequestCache: true,
        });
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
        // 401：未登录探测鉴权接口时继续下一个端点（勿中断整条探测链）
        if (error.response?.status === 401) {
          continue;
        }
        continue;
      }
    }

    return null;
  } finally {
    isRefreshingToken = false;
    releaseTokenRefreshLock();
  }
};

/**
 * 尝试获取令牌刷新锁
 * @returns {boolean} 是否成功获取锁
 */
function acquireTokenRefreshLock() {
  try {
    const lockValue = Date.now().toString();
    const existingLock = localStorage.getItem(TOKEN_REFRESH_LOCK_KEY);

    // 检查锁是否已过期
    if (existingLock) {
      const lockTime = parseInt(existingLock);
      if (Date.now() - lockTime > TOKEN_REFRESH_LOCK_TIMEOUT) {
        // 锁已过期，可以获取
        localStorage.setItem(TOKEN_REFRESH_LOCK_KEY, lockValue);
        return true;
      }
      // 锁仍然有效，无法获取
      return false;
    }

    // 没有锁，可以获取
    localStorage.setItem(TOKEN_REFRESH_LOCK_KEY, lockValue);
    return true;
  } catch (error) {
    logger.debug('获取令牌刷新锁失败:', error);
    return false;
  }
}

/**
 * 释放令牌刷新锁
 */
function releaseTokenRefreshLock() {
  try {
    localStorage.removeItem(TOKEN_REFRESH_LOCK_KEY);
  } catch (error) {
    logger.debug('释放令牌刷新锁失败:', error);
  }
}

