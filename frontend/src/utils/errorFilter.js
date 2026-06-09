/**
 * 检查是否是浏览器扩展相关的错误
 * @param {string} message - 错误消息
 * @returns {boolean} 如果是扩展错误返回true
 */
export const isExtensionError = (message) => {
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
    lowerMessage.includes('extension context invalidated') ||
    // 匹配完整的错误信息
    (lowerMessage.includes('listener indicated') && 
     lowerMessage.includes('asynchronous response') && 
     lowerMessage.includes('message channel closed')) ||
    // 匹配简化版本
    lowerMessage.includes('listener indicated an asynchronous response by returning true');
};

/**
 * 初始化控制台错误过滤
 * 过滤浏览器扩展相关的控制台错误
 */
export const initConsoleErrorFilter = () => {
  const originalConsoleError = console.error;
  const originalConsoleWarn = console.warn;

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
};

/**
 * 早期错误处理（在所有导入之前）
 * 捕获未处理的 Promise rejection（浏览器扩展相关）
 */
export const initEarlyErrorHandler = () => {
  if (typeof window !== 'undefined') {
    window.addEventListener('unhandledrejection', (event) => {
      const errorMessage = event?.reason?.message || event?.reason?.toString() || '';
      const errorString = String(errorMessage).toLowerCase();
      
      // 检查是否是浏览器扩展相关的错误
      if (isExtensionError(errorString)) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
    }, true); // 使用 capture 模式，确保优先处理
  }
};

