/**
 * Vite 插件：构建时生成 version.json，并将版本号注入 JS 包。
 * 供前端 versionCheck 对比包内版本与服务端版本，触发自动刷新。
 */
import { writeFileSync, mkdirSync, existsSync } from 'fs';
import { resolve } from 'path';

/**
 * 导出 versionPlugin 工厂函数，在 vite.config.js 中注册。
 */
export function versionPlugin() {
  let version = null;
  let buildTime = null;

  const ensureVersion = (forDev = false) => {
    if (forDev) {
      return 'dev';
    }
    if (!version) {
      version = Date.now().toString();
      buildTime = new Date().toISOString();
    }
    return version;
  };

  const writeVersionFile = () => {
    const versionData = {
      version: ensureVersion(),
      buildTime: buildTime || new Date().toISOString(),
    };

    const publicDir = resolve(__dirname, 'public');

    try {
      if (!existsSync(publicDir)) {
        mkdirSync(publicDir, { recursive: true });
      }

      const versionPath = resolve(publicDir, 'version.json');
      writeFileSync(versionPath, JSON.stringify(versionData, null, 2), 'utf-8');
      console.log(`✓ 版本文件已生成: ${versionPath}`);
    } catch (error) {
      console.warn('⚠ 生成版本文件失败:', error.message);
    }
  };

  return {
    name: 'version-plugin',
    config(_config, { command }) {
      const buildVersion = command === 'serve' ? 'dev' : ensureVersion();
      return {
        define: {
          __APP_VERSION__: JSON.stringify(buildVersion),
        },
      };
    },
    buildStart() {
      if (version) {
        writeVersionFile();
      }
    },
    generateBundle() {
      if (!version) {
        return;
      }

      const versionData = {
        version,
        buildTime,
      };

      this.emitFile({
        type: 'asset',
        fileName: 'version.json',
        source: JSON.stringify(versionData, null, 2),
      });
    },
  };
};
