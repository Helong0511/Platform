import { request } from '../utils/api';

const BASE = '/api/v1/cache';

/** 缓存条目列表 */
export function listCacheEntries(params = {}) {
  return request({
    url: `${BASE}/entries`,
    method: 'get',
    params,
  });
}

/** 单个缓存详情 */
export function getCacheEntry(key) {
  return request({
    url: `${BASE}/entries/detail`,
    method: 'get',
    params: { key },
  });
}

/** 删除单个缓存 */
export function deleteCacheEntry(key) {
  return request({
    url: `${BASE}/entries`,
    method: 'delete',
    params: { key },
  });
}

/** 清除所有非受保护缓存 */
export function clearAllCacheEntries() {
  return request({
    url: `${BASE}/entries/clear-all`,
    method: 'post',
  });
}

/** 缓存健康指标 */
export function getCacheStats() {
  return request({
    url: `${BASE}/stats`,
    method: 'get',
  });
}
