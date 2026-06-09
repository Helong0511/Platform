/**
 * Vue 应用入口
 * @file main.js
 *
 * 启动流程：
 * 1. 初始化 Axios 拦截器与全局错误处理
 * 2. 创建 Vue 实例，注册 Element Plus 及全部图标
 * 3. 挂载 Pinia、Router 后渲染根组件 App.vue
 * 4. 生产环境启用版本检查，发现新版本自动刷新
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
