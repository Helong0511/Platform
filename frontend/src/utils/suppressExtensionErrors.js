/**
 * 抑制浏览器扩展相关的错误和警告
 * 这些错误通常由广告拦截器、开发者工具扩展等引起，不影响应用功能
 */

/**
 * 抑制 runtime.lastError 警告
 * 这个警告通常由浏览器扩展引起，不是代码问题
 */
export function suppressExtensionErrors() {
  // 拦截 console.error 中的扩展相关错误
  const originalError = console.error;
  console.error = function(...args) {
    const message = args.join(' ');
    const lowerMessage = message.toLowerCase();
    
    // 忽略浏览器扩展相关的错误
    if (
      lowerMessage.includes('runtime.lasterror') ||
      lowerMessage.includes('runtime.lasterror') ||
      lowerMessage.includes('message port closed') ||
      lowerMessage.includes('port closed before a response') ||
      lowerMessage.includes('unchecked runtime.lasterror') ||
      lowerMessage.includes('message channel closed') ||
      lowerMessage.includes('asynchronous response')
    ) {
      // 静默忽略，不输出到控制台
      return;
    }
    
    // 其他错误正常输出
    originalError.apply(console, args);
  };

  // 拦截 console.warn 中的扩展相关警告
  const originalWarn = console.warn;
  console.warn = function(...args) {
    const message = args.join(' ');
    const lowerMessage = message.toLowerCase();
    
    // 忽略浏览器扩展相关的警告
    if (
      lowerMessage.includes('runtime.lasterror') ||
      lowerMessage.includes('runtime.lasterror') ||
      lowerMessage.includes('message port closed') ||
      lowerMessage.includes('port closed before a response') ||
      lowerMessage.includes('unchecked runtime.lasterror')
    ) {
      // 静默忽略，不输出到控制台
      return;
    }
    
    // 其他警告正常输出
    originalWarn.apply(console, args);
  };
}

