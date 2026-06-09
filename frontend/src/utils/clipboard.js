/**
 * 剪贴板复制工具。
 *
 * 优先使用 navigator.clipboard；不支持时回退到隐藏 textarea + document.execCommand。
 */
import { ElMessage } from 'element-plus';
import { logger } from './logger';

/**
 * 将文本复制到系统剪贴板
 * @param {string} text - 待复制的文本
 * @returns {Promise<void>} 复制成功弹出提示，失败显示错误消息
 */
export async function copyToClipboard(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success('已复制到剪贴板');
  } catch {
    try {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      const successful = document.execCommand('copy');
      document.body.removeChild(textArea);
      if (successful) {
        ElMessage.success('已复制到剪贴板');
      } else {
        ElMessage.error('复制失败');
      }
    } catch (fallbackError) {
      logger.error('复制失败:', fallbackError);
      ElMessage.error('复制失败');
    }
  }
}
