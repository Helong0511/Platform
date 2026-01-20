import { writeFileSync, mkdirSync } from 'fs';
import { existsSync } from 'fs';
import { resolve } from 'path';

/**
 * Vite 插件：在构建时生成版本文件
 * 用于前端自动刷新检测
 */
export function versionPlugin() {
  return {
    name: 'version-plugin',
    buildStart() {
      // 生成版本号（使用时间戳）
      const version = Date.now().toString();
      const versionData = {
        version,
        buildTime: new Date().toISOString(),
      };

      // 将版本文件写入 public 目录（构建后会复制到 dist）
      const publicDir = resolve(__dirname, 'public');
      
      try {
        // 确保 public 目录存在
        if (!existsSync(publicDir)) {
          mkdirSync(publicDir, { recursive: true });
        }
        
        const versionPath = resolve(publicDir, 'version.json');
        writeFileSync(versionPath, JSON.stringify(versionData, null, 2), 'utf-8');
        console.log(`✓ 版本文件已生成: ${versionPath}`);
      } catch (error) {
        console.warn('⚠ 生成版本文件失败:', error.message);
      }
    },
    generateBundle() {
      // 在构建结束时再次生成版本文件（确保在 dist 目录中）
      // 使用新的时间戳，确保每次构建版本都不同
      const version = Date.now().toString();
      const versionData = {
        version,
        buildTime: new Date().toISOString(),
      };

      // 将版本信息作为静态资源输出到 dist 根目录
      this.emitFile({
        type: 'asset',
        fileName: 'version.json',
        source: JSON.stringify(versionData, null, 2),
      });
    },
  };
}
