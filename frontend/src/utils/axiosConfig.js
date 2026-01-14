/**
 * Axios 配置模块
 * 配置请求/响应拦截器、CSRF处理、超时设置等
 */
import axios from 'axios';
import { ElMessage } from 'element-plus';
import { logger } from './logger';
import { clearAuthData } from '../store';
import router from '../router';
import {
  getCsrfToken,
  saveCsrfToken,
  extractAndSaveCsrfToken,
  getCsrfTokenFromResponse,
  fetchCsrfTokenFromEndpoints
} from './csrfToken';

/**
 * 配置 Axios 请求拦截器
 */
export const setupRequestInterceptor = () => {
  axios.interceptors.request.use(
    (config) => {
      // 认证 token 现在由浏览器通过 HttpOnly Cookie 自动处理
      // 不再需要手动从 sessionStorage 提取并添加到 Header

      // 添加CSRF令牌（如果存在）
      const csrfToken = getCsrfToken();
      if (csrfToken) {
        config.headers['X-CSRF-Token'] = csrfToken;
      } else {
        // CSRF令牌缺失（对于非GET请求，这是严重问题）
        // 但登录接口不需要CSRF令牌（后端会跳过检查）
        const method = config.method?.toUpperCase();
        const url = config.url || '';
        const isLoginEndpoint = url.includes('/auth/login') || url.includes('/auth/logout');

        if (method && !['GET', 'HEAD', 'OPTIONS'].includes(method) && !isLoginEndpoint) {
          logger.error(`[CSRF] CSRF令牌缺失: ${method} ${config.url} - 请求将被拒绝`);
        }
      }
      
      // 设置合理的超时时间（根据不同的请求类型和设备类型调整）
      if (!config.timeout) {
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

        // 文件上传使用更长的超时时间
        if (config.method === 'post' && config.data instanceof FormData) {
          config.timeout = isMobile ? 60000 : 30000; // 移动端60秒，桌面端30秒
        } else {
          // 普通请求：移动端使用更长的超时时间
          const isAdDataRequest = config.url && (
            config.url.includes('/ad-data/') &&
            !config.url.includes('/export')
          );
          const isDataListRequest = config.url && (
            config.url.includes('/dashboard/') ||
            config.url.includes('/clients-with-data') ||
            config.url.includes('/products-with-data')
          );
          if (isAdDataRequest) {
            config.timeout = isMobile ? 60000 : 45000;
          } else if (isDataListRequest) {
            config.timeout = isMobile ? 30000 : 20000;
          } else {
            config.timeout = isMobile ? 30000 : 15000;
          }
        }
      }
      return config;
    },
    (error) => {
      return Promise.reject(error);
    }
  );
};

/**
 * 处理 CSRF token 错误并自动重试
 */
const handleCsrfError = async (error) => {
  const errorData = error.response?.data;
  const errorDetail = (errorData && typeof errorData === 'object' && !(errorData instanceof Blob))
    ? (errorData.detail || errorData.message || '')
    : '';

  // 检查是否是CSRF相关错误
  if (errorDetail && (errorDetail.includes('CSRF') || errorDetail.includes('csrf') || errorDetail.includes('令牌'))) {
    const originalRequest = error.config;

    // 检查是否已经重试过（避免无限重试）
    if (!originalRequest._retry) {
      originalRequest._retry = true;

      // 优先使用响应头中的CSRF token（如果存在）
      const csrfTokenFromHeader = getCsrfTokenFromResponse(error);
      
      if (csrfTokenFromHeader) {
        saveCsrfToken(csrfTokenFromHeader);
        originalRequest.headers = originalRequest.headers || {};
        originalRequest.headers['X-CSRF-Token'] = csrfTokenFromHeader;
        logger.info('从响应头获取到新的CSRF token，自动重试请求');
        try {
          const retryResponse = await axios(originalRequest);
          originalRequest._retrySuccess = true;
          return retryResponse;
        } catch (retryError) {
          logger.warning('使用响应头中的CSRF token重试失败:', retryError);
        }
      }

      // 如果响应头中没有token，尝试通过GET请求获取新的CSRF token
      try {
        const newCsrfToken = await fetchCsrfTokenFromEndpoints();
        if (newCsrfToken) {
          originalRequest.headers = originalRequest.headers || {};
          originalRequest.headers['X-CSRF-Token'] = newCsrfToken;
          logger.info('通过GET请求获取到新的CSRF token，自动重试请求');
          const retryResponse = await axios(originalRequest);
          originalRequest._retrySuccess = true;
          return retryResponse;
        }
      } catch (e) {
        logger.warning('自动获取CSRF token失败，将显示错误信息');
      }
    }

    // 如果自动重试失败，显示友好的错误信息
    if (!originalRequest._retrySuccess) {
      ElMessage.warning('CSRF令牌已过期，请刷新页面后重试');
    }

    return Promise.reject(error);
  }
  return null;
};

