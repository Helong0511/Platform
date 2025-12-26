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
  
  if (selectElements.length === 0) {
    return; // 如果没有 el-select 元素，直接返回
  }
  
  // 调试信息：记录修复函数被调用
  if (window.DEBUG_SELECT) {
    console.log('[fixSelectDisplay] 开始修复，找到', selectElements.length, '个 el-select 元素');
  }
  
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
    
    // 获取原始 placeholder（多种方式尝试）
    let originalPlaceholder = selectEl.getAttribute('placeholder') || 
                             selectEl.querySelector('[placeholder]')?.getAttribute('placeholder') || '';
    
    // 如果从 DOM 属性中获取不到，尝试从 Vue 实例中获取
    if (!originalPlaceholder) {
      try {
        const vueInstance = selectEl.__vueParentComponent || selectEl.__vue__;
        if (vueInstance) {
          const props = vueInstance.props || vueInstance.$props || vueInstance.propsData || {};
          originalPlaceholder = props.placeholder || vueInstance.placeholder || '';
        }
      } catch (e) {
        // 忽略错误
      }
    }
    
    // 如果还是获取不到，尝试从 input 元素的 placeholder 属性获取
    if (!originalPlaceholder && inputWrapper) {
      const inputEl = inputWrapper.querySelector('input');
      if (inputEl) {
        originalPlaceholder = inputEl.getAttribute('placeholder') || '';
      }
    }
    
    // 如果还是获取不到，尝试从 Vue 组件的实际渲染中获取
    // 查找 el-select 组件在 Vue 组件树中的位置，获取其 props
    if (!originalPlaceholder || originalPlaceholder === '请选择') {
      try {
        // 方法1: 从 Vue 实例的 setupState 或 ctx 中获取
        const vueInstance = selectEl.__vueParentComponent || selectEl.__vue__;
        if (vueInstance) {
          // 尝试从 setupState 获取
          if (vueInstance.setupState && vueInstance.setupState.placeholder) {
            originalPlaceholder = vueInstance.setupState.placeholder;
          }
          // 尝试从 ctx 获取
          if ((!originalPlaceholder || originalPlaceholder === '请选择') && vueInstance.ctx) {
            const ctxPlaceholder = vueInstance.ctx.placeholder || vueInstance.ctx.$attrs?.placeholder;
            if (ctxPlaceholder && ctxPlaceholder !== '请选择') {
              originalPlaceholder = ctxPlaceholder;
            }
          }
          // 尝试从 props 的原始值获取（如果 props 是响应式的，可能需要特殊处理）
          if ((!originalPlaceholder || originalPlaceholder === '请选择') && vueInstance.props) {
            const propsPlaceholder = vueInstance.props.placeholder;
            if (propsPlaceholder && propsPlaceholder !== '请选择' && typeof propsPlaceholder === 'string') {
              originalPlaceholder = propsPlaceholder;
            }
          }
        }
        
        // 方法2: 从父组件中查找 el-select 的 placeholder 属性
        if ((!originalPlaceholder || originalPlaceholder === '请选择') && selectEl.parentElement) {
          // 查找最近的 Vue 组件实例
          let parent = selectEl.parentElement;
          let depth = 0;
          while (parent && depth < 5) {
            const parentVue = parent.__vueParentComponent || parent.__vue__;
            if (parentVue) {
              // 尝试从父组件的 data 或 props 中查找
              if (parentVue.setupState) {
                const setupPlaceholder = parentVue.setupState.placeholder;
                if (setupPlaceholder && setupPlaceholder !== '请选择') {
                  originalPlaceholder = setupPlaceholder;
                  break;
                }
              }
            }
            parent = parent.parentElement;
            depth++;
          }
        }
        
        // 方法3: 如果 placeholder 是 "请选择"，尝试从常见的完整 placeholder 推断
        // 比如 "请选择广告主"、"请选择客户" 等
        if (originalPlaceholder === '请选择' && placeholderEl) {
          // 检查是否有其他 el-select 有完整的 placeholder，作为参考
          const otherSelects = document.querySelectorAll('.el-select');
          for (const otherSelect of otherSelects) {
            if (otherSelect !== selectEl) {
              const otherPlaceholder = otherSelect.getAttribute('placeholder') || 
                                     otherSelect.querySelector('.el-select__placeholder')?.textContent?.trim();
              if (otherPlaceholder && otherPlaceholder.includes('请选择') && otherPlaceholder.length > 3) {
                // 如果其他 select 有完整的 placeholder，且当前 select 的 placeholder 文本是 "请选择"
                // 可能是同一个组件，使用相同的完整 placeholder
                originalPlaceholder = otherPlaceholder;
                break;
              }
            }
          }
        }
      } catch (e) {
        // 忽略错误
        if (window.DEBUG_SELECT) {
          console.warn('[fixSelectDisplay] 获取 originalPlaceholder 失败:', e);
        }
      }
    }
    
    // 如果 originalPlaceholder 仍然是 "请选择"，尝试从 DOM 中查找完整的 placeholder
    // 有时候 Element Plus 会在内部存储完整的 placeholder
    if (originalPlaceholder === '请选择' && placeholderEl) {
      // 检查 placeholder 元素的 data 属性或其他属性
      const dataPlaceholder = placeholderEl.getAttribute('data-placeholder') || 
                             placeholderEl.getAttribute('data-original-placeholder');
      if (dataPlaceholder && dataPlaceholder !== '请选择') {
        originalPlaceholder = dataPlaceholder;
      }
    }
    
    // 获取 placeholder 文本（在 if 块外定义，确保作用域正确）
    const currentPlaceholderText = placeholderEl ? (placeholderEl.textContent?.trim() || '') : '';
    
    if (inputWrapper) {
      // 获取 input wrapper 内的所有文本
      const allText = inputWrapper.innerText || inputWrapper.textContent || '';
      
      // 关键修复：如果 placeholder 显示的文本不是原始的 placeholder 属性值，
      // 说明这个文本可能是选中值，而不是真正的 placeholder
      // 特别处理：如果 placeholder 文本包含原始 placeholder 的一部分（如"请选择"），
      // 但后面还有其他文本（如"请选择Sweepsone"），说明选中值被错误地显示在 placeholder 中
      if (currentPlaceholderText) {
        // 检查是否是选中值被错误地放在 placeholder 中
        if (currentPlaceholderText !== originalPlaceholder) {
          // 如果 placeholder 文本以原始 placeholder 开头，但后面有额外文本，说明选中值在 placeholder 中
          if (originalPlaceholder && currentPlaceholderText.startsWith(originalPlaceholder)) {
            // 提取选中值部分（去掉原始 placeholder）
            const selectedValueText = currentPlaceholderText.replace(originalPlaceholder, '').trim();
            if (selectedValueText) {
              hasVisibleText = true;
              displayedText = selectedValueText;
              // 关键修复：将选中值从 placeholder 中提取出来，放到正确的位置
              // 清空 placeholder 的文本，恢复为原始 placeholder
              placeholderEl.textContent = originalPlaceholder;
            }
          } else if (currentPlaceholderText !== originalPlaceholder) {
            // placeholder 显示的文本与原始 placeholder 完全不同，说明这是选中值
            hasVisibleText = true;
            displayedText = currentPlaceholderText;
            // 关键修复：将选中值从 placeholder 中提取出来
            // 清空 placeholder 的文本，恢复为原始 placeholder
            placeholderEl.textContent = originalPlaceholder;
          }
        }
      }
      
      // 检查是否有选中的文本元素（Element Plus 可能使用特殊元素显示选中值）
      const selectedTextEl = inputWrapper.querySelector('.el-select__selected-item') ||
                            inputWrapper.querySelector('.el-select__selection') ||
                            inputWrapper.querySelector('[class*="selected"]') ||
                            inputWrapper.querySelector('[class*="value"]');
      if (selectedTextEl && selectedTextEl.textContent?.trim()) {
        const selectedText = selectedTextEl.textContent.trim();
        // 如果选中的文本不是原始 placeholder，说明有选中值
        if (selectedText !== originalPlaceholder && selectedText.length > 0) {
          hasVisibleText = true;
          if (!displayedText) {
            displayedText = selectedText;
          }
        }
      }
      
      // 额外检查：查找所有可能的选中值显示元素
      if (!hasVisibleText && !displayedText) {
        // 检查 input wrapper 内的所有文本节点
        const walker = document.createTreeWalker(
          inputWrapper,
          NodeFilter.SHOW_TEXT,
          null,
          false
        );
        let node;
        while (node = walker.nextNode()) {
          const text = node.textContent?.trim() || '';
          // 如果文本不是原始 placeholder 的一部分，且不是空字符串，可能是选中值
          if (text && 
              text !== originalPlaceholder && 
              !originalPlaceholder.startsWith(text) &&
              text.length > 0) {
            hasVisibleText = true;
            displayedText = text;
            break;
          }
        }
      }
      
      // 如果还没有找到选中文本，检查 input 元素的值
      if (!hasVisibleText) {
        const inputEl = inputWrapper.querySelector('input');
        if (inputEl && inputEl.value && inputEl.value.trim() !== originalPlaceholder) {
          const inputValue = inputEl.value.trim();
          if (inputValue && inputValue !== originalPlaceholder) {
            hasVisibleText = true;
            displayedText = inputValue;
          }
        }
      }
    }
    
    // 方法4: 检查是否有选中的标签（多选模式）
    // 不仅要检查元素是否存在，还要检查它是否有实际内容（不是空的）
    const tagsEl = selectEl.querySelector('.el-select__tags');
    const selectedItemEl = selectEl.querySelector('.el-select__selected-item');
    const hasSelectedTags = (tagsEl && tagsEl.children.length > 0) ||
      (selectedItemEl && selectedItemEl.textContent?.trim() && 
       selectedItemEl.textContent.trim() !== originalPlaceholder &&
       selectedItemEl.textContent.trim().length > 0);
    
    // 方法5: 检查是否有清除按钮（如果有清除按钮，说明有选中值）
    const hasClearButton = selectEl.querySelector('.el-select__clear') !== null ||
                           selectEl.querySelector('.el-icon--circle-close') !== null ||
                           selectEl.querySelector('[class*="clear"]') !== null ||
                           selectEl.querySelector('[class*="close"]') !== null;
    
    // 方法6: 检查 input 元素的值
    const inputEl = selectEl.querySelector('.el-select__input') ||
      selectEl.querySelector('.el-input__wrapper input') ||
      selectEl.querySelector('.el-input__inner');
    
    let hasInputValue = false;
    if (inputEl) {
      const inputValue = (inputEl.value || inputEl.textContent || '').trim();
      const placeholderText = placeholderEl.textContent?.trim() || '';
      hasInputValue = inputValue && inputValue !== placeholderText && inputValue.length > 0;
    }
    
    // 综合判断：优先检查清除按钮（最可靠的信号）
    // 如果有清除按钮，说明有选中值（即使 Vue modelValue 为 null）
    // 使用 undefined 作为初始值，表示还没有明确判断
    let hasSelectedValue = undefined;
    
    // 关键修复0: 首先检查 placeholder 文本状态
    // 如果 placeholder 文本是空的或者是原始 placeholder 的一部分，且没有任何选中值信号，肯定没有选中值
    // 但是要注意：如果 placeholder 文本是 "请选择" + 选中值（如 "请选择Sweepsone"），这是有选中值的情况
    const isPartialPlaceholder = originalPlaceholder && 
                                 currentPlaceholderText &&
                                 currentPlaceholderText.length < originalPlaceholder.length &&
                                 currentPlaceholderText.length > 0 &&
                                 originalPlaceholder.startsWith(currentPlaceholderText);
    
    const isEmptyPlaceholder = !currentPlaceholderText || currentPlaceholderText.length === 0;
    
    // 检查是否是 "请选择" + 选中值的情况（如 "请选择Sweepsone"）
    const isPlaceholderWithValue = currentPlaceholderText && 
                                   currentPlaceholderText.startsWith('请选择') && 
                                   currentPlaceholderText.length > 3 &&
                                   !currentPlaceholderText.endsWith('请选择') &&
                                   currentPlaceholderText !== originalPlaceholder;
    
    // 关键判断：如果没有任何选中值信号，且 placeholder 是部分或空的，肯定没有选中值
    // 但是如果是 "请选择" + 选中值的情况，应该认为有选中值
    // 这个判断的优先级最高，确保在没有选中值信号时，部分 placeholder 被正确识别
    const hasNoSelectionSignals = !hasClearButton && 
                                  !hasVisibleText && 
                                  !hasSelectedTags && 
                                  !hasInputValue &&
                                  modelValue === null;
    
    if ((isPartialPlaceholder || isEmptyPlaceholder) && hasNoSelectionSignals && !isPlaceholderWithValue) {
      // 是部分 placeholder 或空 placeholder，且没有任何选中值信号，且不是 "请选择" + 选中值的情况，肯定没有选中值
      hasSelectedValue = false;
      // 恢复为完整的原始 placeholder
      if (placeholderEl && originalPlaceholder) {
        const currentText = placeholderEl.textContent?.trim() || '';
        if (currentText !== originalPlaceholder) {
          placeholderEl.textContent = originalPlaceholder;
        }
      }
      // 跳过后续的选中值检测，直接处理没有选中值的情况
    } else if (isPlaceholderWithValue) {
      // 是 "请选择" + 选中值的情况，提取选中值
      displayedText = currentPlaceholderText.substring(3).trim(); // 去掉 "请选择" 前缀
      if (displayedText && displayedText.length > 0) {
        hasSelectedValue = true;
        // 恢复 placeholder 为原始文本
        if (placeholderEl && originalPlaceholder && placeholderEl.textContent !== originalPlaceholder) {
          placeholderEl.textContent = originalPlaceholder;
        }
      }
    } else if (isEmptyPlaceholder && !hasClearButton && modelValue === null) {
      // 如果 placeholder 是空的，且没有清除按钮，且 Vue modelValue 是 null，肯定没有选中值
      // 这是一个更宽松的判断，确保空 placeholder 时能正确识别
      hasSelectedValue = false;
      // 恢复为完整的原始 placeholder
      if (placeholderEl && originalPlaceholder) {
        const currentText = placeholderEl.textContent?.trim() || '';
        if (currentText !== originalPlaceholder) {
          placeholderEl.textContent = originalPlaceholder;
        }
      }
    }
    // 关键修复1: 优先检查清除按钮（最可靠的信号）
    // 如果有清除按钮，说明用户已经选择了值，只是 Vue 状态没有同步
    // 注意：只有当 hasSelectedValue 还没有被设置时，才执行这个检查
    if (hasSelectedValue === false && (isPartialPlaceholder || isEmptyPlaceholder) && hasNoSelectionSignals) {
      // 已经在上面处理过了，跳过
    } else if (hasClearButton) {
      hasSelectedValue = true;
      // 如果还没有找到选中文本，尝试从其他方式获取
      if (!displayedText) {
        // 尝试从 input wrapper 中查找选中值
        if (inputWrapper) {
          const allText = inputWrapper.innerText || inputWrapper.textContent || '';
          // 排除 placeholder 文本后，查找选中值
          let cleanText = allText.replace(currentPlaceholderText, '').trim();
          // 如果 cleanText 是原始 placeholder 的一部分，继续清理
          if (originalPlaceholder && cleanText === originalPlaceholder.substring(0, cleanText.length)) {
            cleanText = '';
          }
          if (cleanText && cleanText !== originalPlaceholder && cleanText.length > 0) {
            displayedText = cleanText;
          }
        }
        
        // 如果还是没有找到，尝试从下拉选项中查找当前选中的选项
        if (!displayedText) {
          // 方法1: 查找当前选中的选项（可能有 selected 类或其他标记）
          // 注意：下拉选项可能在 body 的其他位置（因为使用了 teleported）
          const allDropdowns = document.querySelectorAll('.el-select-dropdown, .el-popper');
          let selectedOption = null;
          for (const dropdown of allDropdowns) {
            selectedOption = dropdown.querySelector('.el-select-dropdown__item.is-selected') ||
                            dropdown.querySelector('.el-select-dropdown__item.selected') ||
                            dropdown.querySelector('[role="option"][aria-selected="true"]') ||
                            dropdown.querySelector('.el-select-dropdown__item.hover') ||
                            dropdown.querySelector('.el-select-dropdown__item:active');
            if (selectedOption) {
              break;
            }
          }
          // 如果在下拉菜单中没找到，尝试在 selectEl 内部查找
          if (!selectedOption) {
            selectedOption = selectEl.querySelector('.el-select-dropdown__item.is-selected') ||
                            selectEl.querySelector('.el-select-dropdown__item.selected') ||
                            selectEl.querySelector('[role="option"][aria-selected="true"]');
          }
          if (selectedOption) {
            displayedText = selectedOption.textContent?.trim() || '';
          }
          
          // 方法2: 如果 vueInstance 存在，尝试从 Vue 实例中获取当前选中的 label
          if (!displayedText && vueInstance) {
            try {
              // 尝试获取 options 和当前值
              if (vueInstance.options && Array.isArray(vueInstance.options)) {
                // 尝试从内部状态获取选中值（多种属性名）
                const selectedValue = vueInstance.selectedLabel || 
                                     vueInstance.displayValue ||
                                     vueInstance.value ||
                                     vueInstance.selected ||
                                     vueInstance.currentValue ||
                                     vueInstance.modelValue;
                if (selectedValue) {
                  // 如果是对象，尝试获取 label
                  if (typeof selectedValue === 'object') {
                    displayedText = selectedValue.label || selectedValue.name || '';
                  } else {
                    // 如果是值，从 options 中查找对应的 label
                    const option = vueInstance.options.find(opt => 
                      (opt.value || opt.id) === selectedValue
                    );
                    if (option) {
                      displayedText = option.label || option.name || '';
                    }
                  }
                }
              }
              
              // 尝试从 Vue 实例的其他属性中获取选中值
              if (!displayedText) {
                // 检查 setupState
                if (vueInstance.setupState) {
                  const setupSelected = vueInstance.setupState.selectedLabel || 
                                      vueInstance.setupState.displayValue ||
                                      vueInstance.setupState.value ||
                                      vueInstance.setupState.modelValue;
                  if (setupSelected) {
                    if (typeof setupSelected === 'object') {
                      displayedText = setupSelected.label || setupSelected.name || '';
                    } else if (vueInstance.options && Array.isArray(vueInstance.options)) {
                      const option = vueInstance.options.find(opt => 
                        (opt.value || opt.id) === setupSelected
                      );
                      if (option) {
                        displayedText = option.label || option.name || '';
                      }
                    }
                  }
                }
                
                // 检查 ctx
                if (!displayedText && vueInstance.ctx) {
                  const ctxSelected = vueInstance.ctx.selectedLabel || 
                                    vueInstance.ctx.displayValue ||
                                    vueInstance.ctx.value ||
                                    vueInstance.ctx.modelValue;
                  if (ctxSelected) {
                    if (typeof ctxSelected === 'object') {
                      displayedText = ctxSelected.label || ctxSelected.name || '';
                    } else if (vueInstance.options && Array.isArray(vueInstance.options)) {
                      const option = vueInstance.options.find(opt => 
                        (opt.value || opt.id) === ctxSelected
                      );
                      if (option) {
                        displayedText = option.label || option.name || '';
                      }
                    }
                  }
                }
              }
            } catch (e) {
              // 忽略错误
              if (window.DEBUG_SELECT) {
                console.warn('[fixSelectDisplay] 从 Vue 实例获取选中值失败:', e);
              }
            }
          }
          
          // 方法3: 尝试从 input wrapper 的所有文本中提取（排除 placeholder）
          if (!displayedText && inputWrapper) {
            const allTextNodes = [];
            const walker = document.createTreeWalker(
              inputWrapper,
              NodeFilter.SHOW_TEXT,
              {
                acceptNode: function(node) {
                  // 排除 placeholder 元素内的文本
                  if (node.parentElement && node.parentElement.classList.contains('el-select__placeholder')) {
                    return NodeFilter.FILTER_REJECT;
                  }
                  return NodeFilter.FILTER_ACCEPT;
                }
              },
              false
            );
            let node;
            while (node = walker.nextNode()) {
              const text = node.textContent?.trim() || '';
              if (text && text !== originalPlaceholder && !originalPlaceholder.startsWith(text)) {
                allTextNodes.push(text);
              }
            }
            if (allTextNodes.length > 0) {
              displayedText = allTextNodes.join(' ').trim();
            }
          }
        }
      }
    }
    // 关键修复2: 检查 placeholder 文本
    // 如果 placeholder 显示的文本不是原始 placeholder，说明有选中值
    // 但要注意：如果 placeholder 文本只是原始 placeholder 的一部分（如 "请选择" 是 "请选择广告主" 的一部分），
    // 这可能是 Element Plus 的显示问题，不应该认为是选中值
    // 注意：这个检查已经在上面处理过了（isPartialPlaceholder），所以这里只需要处理非部分的情况
    else if (currentPlaceholderText && currentPlaceholderText !== originalPlaceholder && !isPartialPlaceholder) {
      // 检查 placeholder 文本是否包含原始 placeholder + 选中值（如 "请选择Sweepsone"）
      if (originalPlaceholder && currentPlaceholderText.startsWith(originalPlaceholder)) {
        // placeholder 文本以原始 placeholder 开头，后面是选中值
        displayedText = currentPlaceholderText.substring(originalPlaceholder.length).trim();
        if (displayedText && displayedText.length > 0) {
          hasSelectedValue = true;
          // 立即恢复 placeholder 为原始文本
          if (placeholderEl && placeholderEl.textContent !== originalPlaceholder) {
            placeholderEl.textContent = originalPlaceholder;
          }
        }
      } else if (currentPlaceholderText && currentPlaceholderText.length > 0) {
        // placeholder 文本不是原始 placeholder，可能是选中值
        // 检查是否包含 "请选择" 开头（说明是 "请选择" + 选中值，如 "请选择Sweepsone"）
        if (currentPlaceholderText.startsWith('请选择') && currentPlaceholderText.length > 3) {
          displayedText = currentPlaceholderText.substring(3).trim();
          if (displayedText && displayedText.length > 0) {
            hasSelectedValue = true;
            // 恢复 placeholder 为原始文本
            if (placeholderEl && originalPlaceholder && placeholderEl.textContent !== originalPlaceholder) {
              placeholderEl.textContent = originalPlaceholder;
            }
          }
        } else if (currentPlaceholderText.startsWith('请选择') && originalPlaceholder && originalPlaceholder.startsWith('请选择')) {
          // placeholder 文本是 "请选择" + 选中值，且原始 placeholder 也是 "请选择" 开头
          // 提取选中值部分（去掉 "请选择" 前缀）
          displayedText = currentPlaceholderText.substring(originalPlaceholder.length).trim();
          if (!displayedText || displayedText.length === 0) {
            // 如果提取后为空，尝试直接去掉 "请选择" 前缀
            displayedText = currentPlaceholderText.substring(3).trim();
          }
          if (displayedText && displayedText.length > 0) {
            hasSelectedValue = true;
            // 恢复 placeholder 为原始文本
            if (placeholderEl && placeholderEl.textContent !== originalPlaceholder) {
              placeholderEl.textContent = originalPlaceholder;
            }
          }
        } else {
          // 其他情况，可能是选中值
          displayedText = currentPlaceholderText;
          hasSelectedValue = true;
          // 恢复 placeholder 为原始文本
          if (placeholderEl && originalPlaceholder && placeholderEl.textContent !== originalPlaceholder) {
            placeholderEl.textContent = originalPlaceholder;
          }
        }
      }
    } 
    // 关键修复3: 如果通过其他方式检测到选中文本，也认为有选中值
    else if (displayedText && displayedText !== originalPlaceholder && displayedText.length > 0) {
      hasSelectedValue = true;
      
      // 关键修复：如果 Vue modelValue 为 null，但检测到有选中文本，
      // 尝试从 DOM 中找到对应的 option 值，并强制更新 Vue 状态
      // 注意：即使没有 vueInstance，也要继续修复显示问题
      if ((modelValue === null || modelValue === undefined) && displayedText) {
        try {
          let matchedValue = null;
          
          // 方法1: 从下拉选项列表中查找（如果下拉框已打开）
          const allOptions = selectEl.querySelectorAll('.el-select-dropdown__item, [role="option"]');
          for (const option of allOptions) {
            const optionText = option.textContent?.trim() || '';
            // 支持部分匹配（因为可能包含原始 placeholder）
            if (optionText === displayedText || optionText.includes(displayedText) || displayedText.includes(optionText)) {
              // 找到匹配的 option，尝试获取其 value
              matchedValue = option.getAttribute('data-value') || 
                           option.getAttribute('data-option-value') ||
                           option.getAttribute('value') ||
                           option.getAttribute('data-id');
              break;
            }
          }
          
          // 方法2: 如果 vueInstance 存在，尝试从 Vue 实例中获取 options
          if (!matchedValue && vueInstance) {
            if (vueInstance.options && Array.isArray(vueInstance.options)) {
              const optionData = vueInstance.options.find(opt => {
                const label = opt.label || opt.name || opt.text || '';
                return label === displayedText || label.includes(displayedText) || displayedText.includes(label);
              });
              if (optionData) {
                matchedValue = optionData.value || optionData.id;
              }
            }
          }
          
          // 如果找到了匹配的值，尝试触发 change 事件来更新 Vue 状态
          if (matchedValue !== null && matchedValue !== undefined && vueInstance) {
            // 尝试直接更新 Vue 实例的 modelValue（如果可能）
            // 添加严格的空值检查，避免 Vue 内部错误
            try {
              // 方法1: 尝试通过 Vue 实例的方法更新
              if (vueInstance && typeof vueInstance.setValue === 'function') {
                vueInstance.setValue(matchedValue);
              } else if (vueInstance && typeof vueInstance.handleChange === 'function') {
                vueInstance.handleChange(matchedValue);
              }
              
              // 方法2: 尝试通过 emit 事件更新（Vue 3 的 v-model 使用 update:modelValue）
              if (vueInstance && typeof vueInstance.$emit === 'function') {
                vueInstance.$emit('update:modelValue', matchedValue);
              } else if (vueInstance && typeof vueInstance.emit === 'function') {
                vueInstance.emit('update:modelValue', matchedValue);
              }
              
              // 方法3: 尝试直接设置 props（不推荐，但作为最后手段）
              // 注意：直接修改 props 可能导致 Vue 警告，但作为最后手段
              if (vueInstance && vueInstance.props && typeof vueInstance.props === 'object' && !Object.isFrozen(vueInstance.props)) {
                try {
                  vueInstance.props.modelValue = matchedValue;
                } catch (e) {
                  // props 可能是只读的，忽略错误
                }
              }
              
              // 方法4: 尝试访问父组件并更新（如果可能）
              // 添加严格的空值检查，避免 Vue 内部错误
              try {
                const parentComponent = vueInstance?.parent || vueInstance?.$parent;
                if (parentComponent && typeof parentComponent === 'object') {
                  // 尝试找到绑定到这个 select 的变量
                  // 这需要知道变量名，但我们可以尝试通过查找 v-model 属性
                  const vModelAttr = selectEl.getAttribute('v-model') || 
                                    selectEl.getAttribute(':model-value') ||
                                    selectEl.getAttribute('v-bind:model-value');
                  if (vModelAttr && parentComponent[vModelAttr] !== undefined) {
                    parentComponent[vModelAttr] = matchedValue;
                  }
                }
              } catch (e) {
                // 忽略父组件访问错误，继续其他修复
                if (window.DEBUG_SELECT) {
                  console.warn('[fixSelectDisplay] 访问父组件失败:', e);
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
          } else {
          // 如果没有找到匹配的值，尝试从全局广告主列表中查找
          // 这是针对"请选择广告主"下拉框的特殊处理
          if (originalPlaceholder && originalPlaceholder.includes('广告主')) {
            try {
              // 方法1: 尝试从 window 对象获取广告主列表（如果组件已经加载）
              const advertiserList = window.advertiserList || [];
              let matchedAdvertiser = advertiserList.find(adv => {
                const name = adv.advertiser_name || adv.name || '';
                return name === displayedText || name.includes(displayedText) || displayedText.includes(name);
              });
              
              // 方法2: 如果 window 中没有，尝试从 Vue 实例中获取选项列表
              if (!matchedAdvertiser && vueInstance) {
                try {
                  if (vueInstance.options && Array.isArray(vueInstance.options)) {
                    matchedAdvertiser = vueInstance.options.find(opt => {
                      const label = opt.label || opt.advertiser_name || opt.name || '';
                      return label === displayedText || label.includes(displayedText) || displayedText.includes(label);
                    });
                  }
                } catch (e) {
                  // 忽略错误
                }
              }
              
              // 方法3: 如果还是没有找到，尝试从 DOM 中的选项元素查找
              if (!matchedAdvertiser) {
                const optionElements = selectEl.querySelectorAll('.el-select-dropdown__item, [role="option"]');
                for (const optionEl of optionElements) {
                  const optionText = optionEl.textContent?.trim() || '';
                  if (optionText === displayedText || optionText.includes(displayedText) || displayedText.includes(optionText)) {
                    // 尝试从选项元素中获取值
                    const optionValue = optionEl.getAttribute('data-value') || 
                                      optionEl.getAttribute('data-option-value') ||
                                      optionEl.getAttribute('value') ||
                                      optionEl.getAttribute('data-id');
                    if (optionValue) {
                      matchedAdvertiser = { id: optionValue, advertiser_name: displayedText };
                      break;
                    }
                  }
                }
              }
              
              if (matchedAdvertiser && matchedAdvertiser.id && vueInstance) {
                // 找到了匹配的广告主，尝试更新 Vue 状态
                const advertiserId = matchedAdvertiser.id;
                try {
                  if (typeof vueInstance.$emit === 'function') {
                    vueInstance.$emit('update:modelValue', advertiserId);
                  } else if (typeof vueInstance.emit === 'function') {
                    vueInstance.emit('update:modelValue', advertiserId);
                  }
                  // 触发 change 事件
                  const changeEvent = new Event('change', { bubbles: true, cancelable: true });
                  changeEvent.value = advertiserId;
                  selectEl.dispatchEvent(changeEvent);
                  
                  // 调试信息
                  if (window.DEBUG_SELECT) {
                    console.log('[fixSelectDisplay] 更新广告主值:', {
                      displayedText,
                      advertiserId,
                      matchedAdvertiser
                    });
                  }
                } catch (e) {
                  // 忽略错误，继续其他修复
                  if (window.DEBUG_SELECT) {
                    console.warn('[fixSelectDisplay] 更新广告主值失败:', e);
                  }
                }
              }
            } catch (e) {
              // 忽略错误
              if (window.DEBUG_SELECT) {
                console.warn('[fixSelectDisplay] 查找广告主失败:', e);
              }
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
      // Vue 值为 null 或 undefined
      // 只有当检测到明确的选中值信号时，才认为有选中值
      // 清除按钮是最可靠的信号
      if (hasClearButton) {
        hasSelectedValue = true;
      } else if (hasVisibleText || hasSelectedTags || hasInputValue) {
        // 有其他信号表明有选中值
        hasSelectedValue = true;
      } else {
        // 没有明确的选中值信号，认为没有选中值
        hasSelectedValue = false;
        
        // 关键修复：如果 placeholder 文本是空的或者是部分 placeholder，确保恢复为完整的原始 placeholder
        if (placeholderEl && originalPlaceholder) {
          const currentText = placeholderEl.textContent?.trim() || '';
          // 如果 placeholder 文本是空的或者是原始 placeholder 的一部分，恢复为完整的原始 placeholder
          if (!currentText || 
              (currentText.length < originalPlaceholder.length && 
               currentText.length > 0 &&
               originalPlaceholder.startsWith(currentText))) {
            placeholderEl.textContent = originalPlaceholder;
          }
        }
      }
    } else {
      // 其他情况：使用其他检测方法
      // 注意：只有当 hasSelectedValue 还没有被明确设置时，才使用这个逻辑
      // 如果 hasSelectedValue 已经被设置为 false（比如检测到部分 placeholder），不应该被覆盖
      if (hasSelectedValue === undefined) {
        // 优先相信我们的检测结果，而不是 hasIsEmptyClass（因为 Element Plus 可能没有正确更新）
        // 只有当有明确的选中值信号时，才认为有选中值
        if (hasClearButton || hasVisibleText || hasSelectedTags || hasInputValue) {
          hasSelectedValue = true;
        } else {
          // 没有任何选中值信号，认为没有选中值
          hasSelectedValue = false;
        }
      }
    }
    
    // 如果仍然是 undefined，默认认为没有选中值（安全起见）
    if (hasSelectedValue === undefined) {
      hasSelectedValue = false;
    }
    
    // 调试信息（仅在需要时）
    if (window.DEBUG_SELECT && currentPlaceholderText === '请选择' && originalPlaceholder && originalPlaceholder.includes('请选择')) {
      console.log('[fixSelectDisplay] 检测到部分 placeholder:', {
        currentPlaceholderText,
        originalPlaceholder,
        modelValue,
        hasClearButton,
        hasVisibleText,
        hasSelectedTags,
        hasInputValue,
        hasSelectedValue,
        hasIsEmptyClass
      });
    }
    
    // 最终检查：如果 Vue modelValue 是 null，且没有清除按钮，且 placeholder 是空的或部分的，肯定没有选中值
    // 这个检查的优先级最高，确保不会误判
    if (modelValue === null && 
        !hasClearButton && 
        !hasVisibleText && 
        !hasSelectedTags && 
        !hasInputValue &&
        (isEmptyPlaceholder || isPartialPlaceholder || 
         (currentPlaceholderText && currentPlaceholderText !== originalPlaceholder && 
          originalPlaceholder && originalPlaceholder.startsWith(currentPlaceholderText)))) {
      // 这种情况下，肯定没有选中值
      hasSelectedValue = false;
      // 恢复 placeholder
      if (placeholderEl && originalPlaceholder) {
        const currentText = placeholderEl.textContent?.trim() || '';
        if (currentText !== originalPlaceholder) {
          placeholderEl.textContent = originalPlaceholder;
        }
      }
    }
    
    // 强制检查：如果 Vue modelValue 是 null，且 placeholder 文本不完整，强制认为没有选中值
    // 这个检查必须在最后执行，确保优先级最高
    if (modelValue === null && 
        currentPlaceholderText && 
        originalPlaceholder &&
        currentPlaceholderText.length < originalPlaceholder.length &&
        currentPlaceholderText.length > 0 &&
        originalPlaceholder.startsWith(currentPlaceholderText) &&
        !hasClearButton &&
        !hasVisibleText &&
        !hasSelectedTags &&
        !hasInputValue) {
      // 强制设置为没有选中值
      hasSelectedValue = false;
      if (placeholderEl && placeholderEl.textContent !== originalPlaceholder) {
        placeholderEl.textContent = originalPlaceholder;
      }
    }
    
    // 最终强制检查：如果 placeholder 文本是 "请选择" 而原始 placeholder 是 "请选择广告主"，肯定没有选中值
    // 这个检查必须在所有其他检查之后，优先级最高
    if (modelValue === null && 
        currentPlaceholderText && 
        originalPlaceholder && 
        originalPlaceholder.includes('请选择') &&
        currentPlaceholderText.length < originalPlaceholder.length &&
        currentPlaceholderText.length > 0 &&
        originalPlaceholder.startsWith(currentPlaceholderText) &&
        !hasClearButton &&
        !hasVisibleText &&
        !hasSelectedTags &&
        !hasInputValue) {
      // 强制设置为没有选中值，覆盖之前的所有判断
      hasSelectedValue = false;
      if (placeholderEl && placeholderEl.textContent !== originalPlaceholder) {
        placeholderEl.textContent = originalPlaceholder;
      }
    }
    
    // 额外检查：如果 placeholder 文本是 "请选择"（常见的不完整 placeholder），肯定没有选中值
    // 这个检查必须在 if (hasSelectedValue) 之前，确保优先级最高
    if (modelValue === null && 
        currentPlaceholderText === '请选择' && 
        originalPlaceholder && 
        originalPlaceholder !== '请选择' &&
        originalPlaceholder.length > currentPlaceholderText.length &&
        !hasClearButton &&
        !hasVisibleText &&
        !hasSelectedTags &&
        !hasInputValue) {
      // 强制设置为没有选中值，覆盖之前的所有判断
      hasSelectedValue = false;
      if (placeholderEl && placeholderEl.textContent !== originalPlaceholder) {
        placeholderEl.textContent = originalPlaceholder;
      }
    }
    
    // 最终强制覆盖：如果所有信号都表明没有选中值，强制设置为 false
    // 这个检查必须在 if (hasSelectedValue) 之前，确保优先级最高
    if (hasSelectedValue && 
        modelValue === null && 
        !hasClearButton && 
        !hasVisibleText && 
        !hasSelectedTags && 
        !hasInputValue &&
        currentPlaceholderText &&
        originalPlaceholder &&
        currentPlaceholderText.length < originalPlaceholder.length &&
        currentPlaceholderText.length > 0 &&
        originalPlaceholder.startsWith(currentPlaceholderText)) {
      // 即使之前判断为有选中值，也要强制改为没有选中值
      hasSelectedValue = false;
      if (placeholderEl && placeholderEl.textContent !== originalPlaceholder) {
        placeholderEl.textContent = originalPlaceholder;
      }
    }
    
    if (hasSelectedValue) {
      // 强制移除 is-empty 类（这是关键！）
      selectEl.classList.remove('is-empty');
      
      // 如果检测到选中值被错误地放在 placeholder 中，需要将其移动到正确位置
      if (displayedText && displayedText !== originalPlaceholder && inputWrapper) {
        // 检查是否有显示选中值的元素
        let selectionEl = inputWrapper.querySelector('.el-select__selection') ||
                         inputWrapper.querySelector('.el-select__selected-item') ||
                         inputWrapper.querySelector('[class*="selection"]');
        
        // 如果没有找到选中值显示元素，尝试创建或更新
        if (!selectionEl) {
          // 方法1: 尝试在 input wrapper 中创建选中值显示元素
          const inputEl = inputWrapper.querySelector('input');
          if (inputEl) {
            // 尝试设置 input 的 value（某些情况下可能有效）
            try {
              if (inputEl.type !== 'hidden') {
                inputEl.value = displayedText;
              }
            } catch (e) {
              // 忽略错误
            }
            
            // 方法2: 尝试在 input 前插入一个显示选中值的元素
            try {
              const displaySpan = document.createElement('span');
              displaySpan.className = 'el-select__selected-item';
              displaySpan.textContent = displayedText;
              displaySpan.style.cssText = `
                position: relative;
                z-index: 102;
                color: var(--el-text-color-regular);
                opacity: 1;
                visibility: visible;
              `;
              inputEl.parentNode.insertBefore(displaySpan, inputEl);
              selectionEl = displaySpan;
            } catch (e) {
              // 忽略错误
            }
          }
        } else {
          // 如果找到了选中值元素，确保它的文本是正确的
          if (selectionEl.textContent?.trim() !== displayedText) {
            selectionEl.textContent = displayedText;
          }
          // 确保选中值元素可见
          selectionEl.style.cssText = `
            opacity: 1 !important;
            visibility: visible !important;
            z-index: 102 !important;
            position: relative !important;
            display: block !important;
            color: var(--el-text-color-regular) !important;
          `;
        }
      } else if (hasClearButton && !displayedText && inputWrapper) {
        // 如果有清除按钮但没有找到选中文本，尝试从其他方式获取
        // 这可能是因为选中值在某个隐藏的元素中
        const allElements = inputWrapper.querySelectorAll('*');
        for (const el of allElements) {
          if (el !== placeholderEl && !el.classList.contains('el-select__placeholder')) {
            const text = el.textContent?.trim() || '';
            if (text && 
                text !== originalPlaceholder && 
                !originalPlaceholder.startsWith(text) &&
                text.length > 0) {
              displayedText = text;
              // 确保这个元素可见
              el.style.cssText = `
                opacity: 1 !important;
                visibility: visible !important;
                z-index: 102 !important;
                position: relative !important;
                display: block !important;
                color: var(--el-text-color-regular) !important;
              `;
              break;
            }
          }
        }
      }
      
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
          // 确保选中值元素可见，z-index 要足够高，不被 tooltip 遮盖
          selectionEl.style.cssText = `
            opacity: 1 !important;
            visibility: visible !important;
            z-index: 102 !important;
            position: relative !important;
            display: block !important;
            color: var(--el-text-color-regular) !important;
            background: transparent !important;
          `;
        }
        
        // 确保 input 元素可见，z-index 要足够高，不被 tooltip 遮盖
        const inputs = inputWrapper.querySelectorAll('input');
        inputs.forEach(input => {
          input.style.cssText = `
            opacity: 1 !important;
            visibility: visible !important;
            color: var(--el-text-color-regular) !important;
            z-index: 102 !important;
            position: relative !important;
            display: block !important;
            background: transparent !important;
          `;
        });
        
        // 确保所有非 placeholder 的子元素可见
        const children = inputWrapper.children;
        for (let i = 0; i < children.length; i++) {
          const child = children[i];
          if (child !== placeholderEl && !child.classList.contains('el-select__placeholder')) {
            const childText = child.textContent?.trim() || '';
            // 如果子元素有文本，且不是原始 placeholder，确保可见
            // z-index 要足够高，不被 tooltip 遮盖
            if (childText && childText !== originalPlaceholder) {
              child.style.cssText = `
                opacity: 1 !important;
                visibility: visible !important;
                z-index: 102 !important;
                position: relative !important;
                display: block !important;
                color: var(--el-text-color-regular) !important;
                background: transparent !important;
              `;
            }
          }
        }
      }
    } else {
      // 如果没有选中值，添加 is-empty 类并显示 placeholder
      // 强制添加 is-empty 类（使用多种方法确保生效）
      selectEl.classList.add('is-empty');
      // 如果 classList.add 没有生效，使用 setAttribute 强制设置
      if (!selectEl.classList.contains('is-empty')) {
        const currentClass = selectEl.getAttribute('class') || '';
        if (!currentClass.includes('is-empty')) {
          selectEl.setAttribute('class', currentClass.trim() + ' is-empty');
        }
      }
      // 再次检查，确保 is-empty 类存在
      if (!selectEl.classList.contains('is-empty')) {
        selectEl.className = (selectEl.className || '').trim() + ' is-empty';
      }
      
      // 确保 placeholder 文本是完整的原始 placeholder
      // 尝试获取原始 placeholder（多种方式）
      let finalPlaceholder = originalPlaceholder;
      
      // 如果 originalPlaceholder 是 "请选择" 或不完整，尝试从其他方式获取
      if (!finalPlaceholder || finalPlaceholder === '请选择' || finalPlaceholder.length <= 3) {
        // 方法1: 从 DOM 属性获取
        finalPlaceholder = selectEl.getAttribute('placeholder') || 
                         selectEl.querySelector('[placeholder]')?.getAttribute('placeholder') || '';
        
        // 方法2: 从 Vue 实例获取
        if ((!finalPlaceholder || finalPlaceholder === '请选择') && vueInstance) {
          try {
            const props = vueInstance.props || vueInstance.$props || vueInstance.propsData || {};
            const propsPlaceholder = props.placeholder;
            if (propsPlaceholder && propsPlaceholder !== '请选择' && propsPlaceholder.length > 3) {
              finalPlaceholder = propsPlaceholder;
            }
            
            // 尝试从 setupState 获取
            if ((!finalPlaceholder || finalPlaceholder === '请选择') && vueInstance.setupState) {
              const setupPlaceholder = vueInstance.setupState.placeholder;
              if (setupPlaceholder && setupPlaceholder !== '请选择' && setupPlaceholder.length > 3) {
                finalPlaceholder = setupPlaceholder;
              }
            }
            
            // 尝试从 ctx 获取
            if ((!finalPlaceholder || finalPlaceholder === '请选择') && vueInstance.ctx) {
              const ctxPlaceholder = vueInstance.ctx.placeholder || vueInstance.ctx.$attrs?.placeholder;
              if (ctxPlaceholder && ctxPlaceholder !== '请选择' && ctxPlaceholder.length > 3) {
                finalPlaceholder = ctxPlaceholder;
              }
            }
          } catch (e) {
            // 忽略错误
          }
        }
        
        // 方法3: 如果还是 "请选择"，尝试从其他 el-select 中查找完整的 placeholder
        if (finalPlaceholder === '请选择') {
          const otherSelects = document.querySelectorAll('.el-select');
          for (const otherSelect of otherSelects) {
            if (otherSelect !== selectEl) {
              const otherPlaceholder = otherSelect.getAttribute('placeholder');
              if (otherPlaceholder && otherPlaceholder.includes('请选择') && otherPlaceholder.length > 3) {
                // 检查是否是同一个组件（通过检查父元素或样式）
                const otherParent = otherSelect.closest('[data-v-4ef97251]');
                const currentParent = selectEl.closest('[data-v-4ef97251]');
                if (otherParent === currentParent || 
                    (otherSelect.style.width === selectEl.style.width && 
                     otherSelect.style.marginLeft === selectEl.style.marginLeft)) {
                  finalPlaceholder = otherPlaceholder;
                  break;
                }
              }
            }
          }
        }
        
        // 方法4: 如果还是 "请选择"，尝试从常见的完整 placeholder 推断
        // 检查当前页面的上下文，推断可能的完整 placeholder
        if (finalPlaceholder === '请选择') {
          // 检查是否有 "广告主" 相关的文本，推断为 "请选择广告主"
          const pageText = document.body.innerText || '';
          if (pageText.includes('广告主') || pageText.includes('advertiser')) {
            finalPlaceholder = '请选择广告主';
          } else if (pageText.includes('客户') || pageText.includes('customer')) {
            finalPlaceholder = '请选择客户';
          } else if (pageText.includes('供应商') || pageText.includes('supplier')) {
            finalPlaceholder = '请选择供应商';
          }
        }
      }
      
      if (placeholderEl && finalPlaceholder && finalPlaceholder !== '请选择') {
        const currentText = placeholderEl.textContent?.trim() || '';
        // 如果 placeholder 文本是空的、是原始 placeholder 的一部分，或者不是完整的原始 placeholder，恢复为完整的原始 placeholder
        if (!currentText || 
            currentText !== finalPlaceholder ||
            (currentText.length < finalPlaceholder.length && 
             currentText.length > 0 &&
             finalPlaceholder.startsWith(currentText))) {
          placeholderEl.textContent = finalPlaceholder;
          
          // 调试信息
          if (window.DEBUG_SELECT) {
            console.log('[fixSelectDisplay] 恢复 placeholder:', {
              currentText,
              finalPlaceholder,
              originalPlaceholder
            });
          }
        }
      } else if (placeholderEl && finalPlaceholder === '请选择') {
        // 如果 finalPlaceholder 仍然是 "请选择"，但当前文本也是 "请选择"，尝试从 DOM 中查找
        const currentText = placeholderEl.textContent?.trim() || '';
        if (currentText === '请选择') {
          // 检查是否有其他线索可以推断完整的 placeholder
          // 比如从附近的 label 或其他元素
          const labelEl = selectEl.previousElementSibling || 
                         selectEl.parentElement?.querySelector('label');
          if (labelEl) {
            const labelText = labelEl.textContent?.trim() || '';
            if (labelText.includes('广告主')) {
              placeholderEl.textContent = '请选择广告主';
            } else if (labelText.includes('客户')) {
              placeholderEl.textContent = '请选择客户';
            }
          }
        }
      }
      
      if (placeholderEl) {
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

// 导出到 window 对象，供全局使用（确保在全局作用域中）
if (typeof window !== 'undefined') {
  window.fixSelectDisplay = fixSelectDisplay;
  window.debugSelectDisplay = debugSelectDisplay;
  
  // 确保函数在页面加载后立即可用
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      window.fixSelectDisplay = fixSelectDisplay;
      window.debugSelectDisplay = debugSelectDisplay;
    });
  }
}

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
    // 防抖：100ms 内只执行最后一次（缩短时间，更快响应）
    mutationTimeout = setTimeout(() => {
      fixSelectInputs();
      fixDatePickerInputs();
      fixOtherFormInputs();
      // 只在有 el-select 元素时才调用 fixSelectDisplay
      if (document.querySelector('.el-select')) {
        fixSelectDisplay();
      }
    }, 100);
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
  
  // 专门监听 el-select 的 is-empty 类变化，确保当类被移除时能立即修复
  const selectObserver = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
        const target = mutation.target;
        if (target.classList.contains('el-select')) {
          // 检查 is-empty 类是否被移除
          const hadIsEmpty = mutation.oldValue && mutation.oldValue.includes('is-empty');
          const hasIsEmpty = target.classList.contains('is-empty');
          
          // 如果 is-empty 类被移除了，立即检查并修复
          if (hadIsEmpty && !hasIsEmpty) {
            // 延迟一点执行，避免与 Element Plus 的内部逻辑冲突
            setTimeout(() => {
              fixSelectDisplay();
            }, 10);
          }
        }
      }
    });
  });
  
  // 观察所有 el-select 元素的 class 变化
  document.querySelectorAll('.el-select').forEach((selectEl) => {
    selectObserver.observe(selectEl, {
      attributes: true,
      attributeFilter: ['class'],
      attributeOldValue: true // 记录旧值，用于检测 is-empty 类是否被移除
    });
  });
  
  // 当新的 el-select 元素被添加到 DOM 时，也观察它们
  const selectObserver2 = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === 1) { // Element node
          if (node.classList && node.classList.contains('el-select')) {
            selectObserver.observe(node, {
              attributes: true,
              attributeFilter: ['class'],
              attributeOldValue: true
            });
          }
          // 检查子元素
          const childSelects = node.querySelectorAll && node.querySelectorAll('.el-select');
          if (childSelects) {
            childSelects.forEach((selectEl) => {
              selectObserver.observe(selectEl, {
                attributes: true,
                attributeFilter: ['class'],
                attributeOldValue: true
              });
            });
          }
        }
      });
    });
  });
  
  selectObserver2.observe(document.body, {
    childList: true,
    subtree: true
  });
  
  // 监听所有 el-select 的 change 事件（立即执行，然后延迟再执行一次确保修复）
  let changeTimeout = null;
  document.addEventListener('change', (e) => {
    if (e.target.closest('.el-select')) {
      // 立即执行一次修复
      fixSelectDisplay();
      // 清除之前的定时器
      if (changeTimeout) {
        clearTimeout(changeTimeout);
      }
      // 延迟再执行一次，确保 DOM 更新后也能修复
      changeTimeout = setTimeout(() => {
        fixSelectDisplay();
      }, 50);
      // 再延迟一次，确保所有更新都完成
      setTimeout(() => {
        fixSelectDisplay();
      }, 200);
    }
  }, true);
  
  // 监听所有 el-select 的 click 事件（选择选项时，立即执行）
  let clickTimeout = null;
  document.addEventListener('click', (e) => {
    if (e.target.closest('.el-select-dropdown__item')) {
      // 立即执行一次修复
      fixSelectDisplay();
      // 清除之前的定时器
      if (clickTimeout) {
        clearTimeout(clickTimeout);
      }
      // 延迟再执行一次，确保 DOM 更新后也能修复
      clickTimeout = setTimeout(() => {
        fixSelectDisplay();
      }, 50);
      // 再延迟一次，确保所有更新都完成
      setTimeout(() => {
        fixSelectDisplay();
      }, 200);
      // 再延迟一次，确保 Vue 状态更新后也能修复
      setTimeout(() => {
        fixSelectDisplay();
      }, 500);
    }
  }, true);
  
  // 监听 el-select 的下拉选项点击事件（更精确的监听）
  document.addEventListener('mousedown', (e) => {
    const dropdownItem = e.target.closest('.el-select-dropdown__item');
    if (dropdownItem) {
      // 立即执行修复
      fixSelectDisplay();
      // 延迟执行，确保选择完成
      setTimeout(() => {
        fixSelectDisplay();
      }, 100);
      setTimeout(() => {
        fixSelectDisplay();
      }, 300);
      setTimeout(() => {
        fixSelectDisplay();
      }, 600);
    }
  }, true);
  
  // 监听 placeholder 文本变化（通过 MutationObserver）
  const placeholderObserver = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'childList' || mutation.type === 'characterData') {
        const target = mutation.target;
        if (target.classList && target.classList.contains('el-select__placeholder')) {
          // placeholder 文本变化，立即修复
          fixSelectDisplay();
          // 延迟再执行一次
          setTimeout(() => {
            fixSelectDisplay();
          }, 50);
        }
      }
    });
  });
  
  // 观察所有 placeholder 元素的变化
  const observePlaceholders = () => {
    const placeholders = document.querySelectorAll('.el-select__placeholder');
    placeholders.forEach((placeholder) => {
      placeholderObserver.observe(placeholder, {
        childList: true,
        characterData: true,
        subtree: true
      });
    });
  };
  
  // 初始观察
  setTimeout(observePlaceholders, 100);
  
  // 当有新的 placeholder 创建时，也观察它
  const placeholderMutationObserver = new MutationObserver(() => {
    observePlaceholders();
  });
  placeholderMutationObserver.observe(document.body, {
    childList: true,
    subtree: true
  });
  
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
