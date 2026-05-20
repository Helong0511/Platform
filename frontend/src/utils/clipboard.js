import { ElMessage } from 'element-plus';
import { logger } from './logger';

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
