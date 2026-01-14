<script setup>
import { RouterView } from 'vue-router';
import { onMounted, onBeforeUnmount } from 'vue';

// 检查是否是浏览器扩展相关的错误（统一函数）
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

// 错误处理函数 - 专门处理浏览器扩展相关的错误
const handleError = (event) => {
  const errorMessage = event?.message || event?.error?.message || '';
  
  // 忽略浏览器扩展相关的错误（Edge 浏览器扩展可能引起的错误）
  // 检查错误消息、错误名称和文件名
  const errorName = event?.error?.name || '';
  const errorFilename = event?.filename || '';
  const errorStack = event?.error?.stack || '';
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
    errorStack.includes('edge-extension') ||
    errorStack.includes('content.js') ||
    errorStack.includes('content-script')
  );
  
  if (isExtensionErrorMsg || isExtensionFile || isExtensionStack || errorName === 'ExtensionError') {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    return true;
  }
  return false;
};

const handleRejection = (event) => {
  const errorMessage = event?.reason?.message || event?.reason?.toString() || '';
  
  // 忽略浏览器扩展相关的错误
  // 检查错误消息、错误名称和堆栈信息
  const errorName = event?.reason?.name || '';
  const errorStack = event?.reason?.stack || '';
  const isExtensionErrorMsg = isExtensionError(errorMessage);
  const isExtensionStack = typeof errorStack === 'string' && (
    errorStack.includes('extension') ||
    errorStack.includes('chrome-extension') ||
    errorStack.includes('moz-extension') ||
    errorStack.includes('safari-extension') ||
    errorStack.includes('edge-extension')
  );
  const isExtensionReason = event?.reason && typeof event.reason === 'object' && (
    isExtensionError(String(event.reason.message || '')) ||
    isExtensionError(String(event.reason.toString || ''))
  );
  
  if (isExtensionErrorMsg || isExtensionStack || isExtensionReason || errorName === 'ExtensionError') {
    event.preventDefault();
    event.stopPropagation();
    return true;
  }
  return false;
};

onMounted(() => {
  // 在应用挂载时添加错误监听器（使用 capture 模式，确保优先处理）
  window.addEventListener('error', handleError, true);
  window.addEventListener('unhandledrejection', handleRejection, true);
});

onBeforeUnmount(() => {
  // 清理错误监听器
  window.removeEventListener('error', handleError, true);
  window.removeEventListener('unhandledrejection', handleRejection, true);
});
</script>

<template>
  <RouterView />
</template>

<style scoped>
.logo {
  height: 6em;
  padding: 1.5em;
  will-change: filter;
  transition: filter 300ms;
}
.logo:hover {
  filter: drop-shadow(0 0 2em #646cffaa);
}
.logo.vue:hover {
  filter: drop-shadow(0 0 2em #42b883aa);
}
</style>
