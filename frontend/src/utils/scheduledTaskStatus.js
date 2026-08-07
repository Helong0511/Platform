/**
 * 定时任务运行/启用状态工具。
 *
 * 列表接口偶发返回 0/1 或字符串，统一归一化后再驱动「正在运行」展示与禁用启用开关。
 */

/**
 * 将接口字段规范为布尔值。
 * @param {unknown} value
 * @returns {boolean}
 */
export function toBoolFlag(value) {
  if (value === true || value === 1 || value === '1' || value === 'true') return true;
  if (value === false || value === 0 || value === '0' || value === 'false' || value == null) {
    return false;
  }
  return Boolean(value);
}

/**
 * 任务是否正在执行（持锁）。
 * @param {object|null|undefined} task
 * @returns {boolean}
 */
export function isTaskRunning(task) {
  return toBoolFlag(task?.is_running);
}

/**
 * 归一化列表行，保证 is_running / is_active 为布尔。
 * @param {object} row
 * @returns {object}
 */
export function normalizeScheduledTaskRow(row) {
  if (!row || typeof row !== 'object') return row;
  return {
    ...row,
    is_running: toBoolFlag(row.is_running),
    is_active: toBoolFlag(row.is_active),
  };
}

/**
 * 将 last_error 字段（实际承载成功/失败摘要）映射为标签类型。
 * @param {string|null|undefined} message
 * @returns {'success'|'warning'|'danger'|'info'}
 */
export function resolveLastResultTagType(message) {
  const text = String(message || '').trim();
  if (!text) return 'info';
  if (
    text.startsWith('执行成功')
    || text.includes('执行成功:')
    || text.includes('执行成功：')
  ) {
    return 'success';
  }
  if (
    text.startsWith('跳过')
    || text.startsWith('软跳过')
    || text.includes('软跳过:')
    || text.includes('部分跳过')
  ) {
    return 'warning';
  }
  if (
    text.startsWith('执行失败')
    || text.startsWith('部分失败')
    || text.includes('错误:')
    || text.includes('失败:')
  ) {
    return 'danger';
  }
  return 'info';
}
