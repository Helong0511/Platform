// ====== 最早期的错误处理（在所有导入之前） ======
// 捕获未处理的 Promise rejection（浏览器扩展相关）
if (typeof window !== 'undefined') {
  window.addEventListener('unhandledrejection', (event) => {
    const errorMessage = event?.reason?.message || event?.reason?.toString() || '';
    const errorString = String(errorMessage).toLowerCase();
    
    // 检查是否是浏览器扩展相关的错误
    if (errorString.includes('message channel closed') ||
        errorString.includes('message port closed') ||
        errorString.includes('asynchronous response') ||
        errorString.includes('listener indicated an asynchronous response') ||
        errorString.includes('message channel') ||
        errorString.includes('channel closed') ||
        errorString.includes('port closed') ||
        errorString.includes('a listener indicated an asynchronous response') ||
        errorString.includes('but the message channel closed') ||
        errorString.includes('before a response was received') ||
        errorString.includes('listener indicated') ||
        errorString.includes('response by returning true') ||
        errorString.includes('extensioncontextinvalidated') ||
        errorString.includes('extension context invalidated')) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
  }, true); // 使用 capture 模式，确保优先处理
}

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
import { useViewportHeight, disableDoubleTapZoom } from './composables/useMobileTouch';
import pinia from './store';
import { useAuthStore, validateAuthData, clearAuthData } from './store';
import router from './router/index.js';
import { initTimezone } from './utils/dateFormat';
import { logger } from './utils/logger';

// ====== 早期错误过滤（在应用初始化之前） ======
// 过滤浏览器扩展相关的控制台错误
// 必须在最早阶段设置，确保捕获所有错误
const originalConsoleError = console.error;
const originalConsoleWarn = console.warn;

// 检查是否是浏览器扩展相关的错误
const isExtensionError = (message) => {
  if (!message || typeof message !== 'string') return false;
  const lowerMessage = message.toLowerCase();
  return lowerMessage.includes('message channel closed') ||
    lowerMessage.includes('message port closed') ||
    lowerMessage.includes('asynchronous response') ||
    lowerMessage.includes('listener indicated an asynchronous response') ||
    lowerMessage.includes('message channel') ||
    lowerMessage.includes('channel closed') ||
    lowerMessage.includes('port closed') ||
    lowerMessage.includes('a listener indicated an asynchronous response') ||
    lowerMessage.includes('but the message channel closed') ||
    lowerMessage.includes('before a response was received') ||
    lowerMessage.includes('listener indicated') ||
    lowerMessage.includes('response by returning true') ||
    lowerMessage.includes('extensioncontextinvalidated') ||
    lowerMessage.includes('extension context invalidated');
};

console.error = function(...args) {
  // 检查所有参数，包括错误对象
  const errorMessages = args.map(arg => {
    if (arg instanceof Error) {
      return arg.message || arg.toString();
    }
    return String(arg);
  }).join(' ');
  
  // 如果是扩展错误，静默忽略
  if (isExtensionError(errorMessages)) {
    return;
  }
  
  // 否则正常输出
  originalConsoleError.apply(console, args);
};

console.warn = function(...args) {
  // 检查所有参数
  const errorMessages = args.map(arg => {
    if (arg instanceof Error) {
      return arg.message || arg.toString();
    }
    return String(arg);
  }).join(' ');
  
  // 如果是扩展错误，静默忽略
  if (isExtensionError(errorMessages)) {
    return;
  }
  
  // 否则正常输出
  originalConsoleWarn.apply(console, args);
};

// 创建Vue应用
const app = createApp(App);

// 注册Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}

