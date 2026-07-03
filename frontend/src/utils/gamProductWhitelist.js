/**
 * GAM 白名单产品名称解析与规范化（与 app.scheduler_module.gam_api_fetch 规则一致）
 */

/**
 * 规范化单个产品名称
 * @param {string} name
 */
export function normalizeGamProductName(name) {
  let normalized = String(name || '').trim().toLowerCase();
  if (normalized.startsWith('www.')) {
    normalized = normalized.slice(4);
  }
  return normalized;
}

/**
 * 从文本解析产品名称列表（支持换行、逗号、分号、空格分隔）
 * @param {string} text
 */
export function parseGamProductNamesFromText(text) {
  if (!text || !String(text).trim()) return [];
  return String(text)
    .split(/[\n\r,，;；\t]+/)
    .map((part) => normalizeGamProductName(part))
    .filter(Boolean);
}

/**
 * 合并去重产品名称
 * @param {string[]} current
 * @param {string[]} incoming
 */
export function mergeGamProductNames(current, incoming) {
  const set = new Set((current || []).map(normalizeGamProductName).filter(Boolean));
  for (const name of incoming || []) {
    const normalized = normalizeGamProductName(name);
    if (normalized) set.add(normalized);
  }
  return [...set].sort();
}

/**
 * 从平台产品记录提取可选名称
 * @param {Array<{ name?: string }>} products
 */
export function extractPlatformProductNames(products) {
  const names = new Set();
  for (const item of products || []) {
    const normalized = normalizeGamProductName(item?.name);
    if (normalized) names.add(normalized);
  }
  return [...names].sort();
}
