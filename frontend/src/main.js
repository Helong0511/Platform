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
