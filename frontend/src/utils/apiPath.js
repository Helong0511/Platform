/**
 * API 路径参数校验：防止未解析占位符或空 ID 进入请求。
 * @module utils/apiPath
 */

/** 打包 JS 模板占位符（如 ${e}）或 copy-paste 残留 */
const BUNDLE_PLACEHOLDER_RE = /\$\{[^}]+\}/;

/** URL 路径段为 undefined/null 时 axios 会拼出字面量路径 */
const UNRESOLVED_ID_RE = /(?:\/undefined|\/null)(?:\/|$|\?)/;

/**
 * 校验请求 URL，非法时抛出 Error（由 request 捕获并静默或提示）。
 * @param {string} url
 */
export function assertValidRequestUrl(url) {
  if (!url || typeof url !== 'string') {
    throw new Error('API 路径无效');
  }
  if (BUNDLE_PLACEHOLDER_RE.test(url)) {
    throw new Error(`API 路径含未解析占位符: ${url}`);
  }
  if (UNRESOLVED_ID_RE.test(url)) {
    throw new Error(`API 路径 ID 未就绪: ${url}`);
  }
}

/**
 * 校验路径参数 ID。
 * @param {*} id
 * @param {string} [label='id']
 */
export function assertValidPathId(id, label = 'id') {
  if (id === undefined || id === null || id === '') {
    throw new Error(`${label} 不能为空`);
  }
  if (typeof id === 'string' && BUNDLE_PLACEHOLDER_RE.test(id)) {
    throw new Error(`${label} 含未解析占位符`);
  }
}
