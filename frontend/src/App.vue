<script setup>
import { RouterView } from 'vue-router';
import { onMounted, onBeforeUnmount } from 'vue';

// 错误处理函数 - 专门处理浏览器扩展相关的错误
const handleError = (event) => {
  const errorMessage = event?.message || event?.error?.message || '';
  const errorString = String(errorMessage).toLowerCase();
  
  // 忽略浏览器扩展相关的错误（Edge 浏览器扩展可能引起的错误）
  // 检查错误消息、错误名称和文件名
  const errorName = event?.error?.name || '';
  const errorFilename = event?.filename || '';
  const isExtensionError = typeof errorMessage === 'string' && (
    errorString.includes('message channel closed') ||
    errorString.includes('asynchronous response') ||
    errorString.includes('listener indicated an asynchronous response') ||
    errorString.includes('message channel') ||
    errorString.includes('channel closed') ||
    errorString.includes('a listener indicated an asynchronous response') ||
    errorString.includes('but the message channel closed')
  );
  const isExtensionFile = typeof errorFilename === 'string' && (
    errorFilename.includes('extension') ||
    errorFilename.includes('chrome-extension') ||
    errorFilename.includes('moz-extension') ||
    errorFilename.includes('safari-extension') ||
    errorFilename.includes('edge-extension')
  );
  
  if (isExtensionError || isExtensionFile || errorName === 'ExtensionError') {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    return true;
  }
  return false;
};

const handleRejection = (event) => {
  const errorMessage = event?.reason?.message || event?.reason?.toString() || '';
  const errorString = String(errorMessage).toLowerCase();
  
  // 忽略浏览器扩展相关的错误
  // 检查错误消息、错误名称和堆栈信息
  const errorName = event?.reason?.name || '';
  const errorStack = event?.reason?.stack || '';
  const isExtensionError = typeof errorMessage === 'string' && (
    errorString.includes('message channel closed') ||
    errorString.includes('asynchronous response') ||
    errorString.includes('listener indicated an asynchronous response') ||
    errorString.includes('message channel') ||
    errorString.includes('channel closed') ||
    errorString.includes('a listener indicated an asynchronous response') ||
    errorString.includes('but the message channel closed')
  );
  const isExtensionStack = typeof errorStack === 'string' && (
    errorStack.includes('extension') ||
    errorStack.includes('chrome-extension') ||
    errorStack.includes('moz-extension') ||
    errorStack.includes('safari-extension') ||
    errorStack.includes('edge-extension')
  );
  const isExtensionReason = event?.reason && typeof event.reason === 'object' && (
    String(event.reason.message || '').toLowerCase().includes('message channel') ||
    String(event.reason.message || '').toLowerCase().includes('asynchronous response') ||
    String(event.reason.message || '').toLowerCase().includes('listener indicated') ||
    String(event.reason.message || '').toLowerCase().includes('channel closed')
  );
  
  if (isExtensionError || isExtensionStack || isExtensionReason || errorName === 'ExtensionError') {
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
