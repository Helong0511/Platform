/**
 * 敏感路径探测记录 API（/api/v1/sensitive-path-probes）。
 *
 * 管理端查看恶意扫描/探测请求日志、严重级别枚举、封禁相关操作。
 */
import { request } from '@/utils/api';
import { withCsrfMutate } from '@/utils/csrfMutate';

const LIST_TIMEOUT = 30000;

/** 获取敏感路径探测严重级别枚举列表 */
export function getSensitiveSeverityLevels() {
  return request(
    {
      url: '/api/v1/sensitive-path-probes/levels',
      method: 'get',
    },
    { returnDataOnly: true, timeout: LIST_TIMEOUT }
  );
}

/**
 * 分页获取敏感路径探测日志
 * @param {Object} params - 筛选与分页参数
 */
export function getSensitivePathProbeLogs(params) {
  return request(
    {
      url: '/api/v1/sensitive-path-probes/',
      method: 'get',
      params
    },
    { paginated: true, timeout: LIST_TIMEOUT }
  );
}

/**
 * 获取探测来源 IP/路径 Top 统计
 * @param {Object} params - 时间范围等筛选参数
 */
export function getSensitivePathTopStats(params) {
  return request(
    {
      url: '/api/v1/sensitive-path-probes/stats/top',
      method: 'get',
      params
    },
    { returnDataOnly: true, timeout: LIST_TIMEOUT }
  );
}

/**
 * 分页获取已封禁 IP 列表
 * @param {Object} params - 分页参数
 */
export function getSensitiveBlockedIps(params) {
  return request(
    {
      url: '/api/v1/sensitive-path-probes/blocked-ips',
      method: 'get',
      params
    },
    { paginated: true, timeout: LIST_TIMEOUT }
  );
}

/**
 * 手动添加封禁 IP
 * @param {Object} data - IP 地址与备注
 */
export function addSensitiveBlockedIp(data) {
  return withCsrfMutate(() =>
    request(
      {
        url: '/api/v1/sensitive-path-probes/blocked-ips',
        method: 'post',
        data
      },
      { returnDataOnly: true, timeout: LIST_TIMEOUT }
    )
  );
}

/** 批量封禁 IP：blocked_ips 和/或 log_ids */
export function batchAddSensitiveBlockedIps(data) {
  return withCsrfMutate(() =>
    request(
      {
        url: '/api/v1/sensitive-path-probes/blocked-ips/batch',
        method: 'post',
        data
      },
      { returnDataOnly: true, timeout: LIST_TIMEOUT }
    )
  );
}

/**
 * 解除指定封禁 IP
 * @param {number|string} id - 封禁记录 ID
 */
export function unblockSensitiveBlockedIp(id) {
  return withCsrfMutate(() =>
    request(
      {
        url: `/api/v1/sensitive-path-probes/blocked-ips/${id}/unblock`,
        method: 'post'
      },
      { returnDataOnly: true, timeout: LIST_TIMEOUT }
    )
  );
}

/**
 * 清理历史探测日志（按保留天数）
 * @param {Object} data - 清理参数
 */
export function cleanupSensitivePathProbeLogs(data) {
  return withCsrfMutate(() =>
    request(
      {
        url: '/api/v1/sensitive-path-probes/cleanup',
        method: 'post',
        data
      },
      { returnDataOnly: true, timeout: LIST_TIMEOUT }
    )
  );
}
