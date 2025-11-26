// Vue核心
import { createApp, nextTick } from 'vue';
import App from './App.vue';

// 第三方库
import axios from 'axios';
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import zhCn from 'element-plus/dist/locale/zh-cn.mjs';
import * as ElementPlusIconsVue from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

// 本地导入
import './style.css';
import './styles/mobile.css'; // 移动端优化样式
import pinia from './store';
import { useAuthStore, validateAuthData, clearAuthData } from './store';
import router from './router/index.js';
import { initTimezone } from './utils/dateFormat';
import { logger } from './utils/logger';

// 创建Vue应用
const app = createApp(App);

// 注册Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}

// 配置Axios拦截器
axios.interceptors.request.use(
  (config) => {
    // 添加认证token
    const token = sessionStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // 添加CSRF令牌（如果存在）
    const csrfToken = sessionStorage.getItem('csrf_token');
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
    // 移动端网络较慢，需要更长的超时时间
    if (!config.timeout) {
      // 检测是否为移动设备
      const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
      
      // 文件上传使用更长的超时时间
      if (config.method === 'post' && config.data instanceof FormData) {
        config.timeout = isMobile ? 60000 : 30000; // 移动端60秒，桌面端30秒
      } else {
        // 普通请求：移动端使用更长的超时时间
        // 对于广告数据查询请求，使用更长的超时时间（因为涉及复杂查询和大量数据）
        const isAdDataRequest = config.url && (
          config.url.includes('/ad-data/') && 
          !config.url.includes('/export') // 导出请求使用默认超时
        );
        const isDataListRequest = config.url && (
          config.url.includes('/dashboard/') ||
          config.url.includes('/clients-with-data') ||
          config.url.includes('/products-with-data')
        );
        if (isAdDataRequest) {
          // 广告数据查询：使用更长的超时时间（移动端60秒，桌面端45秒）
          // 这些查询可能涉及复杂的JOIN和聚合操作
          config.timeout = isMobile ? 60000 : 45000;
        } else if (isDataListRequest) {
          // 其他数据列表请求：使用中等超时时间
          config.timeout = isMobile ? 30000 : 20000; // 移动端30秒，桌面端20秒
        } else {
          config.timeout = isMobile ? 30000 : 15000; // 其他请求：移动端30秒，桌面端15秒
        }
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
axios.interceptors.response.use(
  (response) => {
    // 从响应头中获取CSRF令牌并存储
    const csrfToken = response.headers['x-csrf-token'] || response.headers['X-CSRF-Token'];
    if (csrfToken) {
      sessionStorage.setItem('csrf_token', csrfToken);
    }
    return response;
  },
  async (error) => {
    // 即使请求失败，也尝试从响应头中获取CSRF令牌
    if (error.response?.headers) {
      const csrfToken = error.response.headers['x-csrf-token'] || error.response.headers['X-CSRF-Token'];
      if (csrfToken) {
        sessionStorage.setItem('csrf_token', csrfToken);
      }
    }
    
    // 处理403 CSRF令牌错误（服务器重启后token可能失效）
    if (error.response && error.response.status === 403) {
      const errorData = error.response.data;
      const errorDetail = (errorData && typeof errorData === 'object' && !(errorData instanceof Blob))
        ? (errorData.detail || errorData.message || '')
        : '';
      
      // 检查是否是CSRF相关错误
      if (errorDetail && (errorDetail.includes('CSRF') || errorDetail.includes('csrf') || errorDetail.includes('令牌'))) {
        // 清除旧的CSRF token
        sessionStorage.removeItem('csrf_token');
        
        // 尝试自动获取新的CSRF token并重试请求
        const originalRequest = error.config;
        
        // 检查是否已经重试过（避免无限重试）
        if (!originalRequest._retry) {
          originalRequest._retry = true;
          
          try {
            // 发送一个GET请求获取新的CSRF token
            // axios已在文件顶部导入，直接使用
            const token = sessionStorage.getItem('token');
            if (token) {
              // 尝试多个轻量级的GET请求端点
              const endpoints = [
                '/api/v1/users/stats',
                '/api/v1/dashboard/stats',
                '/api/v1/products/?page_size=1'
              ];
              
              for (const endpoint of endpoints) {
                try {
                  const response = await axios.get(endpoint, {
                    headers: {
                      'Authorization': `Bearer ${token}`
                    }
                  });
                  
                  // 从响应头获取新的CSRF token
                  const newCsrfToken = response.headers['x-csrf-token'] || response.headers['X-CSRF-Token'];
                  if (newCsrfToken) {
                    sessionStorage.setItem('csrf_token', newCsrfToken);
                    
                    // 更新原始请求的CSRF token并重试
                    originalRequest.headers['X-CSRF-Token'] = newCsrfToken;
                    return axios(originalRequest);
                  }
                } catch (e) {
                  // 继续尝试下一个端点
                  continue;
                }
              }
            }
          } catch (e) {
            // 获取新token失败，继续原有的错误处理流程
            logger.warning('自动获取CSRF token失败，将显示错误信息');
          }
        }
        
        // 如果自动重试失败，显示友好的错误信息
        if (!originalRequest._retrySuccess) {
          ElMessage.warning('CSRF令牌已过期，请刷新页面后重试');
        }
        
        return Promise.reject(error);
      }
    }
    
    // 处理401未授权错误
    if (error.response && error.response.status === 401) {
      // 检查是否是登录请求失败（登录请求返回401是正常的，不应该触发认证清除和跳转）
      const requestUrl = error.config?.url || '';
      const isLoginRequest = requestUrl.includes('/auth/login');
      
      // 如果是登录请求失败，不处理401错误，让登录组件自己处理
      if (isLoginRequest) {
        // 登录失败是正常的业务错误，不需要清除认证信息或跳转
        // 错误消息会由登录组件显示
        return Promise.reject(error);
      }
      
      // 检查是否是 blob 响应，如果是则使用默认消息
      const errorData = error.response.data;
      const errorDetail = (errorData && typeof errorData === 'object' && !(errorData instanceof Blob))
        ? (errorData.detail || errorData.message || '登录已过期，请重新登录')
        : '登录已过期，请重新登录';
      // 统一清除认证信息
      clearAuthData();
      // 标记错误已处理，避免重复显示
      error._handled = true;
      // 只在当前页面不是登录页时才显示错误信息和跳转
      if (window.location.pathname !== '/login') {
        // 如果错误信息是 "Not authenticated"，使用更友好的提示
        const friendlyMessage = errorDetail === 'Not authenticated' || errorDetail.includes('Not authenticated')
          ? '登录已过期，请重新登录'
          : errorDetail;
        ElMessage.error(friendlyMessage);
        // 立即跳转到登录页，使用window.location确保立即生效
        // 如果路由已初始化，优先使用路由跳转
        try {
          router.push('/login').catch(() => {
            window.location.href = '/login';
          });
        } catch (e) {
          // 如果路由未初始化或跳转失败，直接使用页面跳转
          window.location.href = '/login';
        }
      }
    } else if (error.response && error.response.status === 403) {
      // 403 Forbidden错误：可能是CSRF令牌问题
      // 检查是否是 blob 响应，如果是则使用默认消息
      const errorData = error.response.data;
      const errorDetail = (errorData && typeof errorData === 'object' && !(errorData instanceof Blob))
        ? (errorData.detail || errorData.message || '请求被拒绝')
        : '请求被拒绝';
      
      // 检查是否是CSRF相关错误
      if (errorDetail.includes('CSRF') || errorDetail.includes('csrf') || errorDetail.includes('令牌')) {
        // 清除旧的CSRF令牌
        sessionStorage.removeItem('csrf_token');
        
        // 尝试自动获取新的CSRF token并重试请求（仅对非GET请求）
        const originalRequest = error.config;
        const isGetRequest = !originalRequest || !originalRequest.method || ['get', 'GET'].includes(originalRequest.method);
        
        // 对于非GET请求，尝试自动重试
        if (!isGetRequest && originalRequest && !originalRequest._csrfRetry) {
          originalRequest._csrfRetry = true;
          
          try {
            // 发送一个GET请求获取新的CSRF token
            const token = sessionStorage.getItem('token');
            if (token) {
              // 尝试多个轻量级的GET请求端点
              const endpoints = [
                '/api/v1/users/stats',
                '/api/v1/dashboard/stats',
                '/api/v1/products/?page_size=1'
              ];
              
              for (const endpoint of endpoints) {
                try {
                  const response = await axios.get(endpoint, {
                    headers: {
                      'Authorization': `Bearer ${token}`
                    }
                  });
                  
                  // 从响应头获取新的CSRF token
                  const newCsrfToken = response.headers['x-csrf-token'] || response.headers['X-CSRF-Token'];
                  if (newCsrfToken) {
                    sessionStorage.setItem('csrf_token', newCsrfToken);
                    
                    // 更新原始请求的CSRF token并重试
                    originalRequest.headers = originalRequest.headers || {};
                    originalRequest.headers['X-CSRF-Token'] = newCsrfToken;
                    
                    // 重试原始请求
                    logger.info('CSRF token已更新，自动重试请求');
                    return axios(originalRequest);
                  }
                } catch (e) {
                  // 继续尝试下一个端点
                  continue;
                }
              }
            }
          } catch (e) {
            // 获取新token失败，继续原有的错误处理流程
            logger.warning('自动获取CSRF token失败:', e);
          }
        }
        
        // 如果自动重试失败或未执行，显示友好的错误信息
        if (isGetRequest || !originalRequest || !originalRequest._csrfRetrySuccess) {
          ElMessage.warning('CSRF令牌已过期，请刷新页面后重试');
        }
        
        // 标记错误已处理
        error._handled = true;
      } else {
        // 其他403错误，显示具体错误信息
        ElMessage.error(errorDetail);
        error._handled = true;
      }
    } else if (error.response && error.response.status === 429) {
      // 429限流错误：只显示一次，不重复显示
      // 检查是否是 blob 响应，如果是则使用默认消息
      const errorData = error.response.data;
      const errorDetail = (errorData && typeof errorData === 'object' && !(errorData instanceof Blob))
        ? (errorData.detail || '请求过于频繁，请稍后再试')
        : '请求过于频繁，请稍后再试';
      ElMessage.error(errorDetail);
      // 标记错误已处理，避免API函数再次显示
      error._handled = true;
    } else if (error.response && error.response.status >= 400 && error.response.status < 500) {
      // 4xx 客户端错误：显示后端返回的错误信息
      // 优先使用 detail，其次使用 message
      const status = error.response.status;
      // 检查是否是 blob 响应，如果是则使用默认消息
      const errorData = error.response.data;
      let errorDetail = (errorData && typeof errorData === 'object' && !(errorData instanceof Blob))
        ? (errorData.detail || errorData.message || '请求失败，请检查输入')
        : '请求失败，请检查输入';
      
      // 对于 403 错误（如客户被禁用），如果没有具体错误信息，使用通用提示
      if (status === 403 && (!errorData || errorData instanceof Blob || (!errorData.detail && !errorData.message))) {
        errorDetail = '禁止登录，请联系管理员';
      }
      
      // 只有未被标记为已处理的错误才显示
      if (!error._handled) {
        ElMessage.error(errorDetail);
        error._handled = true;  // 标记为已处理，避免重复显示
      }
    } else if (error.response && error.response.status >= 500) {
      // 5xx 服务器错误：显示通用错误信息
      if (!error._handled) {
        ElMessage.error('服务器错误，请稍后重试');
        error._handled = true;
      }
    } else if (!error._handled && !error.response) {
      // 网络错误或其他错误（无响应）
      // 检查是否为超时错误
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
      // 检查是否是 blob 响应，如果是则使用默认消息
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

// 全局注册Axios
app.config.globalProperties.$axios = axios;

// ====== 全局错误捕获 ======
// 捕获JavaScript运行时错误
window.addEventListener('error', (event) => {
  // 忽略 Element Plus 的 ElOnlyChild 错误
  const errorMessage = event?.message || event?.error?.message || '';
  const errorFilename = event?.filename || '';
  
  // 忽略浏览器扩展相关的错误（通常由广告拦截器、开发者工具扩展等引起）
  if (typeof errorMessage === 'string' && (
    errorMessage.includes('message channel closed') ||
    errorMessage.includes('asynchronous response') ||
    errorMessage.includes('listener indicated an asynchronous response')
  )) {
    event.preventDefault(); // 阻止默认的错误处理
    return;
  }
  
  if (typeof errorMessage === 'string' && errorMessage.includes('ElOnlyChild')) {
    return;
  }
  
  // 忽略 ResizeObserver 错误（这是浏览器的一个无害警告，通常由 UI 库触发）
  if (typeof errorMessage === 'string' && errorMessage.includes('ResizeObserver loop completed with undelivered notifications')) {
    return;
  }
  
  // 忽略 inspector.js 中关于 responseText 的错误（这是浏览器开发者工具的问题，不是代码问题）
  // 检查文件名、错误消息和错误名称
  const errorName = event?.error?.name || '';
  const isInspectorFile = typeof errorFilename === 'string' && errorFilename.includes('inspector.js');
  const isResponseTextError = typeof errorMessage === 'string' && (
    (errorMessage.includes('responseText') && errorMessage.includes('responseType')) ||
    errorMessage.includes('Failed to read') && errorMessage.includes('responseText') ||
    (errorMessage.includes('InvalidStateError') && errorMessage.includes('responseText')) ||
    errorMessage.includes('The value is only accessible if the object\'s \'responseType\'')
  );
  const isInvalidStateError = errorName === 'InvalidStateError' || errorMessage.includes('InvalidStateError');
  
  if (isInspectorFile || (isResponseTextError && isInvalidStateError)) {
    // 阻止错误传播和记录
    event.preventDefault();
    return;
  }
  
  // 记录前端运行错误
  try {
    const error = event.error || new Error(event.message);
    const errorType = error.name || 'Error';
    const errorMsg = error.message || event.message || '未知错误';
    const errorStack = error.stack || '';
    const errorUrl = event.filename || window.location.href;
    
    // 异步记录错误，不阻塞页面
    recordFrontendError({
      error_type: errorType,
      error_message: errorMsg,
      error_stack: errorStack,
      error_url: errorUrl,
      user_agent: navigator.userAgent
    }).catch(() => {
      // 静默失败，不影响用户体验
    });
  } catch (e) {
    // 记录错误失败时静默处理
    logger.error('记录前端错误失败:', e);
  }
});

// 捕获未处理的Promise拒绝
window.addEventListener('unhandledrejection', (event) => {
  // 忽略 inspector.js 中关于 responseText 的错误（这是浏览器开发者工具的问题，不是代码问题）
  const errorMessage = event?.reason?.message || event?.reason?.toString() || '';
  const errorStack = event?.reason?.stack || '';
  const errorName = event?.reason?.name || '';
  
  // 检查错误堆栈中是否包含 inspector.js
  const isInspectorError = typeof errorStack === 'string' && errorStack.includes('inspector.js');
  
  // 检查是否是 responseText 相关的 InvalidStateError
  const isResponseTextError = typeof errorMessage === 'string' && (
    (errorMessage.includes('responseText') && errorMessage.includes('responseType')) ||
    errorMessage.includes('Failed to read') && errorMessage.includes('responseText') ||
    (errorMessage.includes('InvalidStateError') && errorMessage.includes('responseText')) ||
    errorMessage.includes('The value is only accessible if the object\'s \'responseType\'')
  );
  const isInvalidStateError = errorName === 'InvalidStateError' || 
    (typeof errorMessage === 'string' && errorMessage.includes('InvalidStateError'));
  
  if (isInspectorError || (isResponseTextError && isInvalidStateError)) {
    event.preventDefault(); // 阻止默认的错误处理
    return;
  }
  
  // 忽略浏览器扩展相关的错误（通常由广告拦截器、开发者工具扩展等引起）
  if (typeof errorMessage === 'string' && (
    errorMessage.includes('message channel closed') ||
    errorMessage.includes('asynchronous response') ||
    errorMessage.includes('listener indicated an asynchronous response')
  )) {
    event.preventDefault(); // 阻止默认的错误处理
    return;
  }
  
  // 忽略 Element Plus 的 ElOnlyChild 错误
  if (typeof errorMessage === 'string' && errorMessage.includes('ElOnlyChild')) {
    return;
  }
  
  // 忽略 ResizeObserver 错误（这是浏览器的一个无害警告，通常由 UI 库触发）
  if (typeof errorMessage === 'string' && errorMessage.includes('ResizeObserver loop completed with undelivered notifications')) {
    return;
  }
  
  // 记录前端运行错误
  try {
    const error = event.reason || new Error('Unhandled Promise Rejection');
    const errorType = error.name || 'UnhandledRejection';
    const errorMsg = error.message || String(event.reason) || '未处理的Promise拒绝';
    const errorStack = error.stack || '';
    const errorUrl = window.location.href;
    
    // 异步记录错误，不阻塞页面
    recordFrontendError({
      error_type: errorType,
      error_message: errorMsg,
      error_stack: errorStack,
      error_url: errorUrl,
      user_agent: navigator.userAgent
    }).catch(() => {
      // 静默失败，不影响用户体验
    });
  } catch (e) {
    // 记录错误失败时静默处理
    logger.error('记录前端错误失败:', e);
  }
});

// 记录前端错误的函数
async function recordFrontendError(errorInfo) {
  try {
    // 检查是否有token（可选，未登录用户也可以记录错误）
    const token = sessionStorage.getItem('token');
    
    // 构建请求参数
    const params = new URLSearchParams({
      error_type: errorInfo.error_type || 'JavaScriptError',
      error_message: errorInfo.error_message || '未知错误',
      ...(errorInfo.error_stack && { error_stack: errorInfo.error_stack }),
      ...(errorInfo.error_url && { error_url: errorInfo.error_url }),
      ...(errorInfo.user_agent && { user_agent: errorInfo.user_agent })
    });
    
    // 发送错误日志（使用POST请求，避免URL过长）
    await axios.post(`/api/v1/audit-logs/client-error?${params.toString()}`, {}, {
      timeout: 5000, // 5秒超时，避免阻塞
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    });
  } catch (error) {
    // 静默失败，不影响用户体验
    // 仅在开发环境记录调试信息
    if (import.meta.env.DEV) {
      // 使用动态导入避免在生产环境加载 logger
      const { logger } = await import('./utils/logger');
      logger.debug('记录前端错误失败:', error);
    }
  }
}

// 使用插件
app.use(pinia);

// 初始化认证状态（延迟执行，不阻塞登录页渲染）
// 只在非登录页时执行认证检查
const initializeAuth = () => {
  // 如果当前是登录页，跳过认证检查
  if (window.location.pathname === '/login' || window.location.pathname === '/') {
    return;
  }
  
  // 先验证认证数据完整性，再恢复状态
  validateAuthData();
  const authStore = useAuthStore();
  authStore.checkAuth();
};

// 使用路由
app.use(router);
app.use(ElementPlus, {
  locale: zhCn,
});

// 初始化时区配置（延迟执行，不阻塞应用启动）
// 只在已登录时初始化时区配置
const initializeTimezone = () => {
  const token = sessionStorage.getItem('token');
  if (token && window.location.pathname !== '/login' && window.location.pathname !== '/') {
    initTimezone().catch(() => {
      // 静默处理错误，使用默认值
    });
  }
};

// 挂载应用
app.mount('#app');

// 在应用挂载后，根据当前路由决定是否初始化认证和时区
// 使用 nextTick 确保路由已初始化
nextTick(() => {
  // 延迟初始化，不阻塞首次渲染
  setTimeout(() => {
    initializeAuth();
    initializeTimezone();
  }, 0);
});
