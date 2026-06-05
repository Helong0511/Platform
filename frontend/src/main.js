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
import { initGlobalErrorHandler } from './utils/globalErrorHandler';
import { initVersionCheck } from './utils/versionCheck';

// 初始化 Axios 配置（必须在创建 Vue 应用之前）
initAxiosConfig();
// 全局 JS 错误捕获 + 上报审计日志（含扩展错误过滤）
initGlobalErrorHandler();

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

// 生产环境：登录页对比包内版本与服务端 version.json，有更新则自动刷新
if (import.meta.env.PROD) {
  initVersionCheck({ enabled: true, showMessage: true, router });
}
