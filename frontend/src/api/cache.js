/**
 * 系统缓存管理 API（对接 /api/v1/cache）。
 *
 * 供管理端查看 Redis/内存缓存条目、单条详情、删除与批量清理。
 */
import { request } from '../utils/api';

const BASE = '/api/v1/cache';

/**
 * 缓存条目列表 接口。
 */
export function listCacheEntries(params = {}) {
  return request({
    url: `${BASE}/entries`,
    method: 'get',
    params,
  });
}

/**
 * 单个缓存详情 接口。
 */
export function getCacheEntry(key) {
  return request({
    url: `${BASE}/entries/detail`,
    method: 'get',
    params: { key },
  });
}

/**
 * 删除单个缓存 接口。
 */
export function deleteCacheEntry(key) {
  return request({
    url: `${BASE}/entries`,
    method: 'delete',
    params: { key },
  });
}

/**
 * 清除所有非受保护缓存 接口。
 */
export function clearAllCacheEntries() {
  return request({
    url: `${BASE}/entries/clear-all`,
    method: 'post',
  });
}

/**
 * 缓存健康指标 接口。
 */
export function getCacheStats() {
  return request({
    url: `${BASE}/stats`,
    method: 'get',
  });
}
