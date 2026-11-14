/**
 * 全局错误处理模块
 * 捕获 JavaScript 运行时错误和未处理的 Promise 拒绝
 */
import { isExtensionError } from './errorFilter';
import { logger } from './logger';

/**
 * ResizeObserver 在布局抖动时的浏览器已知良性告警（非业务故障）。
 * Chrome 旧版：ResizeObserver loop limit exceeded
 * Chrome 新版：ResizeObserver loop completed with undelivered notifications
 */
function isBenignResizeObserverError(message = '') {
  const text = String(message || '');
  return text.includes('ResizeObserver loop limit exceeded')
    || text.includes('ResizeObserver loop completed with undelivered notifications');
}

/**
 * 鉴权失败 / 已由 axios 拦截器处理的请求错误，不应记为「程序运行错误」。
 * 典型文案：Request failed with status code 401
 */
function isAuthOrHandledRequestError(errorLike, message = '') {
  const status = errorLike?.response?.status
    ?? errorLike?.status
    ?? errorLike?.statusCode;
  if (status === 401 || status === 403) {
    return true;
  }
  if (errorLike?._handled) {
    return true;
  }
  const text = String(message || errorLike?.message || '');
  if (/status code 401\b/i.test(text) || /status code 403\b/i.test(text)) {
    return true;
  }
  if (/登录已过期|未登录|令牌|Not authenticated|Unauthorized/i.test(text)) {
    return true;
  }
  return false;
}

/**
 * 记录前端错误到后端
 */
async function recordFrontendError(errorInfo) {
  try {
    // 使用全局 axios（initAxiosConfig 已设置 withCredentials，可带 Cookie / CSRF）
    const axios = (await import('axios')).default;
    const payload = {
      error_type: errorInfo.error_type || 'JavaScriptError',
      error_message: errorInfo.error_message || '未知错误',
      ...(errorInfo.error_stack && { error_stack: errorInfo.error_stack }),
      ...(errorInfo.error_url && { error_url: errorInfo.error_url }),
      ...(errorInfo.user_agent && { user_agent: errorInfo.user_agent })
    };

    // 错误消息/堆栈放在 JSON 请求体，避免进入 URL、代理访问日志与浏览器历史。
    await axios.post('/api/v1/audit-logs/client-error', payload, {
      timeout: 5000,
      skipErrorMessage: true,
      silent: true,
    });
  } catch (error) {
    if (import.meta.env.DEV) {
      logger.debug('记录前端错误失败:', error);
    }
  }
}

/**
 * 初始化全局错误处理器
 */
export const initGlobalErrorHandler = () => {
  // 捕获JavaScript运行时错误
  window.addEventListener('error', (event) => {
    const errorMessage = event?.message || event?.error?.message || '';
    const errorFilename = event?.filename || '';
    const errorString = String(errorMessage).toLowerCase();
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
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      return false;
    }

    if (typeof errorMessage === 'string' && errorMessage.includes('ElOnlyChild')) {
      return;
    }

    if (isBenignResizeObserverError(errorMessage)) {
      event.preventDefault?.();
      return;
    }

    // 忽略 inspector.js 中关于 responseText 的错误
    const isInspectorFile = typeof errorFilename === 'string' && errorFilename.includes('inspector.js');
    const isResponseTextError = typeof errorMessage === 'string' && (
      (errorMessage.includes('responseText') && errorMessage.includes('responseType')) ||
      errorMessage.includes('Failed to read') && errorMessage.includes('responseText') ||
      (errorMessage.includes('InvalidStateError') && errorMessage.includes('responseText')) ||
      errorMessage.includes('The value is only accessible if the object\'s \'responseType\'')
    );
    const isInvalidStateError = errorName === 'InvalidStateError' || errorMessage.includes('InvalidStateError');

    if (isInspectorFile || (isResponseTextError && isInvalidStateError)) {
      event.preventDefault();
      return;
    }

    if (isAuthOrHandledRequestError(event?.error, errorMessage)) {
      return;
    }

    // 记录前端运行错误
    try {
      const error = event.error || new Error(event.message);
      const errorType = error.name || 'Error';
      const errorMsg = error.message || event.message || '未知错误';
      const errorStack = error.stack || '';
      const errorUrl = event.filename || window.location.href;

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
      logger.error('记录前端错误失败:', e);
    }
  });

  // 捕获未处理的Promise拒绝
  window.addEventListener('unhandledrejection', (event) => {
    const errorMessage = event?.reason?.message || event?.reason?.toString() || '';
    const errorStack = event?.reason?.stack || '';
    const errorName = event?.reason?.name || '';

    // 忽略 inspector.js 中关于 responseText 的错误
    const isInspectorError = typeof errorStack === 'string' && errorStack.includes('inspector.js');
    const isResponseTextError = typeof errorMessage === 'string' && (
      (errorMessage.includes('responseText') && errorMessage.includes('responseType')) ||
      errorMessage.includes('Failed to read') && errorMessage.includes('responseText') ||
      (errorMessage.includes('InvalidStateError') && errorMessage.includes('responseText')) ||
      errorMessage.includes('The value is only accessible if the object\'s \'responseType\'')
    );
    const isInvalidStateError = errorName === 'InvalidStateError' ||
      (typeof errorMessage === 'string' && errorMessage.includes('InvalidStateError'));

    if (isInspectorError || (isResponseTextError && isInvalidStateError)) {
      event.preventDefault();
      return;
    }

    // 忽略浏览器扩展相关的错误
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
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (typeof errorMessage === 'string' && errorMessage.includes('ElOnlyChild')) {
      return;
    }

    if (isBenignResizeObserverError(errorMessage)) {
      event.preventDefault?.();
      return;
    }

    // 401/403：登录过期等，axios 已处理，勿记为程序运行错误
    if (isAuthOrHandledRequestError(event?.reason, errorMessage)) {
      event.preventDefault();
      return;
    }

    // 记录前端运行错误
    try {
      const error = event.reason || new Error('Unhandled Promise Rejection');
      const errorType = error.name || 'UnhandledRejection';
      const errorMsg = error.message || String(event.reason) || '未处理的Promise拒绝';
      const errorStack = error.stack || '';
      const errorUrl = window.location.href;

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
      logger.error('记录前端错误失败:', e);
    }
  });
};

