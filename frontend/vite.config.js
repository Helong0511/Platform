import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { versionPlugin } from './vite-plugin-version.js'
import { copyFileSync, existsSync, mkdirSync } from 'fs'
import { resolve } from 'path'

// 自定义插件：构建后复制 favicon.ico
const copyFaviconPlugin = {
  name: 'copy-favicon',
  closeBundle() {
    const faviconSrc = resolve(__dirname, 'favicon.ico');
    const faviconDest = resolve(__dirname, 'dist', 'favicon.ico');
    
    // 确保 dist 目录存在
    const distDir = resolve(__dirname, 'dist');
    if (!existsSync(distDir)) {
      mkdirSync(distDir, { recursive: true });
    }
    
    // 复制 favicon.ico
    if (existsSync(faviconSrc)) {
      copyFileSync(faviconSrc, faviconDest);
      console.log('✅ favicon.ico 已复制到 dist 目录');
    } else {
      console.warn('⚠️  favicon.ico 源文件不存在');
    }
  }
};

// https://vite.dev/config/
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 3310,
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        // 连接超时设置（增加到60秒，应该大于前端请求的timeout）
        timeout: 60000,
        // 错误处理
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            // 代理错误已处理
          });
        }
      }
    }
  },

  build: {
    // 构建配置优化
    chunkSizeWarningLimit: 1500,
    // 使用 esbuild 压缩（比 terser 快 10-100 倍）
    minify: 'esbuild',
    // esbuild 压缩选项（比 terser 快很多）
    esbuild: {
      drop: ['console', 'debugger'],  // 移除 console 和 debugger
    },
    // 生产环境禁用source map（防止源码泄露，加快构建速度）
    sourcemap: false,
    // 代码分割优化
    rollupOptions: {
      output: {
        // 手动分包，提高缓存效率
        manualChunks: (id) => {
          // Vue 核心库
          if (id.includes('node_modules/vue') || id.includes('node_modules/vue-router') || id.includes('node_modules/pinia')) {
            return 'vue-vendor';
          }
          // Element Plus
          if (id.includes('node_modules/element-plus')) {
            return 'element-plus';
          }
          // Axios
          if (id.includes('node_modules/axios')) {
            return 'axios';
          }
          // ECharts
          if (id.includes('node_modules/echarts')) {
            return 'echarts';
          }
          // 其他 node_modules
          if (id.includes('node_modules')) {
            return 'vendor';
          }
          // 为特定页面创建独立的 chunk，确保命名稳定
          if (id.includes('/views/AdData.vue')) {
            return 'ad-data';
          }
          if (id.includes('/views/ad-data/DailyReport.vue')) {
            return 'daily-report';
          }
        },
        // 优化 chunk 文件名
        // 使用稳定的命名策略，确保动态导入的模块能够正确加载
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
        assetFileNames: 'assets/[ext]/[name]-[hash].[ext]',
      },
    },
    // 禁用压缩大小报告（加快构建速度）
    reportCompressedSize: false,
    // 设置构建目标（现代浏览器，减少转译）
    target: 'es2015',
    // 启用 CSS 代码分割
    cssCodeSplit: true,
    // 减少构建输出信息（加快构建速度）
    emptyOutDir: true,
  },

  plugins: [
    vue(),
    versionPlugin(), // 版本文件生成插件
    copyFaviconPlugin, // 复制 favicon.ico 插件
  ],

  // 优化配置
  optimizeDeps: {
    // 预构建依赖
    include: ['vue', 'vue-router', 'pinia', 'element-plus', 'axios'],
  },

})
