import { request } from '@/utils/api';
import { withCsrfMutate } from '@/utils/csrfMutate';

const LIST_TIMEOUT = 30000;

export function getSensitiveSeverityLevels() {
  return request(
    {
      url: '/api/v1/sensitive-path-probes/levels',
      method: 'get',
    },
    { returnDataOnly: true, timeout: LIST_TIMEOUT }
  );
}

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
