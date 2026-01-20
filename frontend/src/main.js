// ====== 最早期的错误处理（在所有导入之前） ======
import { initEarlyErrorHandler, initConsoleErrorFilter } from './utils/errorFilter';
initEarlyErrorHandler();
initConsoleErrorFilter();

// Vue核心
import { createApp, nextTick } from 'vue';
import App from './App.vue';

// 第三方库
import axios from 'axios';
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import zhCn from 'element-plus/dist/locale/zh-cn.mjs';
import * as ElementPlusIconsVue from '@element-plus/icons-vue';

// 本地导入
import './style.css';
import './styles/mobile.css'; // 移动端优化样式
import { useViewportHeight, disableDoubleTapZoom } from './composables/useMobileTouch';
import pinia from './store';
import { useAuthStore, validateAuthData } from './store';
import router from './router/index.js';
import { initTimezone } from './utils/dateFormat';
import { initAxiosConfig } from './utils/axiosConfig';
import { initGlobalErrorHandler } from './utils/globalErrorHandler';
import { initDomFixes } from './utils/domFixes';
import { initCsrfTokenSync } from './utils/csrfToken';
import { initVersionCheck } from './utils/versionCheck';

// 创建Vue应用
const app = createApp(App);

// 注册Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}

// 初始化 Axios 配置
initAxiosConfig();

// 初始化 CSRF 令牌跨标签页同步机制
initCsrfTokenSync();

// 初始化全局错误处理器
initGlobalErrorHandler();

// 全局注册Axios
app.config.globalProperties.$axios = axios;

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
    
    // 初始化 DOM 修复
    initDomFixes();
    
    // 初始化版本检查（仅在生产环境或需要时启用）
    // 开发环境通常不需要，因为 Vite 已经有 HMR
    // 只在页面打开时检查一次，不进行定期检查
    if (import.meta.env.PROD) {
      initVersionCheck({
        enabled: true,
      });
    }
  }, 0);
});