// 配置Axios
axios.defaults.withCredentials = true;
// 配置Axios拦截器
axios.interceptors.request.use(
  (config) => {
    // 认证 token 现在由浏览器通过 HttpOnly Cookie 自动处理
    // 不再需要手动从 sessionStorage 提取并添加到 Header

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
        // 尝试自动获取新的CSRF token并重试请求
        const originalRequest = error.config;

        // 检查是否已经重试过（避免无限重试）
        if (!originalRequest._retry) {
          originalRequest._retry = true;

          // 优先使用响应头中的CSRF token（如果存在）
          const csrfTokenFromHeader = error.response?.headers?.['x-csrf-token'] || error.response?.headers?.['X-CSRF-Token'];
          
          if (csrfTokenFromHeader) {
            // 响应头中已经有新的token，直接使用它重试
            sessionStorage.setItem('csrf_token', csrfTokenFromHeader);
            originalRequest.headers = originalRequest.headers || {};
            originalRequest.headers['X-CSRF-Token'] = csrfTokenFromHeader;
            logger.info('从响应头获取到新的CSRF token，自动重试请求');
            try {
              const retryResponse = await axios(originalRequest);
              originalRequest._retrySuccess = true;
              return retryResponse;
            } catch (retryError) {
              // 重试失败，继续原有的错误处理流程
              logger.warning('使用响应头中的CSRF token重试失败:', retryError);
            }
          }

          // 如果响应头中没有token，尝试通过GET请求获取新的CSRF token
          try {
            // 发送一个GET请求获取新的CSRF token
            // 系统使用 HttpOnly Cookie，axios 会自动携带认证信息，不需要手动设置 Authorization header
            // 尝试多个轻量级的GET请求端点
            const endpoints = [
              '/api/v1/users/stats',
              '/api/v1/dashboard/stats',
              '/api/v1/products/?page_size=1',
              '/api/v1/short-links/?page_size=1',
              '/api/v1/clients/?page_size=1'
            ];

            for (const endpoint of endpoints) {
              try {
                const response = await axios.get(endpoint);

                // 从响应头获取新的CSRF token
                const newCsrfToken = response.headers['x-csrf-token'] || response.headers['X-CSRF-Token'];
                if (newCsrfToken) {
                  sessionStorage.setItem('csrf_token', newCsrfToken);

                  // 更新原始请求的CSRF token并重试
                  originalRequest.headers = originalRequest.headers || {};
                  originalRequest.headers['X-CSRF-Token'] = newCsrfToken;
                  logger.info('通过GET请求获取到新的CSRF token，自动重试请求');
                  const retryResponse = await axios(originalRequest);
                  originalRequest._retrySuccess = true;
                  return retryResponse;
                }
              } catch (e) {
                // 继续尝试下一个端点
                continue;
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
            // 系统使用 HttpOnly Cookie，axios 会自动携带认证信息，不需要手动设置 Authorization header
            // 尝试多个轻量级的GET请求端点
            const endpoints = [
              '/api/v1/users/stats',
              '/api/v1/dashboard/stats',
              '/api/v1/products/?page_size=1',
              '/api/v1/short-links/?page_size=1',
              '/api/v1/clients/?page_size=1'
            ];

            for (const endpoint of endpoints) {
              try {
                const response = await axios.get(endpoint);

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
// 使用 capture 模式确保在早期阶段捕获错误
window.addEventListener('error', (event) => {
  // 忽略 Element Plus 的 ElOnlyChild 错误
  const errorMessage = event?.message || event?.error?.message || '';
  const errorFilename = event?.filename || '';
  const errorString = String(errorMessage).toLowerCase();

  // 忽略浏览器扩展相关的错误（通常由广告拦截器、开发者工具扩展等引起）
  // 包括 Edge 浏览器扩展可能引起的错误
  // 检查错误消息、错误名称和文件名
  const errorName = event?.error?.name || '';
  const errorStack = event?.error?.stack || '';
  
  // 使用统一的扩展错误检查函数
  const isExtensionErrorMsg = isExtensionError(errorMessage);
  const isExtensionFile = typeof errorFilename === 'string' && (
    errorFilename.includes('extension') ||
    errorFilename.includes('chrome-extension') ||
    errorFilename.includes('moz-extension') ||
    errorFilename.includes('safari-extension') ||
    errorFilename.includes('edge-extension') ||
    errorFilename.includes('content.js') ||
    errorFilename.includes('content-script')
  );
  const isExtensionStack = typeof errorStack === 'string' && (
    errorStack.includes('extension') ||
    errorStack.includes('chrome-extension') ||
    errorStack.includes('moz-extension') ||
    errorStack.includes('safari-extension') ||
    errorStack.includes('edge-extension')
  );
  
  if (isExtensionErrorMsg || isExtensionFile || isExtensionStack || errorName === 'ExtensionError') {
    event.preventDefault(); // 阻止默认的错误处理
    event.stopPropagation(); // 阻止事件冒泡
    event.stopImmediatePropagation(); // 阻止其他监听器处理
    return false; // 返回 false 表示已处理
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
  // errorName 已在上面声明，直接使用
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
// 使用 capture 模式确保在早期阶段捕获错误
window.addEventListener('unhandledrejection', (event) => {
  // 忽略 inspector.js 中关于 responseText 的错误（这是浏览器开发者工具的问题，不是代码问题）
  const errorMessage = event?.reason?.message || event?.reason?.toString() || '';
  const errorStack = event?.reason?.stack || '';
  const errorName = event?.reason?.name || '';
  const errorString = String(errorMessage).toLowerCase();

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
  // 包括 Edge 浏览器扩展可能引起的错误
  // 检查错误消息、错误名称和堆栈信息
  const isExtensionErrorMsg = isExtensionError(errorMessage);
  const isExtensionStack = typeof errorStack === 'string' && (
    errorStack.includes('extension') ||
    errorStack.includes('chrome-extension') ||
    errorStack.includes('moz-extension') ||
    errorStack.includes('safari-extension') ||
    errorStack.includes('edge-extension') ||
    errorStack.includes('content.js') ||
    errorStack.includes('content-script')
  );
  const isExtensionReason = event?.reason && typeof event.reason === 'object' && (
    isExtensionError(String(event.reason.message || '')) ||
    isExtensionError(String(event.reason.toString || ''))
  );
  
  if (isExtensionErrorMsg || isExtensionStack || isExtensionReason || errorName === 'ExtensionError') {
    event.preventDefault(); // 阻止默认的错误处理
    event.stopPropagation(); // 阻止事件冒泡
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
    // 系统使用 HttpOnly Cookie，axios 会自动携带认证信息，不需要手动设置 Authorization header
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
      timeout: 5000 // 5秒超时，避免阻塞
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
  if (window.location.pathname === '/login' || window.location.pathname === '/') {
    return;
  }
  
  // 使用 authStore 检查是否已登录
  const authStore = useAuthStore();
  if (authStore.isAuthenticated) {
    initTimezone().catch(() => {
      // 静默处理错误，使用默认值
    });
  }
};

// 挂载应用
app.mount('#app');

// 修复 el-select 选中值显示问题：强制更新 el-select 状态（全局函数）
const fixSelectDisplay = () => {
  const selectElements = document.querySelectorAll('.el-select');
  let fixedCount = 0;
  
  selectElements.forEach((selectEl) => {
    // 检查 placeholder 元素
    const placeholderEl = selectEl.querySelector('.el-select__placeholder');
    if (!placeholderEl) return;
    
    // 方法1: 通过 Vue 实例检查 modelValue（最可靠的方式）
    let hasVueValue = false;
    let vueInstance = null;
    let modelValue = null;
    
    try {
      // 尝试获取 Vue 实例（多种方式）
      vueInstance = selectEl.__vueParentComponent || 
                   selectEl.__vue__ || 
                   selectEl._vnode?.ctx ||
                   selectEl._vnode?.component;
      
      if (vueInstance) {
        // 尝试多种方式获取 modelValue
        const props = vueInstance.props || vueInstance.$props || vueInstance.propsData || {};
        modelValue = props.modelValue !== undefined ? props.modelValue : 
                    (vueInstance.modelValue !== undefined ? vueInstance.modelValue :
                    (vueInstance.$attrs?.modelValue !== undefined ? vueInstance.$attrs.modelValue : null));
        
        // 检查值是否存在
        // 注意：空字符串 '' 也可能是有效选择（如"全部客户"），所以也要检查
        // 但 null 和 undefined 表示没有选择
        if (modelValue !== null && modelValue !== undefined) {
          hasVueValue = true;
        }
      }
    } catch (e) {
      // 忽略错误，继续其他检测方法
    }
    
    // 方法2: 检查是否有 is-empty 类
    const hasIsEmptyClass = selectEl.classList.contains('is-empty');
    
    // 方法3: 检查 input wrapper 内的所有可见文本内容
    const inputWrapper = selectEl.querySelector('.el-input__wrapper');
    let hasVisibleText = false;
    let displayedText = '';
    const originalPlaceholder = selectEl.getAttribute('placeholder') || '';
    
    if (inputWrapper) {
      // 获取 input wrapper 内的所有文本
      const allText = inputWrapper.innerText || inputWrapper.textContent || '';
      const currentPlaceholderText = placeholderEl.textContent?.trim() || '';
      
      // 关键修复：如果 placeholder 显示的文本不是原始的 placeholder 属性值，
      // 说明这个文本可能是选中值，而不是真正的 placeholder
      if (currentPlaceholderText && currentPlaceholderText !== originalPlaceholder) {
        // placeholder 显示的文本与原始 placeholder 不同，说明这是选中值
        hasVisibleText = true;
        displayedText = currentPlaceholderText;
      } else {
        // 正常情况：排除 placeholder 文本后检查是否有其他文本
        const cleanText = allText.replace(currentPlaceholderText, '').trim();
        hasVisibleText = cleanText.length > 0;
        displayedText = cleanText;
      }
      
      // 检查是否有选中的文本元素（Element Plus 可能使用特殊元素显示选中值）
      const selectedTextEl = inputWrapper.querySelector('.el-select__selected-item') ||
                            inputWrapper.querySelector('.el-select__selection') ||
                            inputWrapper.querySelector('[class*="selected"]') ||
                            inputWrapper.querySelector('[class*="value"]');
      if (selectedTextEl && selectedTextEl.textContent?.trim()) {
        const selectedText = selectedTextEl.textContent.trim();
        // 如果选中的文本不是原始 placeholder，说明有选中值
        if (selectedText !== originalPlaceholder) {
          hasVisibleText = true;
          displayedText = selectedText;
        }
      }
    }
    
    // 方法4: 检查是否有选中的标签（多选模式）
    const hasSelectedTags = selectEl.querySelector('.el-select__tags') !== null ||
      selectEl.querySelector('.el-select__selected-item') !== null;
    
    // 方法5: 检查 input 元素的值
    const inputEl = selectEl.querySelector('.el-select__input') ||
      selectEl.querySelector('.el-input__wrapper input') ||
      selectEl.querySelector('.el-input__inner');
    
    let hasInputValue = false;
    if (inputEl) {
      const inputValue = (inputEl.value || inputEl.textContent || '').trim();
      const placeholderText = placeholderEl.textContent?.trim() || '';
      hasInputValue = inputValue && inputValue !== placeholderText && inputValue.length > 0;
    }
    
    // 综合判断：优先使用 Vue modelValue（最可靠）
    // 如果 Vue modelValue 为 null 或 undefined，即使 is-empty 为 false，也应该显示 placeholder
    let hasSelectedValue = false;
    
    // 特殊情况：如果 placeholder 显示的文本与原始 placeholder 不同，说明有选中值
    // 这是关键修复：即使 Vue modelValue 为 null，如果 placeholder 显示的文本不是原始 placeholder，
    // 说明用户已经选择了值，只是 Vue 状态没有同步
    if (displayedText && displayedText !== originalPlaceholder && displayedText.length > 0) {
      hasSelectedValue = true;
      
      // 关键修复：如果 Vue modelValue 为 null，但检测到有选中文本，
      // 尝试从 DOM 中找到对应的 option 值，并强制更新 Vue 状态
      if ((modelValue === null || modelValue === undefined) && vueInstance) {
        try {
          // 查找所有 option 元素，找到 label 匹配的 option
          const allOptions = selectEl.querySelectorAll('.el-select-dropdown__item, [role="option"]');
          let matchedOption = null;
          let matchedValue = null;
          
          for (const option of allOptions) {
            const optionText = option.textContent?.trim() || '';
            if (optionText === displayedText) {
              // 找到匹配的 option，尝试获取其 value
              matchedOption = option;
              // 尝试从 data-value 或 data-option-value 属性获取值
              matchedValue = option.getAttribute('data-value') || 
                           option.getAttribute('data-option-value') ||
                           option.getAttribute('value');
              
              // 如果还是找不到，尝试从 Vue 实例中获取 options
              if (!matchedValue && vueInstance.options) {
                const optionData = vueInstance.options.find(opt => {
                  const label = opt.label || opt.name || '';
                  return label === displayedText;
                });
                if (optionData) {
                  matchedValue = optionData.value;
                }
              }
              
              break;
            }
          }
          
          // 如果找到了匹配的值，尝试触发 change 事件来更新 Vue 状态
          if (matchedValue !== null && matchedValue !== undefined) {
            // 尝试直接更新 Vue 实例的 modelValue（如果可能）
            try {
              // 方法1: 尝试通过 Vue 实例的方法更新
              if (vueInstance.setValue) {
                vueInstance.setValue(matchedValue);
              } else if (vueInstance.handleChange) {
                vueInstance.handleChange(matchedValue);
              }
              
              // 方法2: 尝试通过 emit 事件更新（Vue 3 的 v-model 使用 update:modelValue）
              if (vueInstance.$emit) {
                vueInstance.$emit('update:modelValue', matchedValue);
              } else if (vueInstance.emit) {
                vueInstance.emit('update:modelValue', matchedValue);
              }
              
              // 方法3: 尝试直接设置 props（不推荐，但作为最后手段）
              if (vueInstance.props && typeof vueInstance.props === 'object') {
                vueInstance.props.modelValue = matchedValue;
              }
              
              // 方法4: 尝试访问父组件并更新（如果可能）
              const parentComponent = vueInstance.parent || vueInstance.$parent;
              if (parentComponent) {
                // 尝试找到绑定到这个 select 的变量
                // 这需要知道变量名，但我们可以尝试通过查找 v-model 属性
                const vModelAttr = selectEl.getAttribute('v-model') || 
                                  selectEl.getAttribute(':model-value') ||
                                  selectEl.getAttribute('v-bind:model-value');
                if (vModelAttr && parentComponent[vModelAttr]) {
                  parentComponent[vModelAttr] = matchedValue;
                }
              }
              
              // 方法5: 创建并触发 change 事件（可能触发 Element Plus 的内部更新）
              const changeEvent = new Event('change', { bubbles: true, cancelable: true });
              changeEvent.value = matchedValue;
              selectEl.dispatchEvent(changeEvent);
              
              // 方法6: 尝试触发 input 事件（某些情况下可能有效）
              const inputEvent = new Event('input', { bubbles: true, cancelable: true });
              inputEvent.value = matchedValue;
              selectEl.dispatchEvent(inputEvent);
            } catch (e) {
              // 忽略错误，继续其他修复
              if (window.DEBUG_SELECT) {
                console.warn('[fixSelectDisplay] 尝试更新 Vue modelValue 失败:', e);
              }
            }
          }
        } catch (e) {
          // 忽略错误，继续其他修复
        }
      }
    } else if (hasVueValue) {
      // Vue 有值（包括空字符串），肯定有选中值
      hasSelectedValue = true;
    } else if (modelValue === null || modelValue === undefined) {
      // Vue 值为 null 或 undefined，且没有检测到选中文本，肯定没有选中值
      hasSelectedValue = false;
    } else {
      // 其他情况：使用其他检测方法
      hasSelectedValue = !hasIsEmptyClass || hasVisibleText || hasSelectedTags || hasInputValue;
    }
    
    if (hasSelectedValue) {
      // 强制移除 is-empty 类（这是关键！）
      selectEl.classList.remove('is-empty');
      
      // 强制隐藏 placeholder
      placeholderEl.style.cssText = `
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        height: 0 !important;
        width: 0 !important;
        overflow: hidden !important;
        pointer-events: none !important;
        position: absolute !important;
        z-index: -9999 !important;
        left: -9999px !important;
        top: -9999px !important;
      `;
      
      // 确保选中值可见 - 找到所有可能的显示元素
      if (inputWrapper) {
        // 找到显示选中值的元素（可能是 .el-select__selection 或其他）
        const selectionEl = inputWrapper.querySelector('.el-select__selection') ||
                           inputWrapper.querySelector('.el-select__selected-item') ||
                           inputWrapper.querySelector('[class*="selection"]');
        
        if (selectionEl) {
          // 确保选中值元素可见
          selectionEl.style.cssText = `
            opacity: 1 !important;
            visibility: visible !important;
            z-index: 9999 !important;
            position: relative !important;
            display: block !important;
            color: var(--el-text-color-regular) !important;
          `;
        }
        
        // 确保 input 元素可见
        const inputs = inputWrapper.querySelectorAll('input');
        inputs.forEach(input => {
          input.style.cssText = `
            opacity: 1 !important;
            visibility: visible !important;
            color: var(--el-text-color-regular) !important;
            z-index: 9999 !important;
            position: relative !important;
            display: block !important;
          `;
        });
        
        // 确保所有非 placeholder 的子元素可见
        const children = inputWrapper.children;
        for (let i = 0; i < children.length; i++) {
          const child = children[i];
          if (child !== placeholderEl && !child.classList.contains('el-select__placeholder')) {
            const childText = child.textContent?.trim() || '';
            // 如果子元素有文本，且不是原始 placeholder，确保可见
            if (childText && childText !== originalPlaceholder) {
              child.style.cssText = `
                opacity: 1 !important;
                visibility: visible !important;
                z-index: 9999 !important;
                position: relative !important;
                display: block !important;
                color: var(--el-text-color-regular) !important;
              `;
            }
          }
        }
      }
    } else {
      // 如果没有选中值，添加 is-empty 类并显示 placeholder
      selectEl.classList.add('is-empty');
      placeholderEl.style.cssText = `
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
        position: absolute !important;
        left: 11px !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        z-index: 1 !important;
        height: auto !important;
        width: auto !important;
        pointer-events: none !important;
      `;
    }
    
    fixedCount++;
  });
  
  // 调试输出（仅在开发环境或需要时）
  if (fixedCount > 0 && window.DEBUG_SELECT) {
    console.log(`[fixSelectDisplay] 已处理 ${fixedCount} 个下拉选择框`);
  }
};

// 添加调试函数，帮助诊断问题（全局函数）
const debugSelectDisplay = () => {
  const selectElements = document.querySelectorAll('.el-select');
  console.log('=== el-select 调试信息 ===');
  selectElements.forEach((selectEl, index) => {
    const placeholderEl = selectEl.querySelector('.el-select__placeholder');
    const inputWrapper = selectEl.querySelector('.el-input__wrapper');
    const inputEl = selectEl.querySelector('input');
    const hasIsEmpty = selectEl.classList.contains('is-empty');
    
    // 尝试获取 Vue 实例
    let vueValue = null;
    try {
      const vueInstance = selectEl.__vueParentComponent || selectEl.__vue__;
      if (vueInstance) {
        const props = vueInstance.props || vueInstance.$props || {};
        vueValue = props.modelValue !== undefined ? props.modelValue : 
                  (vueInstance.modelValue !== undefined ? vueInstance.modelValue : null);
      }
    } catch (e) {
      vueValue = '无法获取: ' + e.message;
    }
    
    console.log(`\n下拉框 ${index + 1}:`, {
      'is-empty 类': hasIsEmpty,
      'Vue modelValue': vueValue,
      'placeholder 文本': placeholderEl?.textContent?.trim(),
      'input value': inputEl?.value,
      'input textContent': inputEl?.textContent?.trim(),
      'wrapper innerText': inputWrapper?.innerText?.trim(),
      'DOM 结构': selectEl.outerHTML.substring(0, 200)
    });
  });
  console.log('=== 调试信息结束 ===');
};

// 导出到 window 对象，供全局使用
window.fixSelectDisplay = fixSelectDisplay;
window.debugSelectDisplay = debugSelectDisplay;

// 修复表单元素可访问性问题：为缺少 title 和 placeholder 的 input 元素添加可访问性属性
const fixSelectAccessibility = () => {
  // 使用 MutationObserver 监听 DOM 变化，确保动态创建的表单元素也能被修复
  // 使用防抖，避免频繁调用导致性能问题
  let mutationTimeout = null;
  const observer = new MutationObserver(() => {
    // 清除之前的定时器
    if (mutationTimeout) {
      clearTimeout(mutationTimeout);
    }
    // 防抖：300ms 内只执行最后一次
    mutationTimeout = setTimeout(() => {
      fixSelectInputs();
      fixDatePickerInputs();
      fixOtherFormInputs();
      // 只在有 el-select 元素时才调用 fixSelectDisplay
      if (document.querySelector('.el-select')) {
        fixSelectDisplay();
      }
    }, 300);
  });

  // 修复 el-select 的 input 元素
  const fixSelectInputs = () => {
    const selectInputs = document.querySelectorAll('.el-select .el-select__input, .el-select .el-input__inner, .el-select .el-input__wrapper input');
    selectInputs.forEach((input) => {
      if (!input.getAttribute('title') && !input.getAttribute('placeholder')) {
        const selectEl = input.closest('.el-select');
        if (selectEl) {
          let placeholder = selectEl.getAttribute('placeholder') ||
            selectEl.getAttribute('data-placeholder') ||
            '请选择';

          input.setAttribute('title', placeholder);
          if (input.tagName === 'INPUT' && !input.getAttribute('placeholder')) {
            input.setAttribute('placeholder', placeholder);
          }
          if (!input.getAttribute('aria-label')) {
            input.setAttribute('aria-label', placeholder);
          }
        } else {
          input.setAttribute('title', '请选择');
          if (!input.getAttribute('aria-label')) {
            input.setAttribute('aria-label', '请选择');
          }
        }
      } else if (!input.getAttribute('aria-label')) {
        const label = input.getAttribute('title') || input.getAttribute('placeholder') || '请选择';
        input.setAttribute('aria-label', label);
      }
    });
  };


  // 修复 el-date-picker 的 input 元素
  const fixDatePickerInputs = () => {
    const datePickerInputs = document.querySelectorAll('.el-date-picker .el-input__inner, .el-date-editor .el-input__inner, .el-date-editor input');
    datePickerInputs.forEach((input) => {
      if (!input.getAttribute('title') && !input.getAttribute('placeholder')) {
        const datePickerEl = input.closest('.el-date-picker, .el-date-editor');
        if (datePickerEl) {
          let placeholder = datePickerEl.getAttribute('placeholder') ||
            datePickerEl.getAttribute('start-placeholder') ||
            datePickerEl.getAttribute('end-placeholder') ||
            '请选择日期';

          input.setAttribute('title', placeholder);
          if (input.tagName === 'INPUT' && !input.getAttribute('placeholder')) {
            input.setAttribute('placeholder', placeholder);
          }
          if (!input.getAttribute('aria-label')) {
            input.setAttribute('aria-label', placeholder);
          }
        } else {
          input.setAttribute('title', '请选择日期');
          if (!input.getAttribute('aria-label')) {
            input.setAttribute('aria-label', '请选择日期');
          }
        }
      } else if (!input.getAttribute('aria-label')) {
        const label = input.getAttribute('title') || input.getAttribute('placeholder') || '请选择日期';
        input.setAttribute('aria-label', label);
      }
    });
  };

  // 修复其他表单元素的 input（el-autocomplete, el-cascader 等）
  const fixOtherFormInputs = () => {
    const otherInputs = document.querySelectorAll('.el-autocomplete input, .el-cascader input, .el-time-picker input');
    otherInputs.forEach((input) => {
      if (!input.getAttribute('title') && !input.getAttribute('placeholder') && !input.getAttribute('aria-label')) {
        const parentEl = input.closest('.el-autocomplete, .el-cascader, .el-time-picker');
        let placeholder = '请输入';

        if (parentEl) {
          placeholder = parentEl.getAttribute('placeholder') ||
            parentEl.getAttribute('data-placeholder') ||
            placeholder;
        }

        input.setAttribute('title', placeholder);
        if (input.tagName === 'INPUT' && !input.getAttribute('placeholder')) {
          input.setAttribute('placeholder', placeholder);
        }
        input.setAttribute('aria-label', placeholder);
      }
    });
  };

  // 立即执行一次修复
  const fixAllInputs = () => {
    fixSelectInputs();
    fixDatePickerInputs();
    fixOtherFormInputs();
    fixSelectDisplay(); // 修复 el-select 选中值显示问题
  };

  // 延迟执行，确保 DOM 已完全加载
  setTimeout(fixAllInputs, 100);
  
  // 增加修复频率，确保选中值能正确显示
  setTimeout(fixSelectDisplay, 200);
  setTimeout(fixSelectDisplay, 500);
  setTimeout(fixSelectDisplay, 1000);

  // 在路由变化后也执行修复（Vue Router 导航后）
  if (router) {
    router.afterEach(() => {
      setTimeout(fixAllInputs, 200);
      setTimeout(fixSelectDisplay, 500);
      setTimeout(fixSelectDisplay, 1000);
    });
  }

  // 开始观察 DOM 变化（使用更保守的配置，避免性能问题）
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class'] // 只监听 class 变化，不监听 style（避免频繁触发）
  });
  
  // 监听所有 el-select 的 change 事件（使用防抖，避免频繁调用）
  let changeTimeout = null;
  document.addEventListener('change', (e) => {
    if (e.target.closest('.el-select')) {
      // 清除之前的定时器
      if (changeTimeout) {
        clearTimeout(changeTimeout);
      }
      // 防抖：100ms 后执行
      changeTimeout = setTimeout(() => {
        fixSelectDisplay();
      }, 100);
    }
  }, true);
  
  // 监听所有 el-select 的 click 事件（选择选项时，使用防抖）
  let clickTimeout = null;
  document.addEventListener('click', (e) => {
    if (e.target.closest('.el-select-dropdown__item')) {
      // 清除之前的定时器
      if (clickTimeout) {
        clearTimeout(clickTimeout);
      }
      // 防抖：100ms 后执行
      clickTimeout = setTimeout(() => {
        fixSelectDisplay();
      }, 100);
    }
  }, true);
  
};

// 修复 -moz-appearance 兼容性问题：为所有使用 -moz-appearance 的元素添加 appearance 属性
const fixMozAppearance = () => {
  // 查找所有使用 -moz-appearance 的元素
  const styleSheets = document.styleSheets;

  // 方法1：通过内联样式修复
  const elementsWithMozAppearance = document.querySelectorAll('[style*="-moz-appearance"]');
  elementsWithMozAppearance.forEach((el) => {
    const style = el.getAttribute('style') || '';
    if (style.includes('-moz-appearance') && !style.includes('appearance:')) {
      // 获取 -moz-appearance 的值
      const match = style.match(/-moz-appearance:\s*([^;]+)/);
      if (match) {
        const value = match[1].trim();
        el.style.appearance = value;
      }
    }
  });

  // 方法2：通过计算样式修复
  // 注意：Element Plus 编译后的 CSS 可能使用 .el-input_inner（单下划线）或 .el-input__inner（双下划线）
  const allInputs = document.querySelectorAll('input, .el-input__inner, .el-input_inner, .el-input__wrapper');
  allInputs.forEach((el) => {
    const computedStyle = window.getComputedStyle(el);
    const mozAppearance = computedStyle.getPropertyValue('-moz-appearance');
    const appearance = computedStyle.getPropertyValue('appearance');

    // 如果元素有 -moz-appearance 但没有 appearance，添加它
    if (mozAppearance && mozAppearance !== 'none' && (!appearance || appearance === 'none' || appearance === 'auto')) {
      // 如果 -moz-appearance 是 textfield，设置 appearance 为 textfield
      if (mozAppearance.trim() === 'textfield') {
        el.style.appearance = 'textfield';
      } else {
        el.style.appearance = mozAppearance;
      }
    }
  });

  // 方法3：专门修复 Element Plus 分页组件中的输入框
  // 查找所有在 .el-pagination 中的输入元素
  const paginationInputs = document.querySelectorAll('.el-pagination input, .el-pagination .el-input__inner, .el-pagination .el-input_inner');
  paginationInputs.forEach((el) => {
    const computedStyle = window.getComputedStyle(el);
    const mozAppearance = computedStyle.getPropertyValue('-moz-appearance');
    const appearance = computedStyle.getPropertyValue('appearance');

    // 如果元素有 -moz-appearance: textfield 但没有 appearance，强制添加
    if (mozAppearance && mozAppearance.trim() === 'textfield' && (!appearance || appearance === 'none' || appearance === 'auto')) {
      el.style.appearance = 'textfield';
    }
  });

  // 方法4：直接修改 Element Plus 样式表中的规则
  // 扫描所有样式表，查找包含 .el-pagination .el-input_inner 的规则
  try {
    const styleSheets = document.styleSheets;
    for (let i = 0; i < styleSheets.length; i++) {
      try {
        const sheet = styleSheets[i];
        // 跳过跨域样式表
        if (!sheet.cssRules) continue;

        // 检查是否是 Element Plus 样式表
        const href = sheet.href || '';
        const isElementPlus = href.includes('element-plus') || href.includes('elementPlus');

        for (let j = 0; j < sheet.cssRules.length; j++) {
          const rule = sheet.cssRules[j];
          if (rule.style && rule.selectorText) {
            // 查找包含 .el-pagination .el-input_inner 的规则
            if (rule.selectorText.includes('.el-pagination') &&
              (rule.selectorText.includes('.el-input_inner') || rule.selectorText.includes('.el-input__inner'))) {
              const mozAppearance = rule.style.getPropertyValue('-moz-appearance');
              const appearance = rule.style.getPropertyValue('appearance');

              // 如果规则有 -moz-appearance 但没有 appearance，添加它
              if (mozAppearance && mozAppearance.trim() === 'textfield' && (!appearance || appearance === 'none' || appearance === 'auto')) {
                try {
                  rule.style.setProperty('appearance', 'textfield', 'important');
                } catch (e) {
                  // 如果无法修改规则，尝试通过内联样式修复匹配的元素
                  try {
                    const elements = document.querySelectorAll(rule.selectorText);
                    elements.forEach((el) => {
                      el.style.setProperty('appearance', 'textfield', 'important');
                    });
                  } catch (e2) {
                    // 忽略选择器解析错误
                  }
                }
              }
            }
          }
        }
      } catch (e) {
        // 忽略跨域样式表访问错误
      }
    }
  } catch (e) {
    // 忽略样式表访问错误
  }
};

// 修复 mask 相关属性的兼容性问题：为所有使用 mask 相关属性的元素添加 -webkit- 前缀
const fixMaskProperties = () => {
  // 修复 mask-image
  const fixMaskImage = (el) => {
    const computedStyle = window.getComputedStyle(el);
    const maskImage = computedStyle.getPropertyValue('mask-image');
    const webkitMaskImage = computedStyle.getPropertyValue('-webkit-mask-image');

    // 如果有 mask-image 但没有 -webkit-mask-image，添加它
    if (maskImage && maskImage !== 'none' && !webkitMaskImage) {
      el.style.setProperty('-webkit-mask-image', maskImage, 'important');
    }

    // 检查内联样式
    const style = el.getAttribute('style') || '';
    if (style.includes('mask-image:') && !style.includes('-webkit-mask-image:')) {
      const match = style.match(/mask-image:\s*([^;]+)/);
      if (match) {
        const value = match[1].trim();
        el.style.setProperty('-webkit-mask-image', value, 'important');
      }
    }
  };

  // 修复 mask-position
  const fixMaskPosition = (el) => {
    const computedStyle = window.getComputedStyle(el);
    const maskPosition = computedStyle.getPropertyValue('mask-position');
    const webkitMaskPosition = computedStyle.getPropertyValue('-webkit-mask-position');

    if (maskPosition && maskPosition !== 'initial' && !webkitMaskPosition) {
      el.style.setProperty('-webkit-mask-position', maskPosition, 'important');
    }

    const style = el.getAttribute('style') || '';
    if (style.includes('mask-position:') && !style.includes('-webkit-mask-position:')) {
      const match = style.match(/mask-position:\s*([^;]+)/);
      if (match) {
        const value = match[1].trim();
        el.style.setProperty('-webkit-mask-position', value, 'important');
      }
    }
  };

  // 修复 mask-repeat
  const fixMaskRepeat = (el) => {
    const computedStyle = window.getComputedStyle(el);
    const maskRepeat = computedStyle.getPropertyValue('mask-repeat');
    const webkitMaskRepeat = computedStyle.getPropertyValue('-webkit-mask-repeat');

    if (maskRepeat && maskRepeat !== 'initial' && !webkitMaskRepeat) {
      el.style.setProperty('-webkit-mask-repeat', maskRepeat, 'important');
    }

    const style = el.getAttribute('style') || '';
    if (style.includes('mask-repeat:') && !style.includes('-webkit-mask-repeat:')) {
      const match = style.match(/mask-repeat:\s*([^;]+)/);
      if (match) {
        const value = match[1].trim();
        el.style.setProperty('-webkit-mask-repeat', value, 'important');
      }
    }
  };

  // 优化：只检查可能使用 mask 相关属性的元素，而不是所有元素
  // 方法1：检查内联样式
  const elementsWithMaskInStyle = document.querySelectorAll('[style*="mask-image"], [style*="mask-position"], [style*="mask-repeat"]');
  elementsWithMaskInStyle.forEach((el) => {
    fixMaskImage(el);
    fixMaskPosition(el);
    fixMaskRepeat(el);
  });

  // 方法2：检查计算样式（只检查特定类名的元素，提高性能）
  const potentialMaskElements = document.querySelectorAll('[class*="mask"], [class*="close-button"], [class*="button"], .el-select-dropdown__item');
  potentialMaskElements.forEach((el) => {
    const computedStyle = window.getComputedStyle(el);
    const hasMaskImage = computedStyle.getPropertyValue('mask-image') !== 'none';
    const hasMaskPosition = computedStyle.getPropertyValue('mask-position') !== 'initial' && computedStyle.getPropertyValue('mask-position') !== '';
    const hasMaskRepeat = computedStyle.getPropertyValue('mask-repeat') !== 'initial' && computedStyle.getPropertyValue('mask-repeat') !== '';

    if (hasMaskImage) {
      fixMaskImage(el);
    }
    if (hasMaskPosition) {
      fixMaskPosition(el);
    }
    if (hasMaskRepeat) {
      fixMaskRepeat(el);
    }
  });

  // 方法3：扫描所有样式表，查找使用 mask-image 的规则，并动态修复
  // 注意：这可以修复通过外部样式表（如第三方库）添加的 mask-image
  try {
    const styleSheets = document.styleSheets;
    for (let i = 0; i < styleSheets.length; i++) {
      try {
        const sheet = styleSheets[i];
        // 跳过跨域样式表
        if (!sheet.cssRules) continue;

        for (let j = 0; j < sheet.cssRules.length; j++) {
          const rule = sheet.cssRules[j];
          if (rule.style && rule.style.maskImage && rule.style.maskImage !== 'none') {
            // 如果规则有 mask-image 但没有 -webkit-mask-image，尝试添加
            if (!rule.style.webkitMaskImage) {
              rule.style.webkitMaskImage = rule.style.maskImage;
            }

            // 查找匹配的元素并应用修复
            try {
              const selector = rule.selectorText;
              if (selector) {
                const elements = document.querySelectorAll(selector);
                elements.forEach((el) => {
                  fixMaskImage(el);
                });
              }
            } catch (e) {
              // 忽略选择器解析错误
            }
          }
        }
      } catch (e) {
        // 忽略跨域样式表访问错误
      }
    }
  } catch (e) {
    // 忽略样式表访问错误
  }
};

// 移动端优化初始化
const initMobileOptimizations = () => {
  // 修复视口高度（解决移动端浏览器地址栏问题）
  useViewportHeight();

  // 禁用双击缩放
  disableDoubleTapZoom();
};

// 在应用挂载后，根据当前路由决定是否初始化认证和时区
// 使用 nextTick 确保路由已初始化
nextTick(() => {
  // 延迟初始化，不阻塞首次渲染
  setTimeout(() => {
    // 初始化移动端优化
    initMobileOptimizations();

    initializeAuth();
    initializeTimezone();
    fixSelectAccessibility();
    fixMozAppearance();
    fixMaskProperties();

    // 使用 MutationObserver 监听 DOM 变化，确保动态创建的元素也能被修复
    const observer = new MutationObserver(() => {
      fixMozAppearance();
      fixMaskProperties();
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['style', 'class']
    });
  }, 0);
});
