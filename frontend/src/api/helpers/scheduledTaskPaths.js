/**
 * 定时任务 URL 编码（支持中文任务名）
 */
export function encodeScheduledTaskName(taskName) {
  return encodeURIComponent(taskName);
}

export function scheduledTaskPath(taskName, suffix = '') {
  const encoded = encodeScheduledTaskName(taskName);
  return suffix
    ? `/api/v1/scheduled-tasks/${encoded}/${suffix}`
    : `/api/v1/scheduled-tasks/${encoded}`;
}
