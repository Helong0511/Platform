/**
 * 主入口文件（优化版）
 */
import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import pinia from './store';
import ElementPlus from 'element-plus';
import * as ElementPlusIconsVue from '@element-plus/icons-vue';
import zhCn from 'element-plus/dist/locale/zh-cn.mjs';
import 'element-plus/dist/index.css';
import './style.css';
import { initAxiosConfig } from './utils/axiosConfig';

// 初始化 Axios 配置（必须在创建 Vue 应用之前）
initAxiosConfig();

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

// 全局错误处理函数
const handleGlobalError = (event) => {
  const errorMessage = event?.message || event?.error?.message || '';
  
  // 忽略浏览器扩展相关的错误
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

// 全局未捕获Promise拒绝处理函数
const handleGlobalRejection = (event) => {
  const errorMessage = event?.reason?.message || event?.reason?.toString() || '';
  
  // 忽略浏览器扩展相关的错误
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

// 添加全局错误监听器
window.addEventListener('error', handleGlobalError, true);
window.addEventListener('unhandledrejection', handleGlobalRejection, true);

// 创建 Vue 实例
const app = createApp(App);

// 注册所有图标标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}

// 使用插件
app.use(pinia);
app.use(router);
app.use(ElementPlus, { locale: zhCn });

// 挂载应用
app.mount('#app');

console.log('应用启动成功');