/**
 * 配置 Axios 响应拦截器
 */
export const setupResponseInterceptor = () => {
  axios.interceptors.response.use(
    (response) => {
      // 从响应头中获取CSRF令牌并存储
      extractAndSaveCsrfToken(response);
      return response;
    },
    async (error) => {
      // 即使请求失败，也尝试从响应头中获取CSRF令牌
      extractAndSaveCsrfToken(error);

      // 处理403 CSRF令牌错误
      if (error.response && error.response.status === 403) {
        const retryResponse = await handleCsrfError(error);
        if (retryResponse) {
          return retryResponse;
        }
      }

      // 处理401未授权错误
      if (error.response && error.response.status === 401) {
        const requestUrl = error.config?.url || '';
        const isLoginRequest = requestUrl.includes('/auth/login');

        if (isLoginRequest) {
          return Promise.reject(error);
        }

        const errorData = error.response.data;
        const errorDetail = (errorData && typeof errorData === 'object' && !(errorData instanceof Blob))
          ? (errorData.detail || errorData.message || '登录已过期，请重新登录')
          : '登录已过期，请重新登录';
        
        clearAuthData();
        error._handled = true;
        
        if (window.location.pathname !== '/login') {
          const friendlyMessage = errorDetail === 'Not authenticated' || errorDetail.includes('Not authenticated')
            ? '登录已过期，请重新登录'
            : errorDetail;
          ElMessage.error(friendlyMessage);
          try {
            router.push('/login').catch(() => {
              window.location.href = '/login';
            });
          } catch (e) {
            window.location.href = '/login';
          }
        }
      } else if (error.response && error.response.status === 403) {
        // 403 Forbidden错误：可能是CSRF令牌问题或其他权限问题
        const errorData = error.response.data;
        const errorDetail = (errorData && typeof errorData === 'object' && !(errorData instanceof Blob))
          ? (errorData.detail || errorData.message || '请求被拒绝')
          : '请求被拒绝';

        if (errorDetail.includes('CSRF') || errorDetail.includes('csrf') || errorDetail.includes('令牌')) {
          sessionStorage.removeItem('csrf_token');
          const retryResponse = await handleCsrfError(error);
          if (retryResponse) {
            return retryResponse;
          }
          error._handled = true;
        } else {
          ElMessage.error(errorDetail);
          error._handled = true;
        }
      } else if (error.response && error.response.status === 429) {
        // 429限流错误
        const errorData = error.response.data;
        const errorDetail = (errorData && typeof errorData === 'object' && !(errorData instanceof Blob))
          ? (errorData.detail || '请求过于频繁，请稍后再试')
          : '请求过于频繁，请稍后再试';
        ElMessage.error(errorDetail);
        error._handled = true;
      } else if (error.response && error.response.status >= 400 && error.response.status < 500) {
        // 4xx 客户端错误
        const status = error.response.status;
        const errorData = error.response.data;
        let errorDetail = (errorData && typeof errorData === 'object' && !(errorData instanceof Blob))
          ? (errorData.detail || errorData.message || '请求失败，请检查输入')
          : '请求失败，请检查输入';

        if (status === 403 && (!errorData || errorData instanceof Blob || (!errorData.detail && !errorData.message))) {
          errorDetail = '禁止登录，请联系管理员';
        }

        if (!error._handled) {
          ElMessage.error(errorDetail);
          error._handled = true;
        }
      } else if (error.response && error.response.status >= 500) {
        // 5xx 服务器错误
        if (!error._handled) {
          ElMessage.error('服务器错误，请稍后重试');
          error._handled = true;
        }
      } else if (!error._handled && !error.response) {
        // 网络错误或其他错误（无响应）
        if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
          const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
          const errorMsg = isMobile
            ? '网络连接超时，请检查网络连接或稍后重试'
            : '请求超时，请检查网络连接';
          ElMessage.error(errorMsg);
        } else {
          ElMessage.error('网络连接失败，请检查网络连接');
        }
        error._handled = true;
      } else if (!error._handled) {
        // 其他未处理的错误
        const errorData = error.response?.data;
        const errorDetail = (errorData && typeof errorData === 'object' && !(errorData instanceof Blob))
          ? (errorData.detail || errorData.message || '请求失败，请稍后重试')
          : '请求失败，请稍后重试';
        ElMessage.error(errorDetail);
        error._handled = true;
      }
      return Promise.reject(error);
    }
  );
};

/**
 * 初始化 Axios 配置
 */
export const initAxiosConfig = () => {
  axios.defaults.withCredentials = true;
  setupRequestInterceptor();
  setupResponseInterceptor();
};

