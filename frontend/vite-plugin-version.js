import { writeFileSync, mkdirSync, existsSync } from 'fs';
import { resolve } from 'path';

/**
 * Vite 插件：在构建时生成版本文件，并将版本号注入 JS 包
 * 用于前端自动刷新检测（包内版本 vs 服务端 version.json）
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
