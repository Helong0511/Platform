/**
 * 定时任务 API 路径辅助
 * @file api/helpers/scheduledTaskPaths.js
 *
 * 对中文任务名进行 URL 编码，生成 REST 路径。
 */

/**
 * 编码定时任务名称（支持中文）
 * @param {string} taskName - 任务名称
 * @returns {string} URL 编码后的任务名
 */
export function encodeScheduledTaskName(taskName) {
  return encodeURIComponent(taskName);
}

/**
 * 构建定时任务 API 路径
 * @param {string} taskName - 任务名称
 * @param {string} [suffix=''] - 路径后缀（如 run、logs）
 * @returns {string} 完整 API 路径
 */
export function scheduledTaskPath(taskName, suffix = '') {
  const encoded = encodeScheduledTaskName(taskName);
  return suffix
    ? `/api/v1/scheduled-tasks/${encoded}/${suffix}`
    : `/api/v1/scheduled-tasks/${encoded}`;
}
