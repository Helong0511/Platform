import { request } from '@/utils/api'

export function getSensitivePathProbeLogs(params) {
  return request({
    url: '/api/v1/sensitive-path-probes/',
    method: 'get',
    params,
  }, { paginated: true, timeout: 30000 })
}

export function getSensitivePathTopStats(params) {
  return request({
    url: '/api/v1/sensitive-path-probes/stats/top',
    method: 'get',
    params,
  }, { returnDataOnly: true, timeout: 30000 })
}

export function getSensitiveBlockedIps(params) {
  return request({
    url: '/api/v1/sensitive-path-probes/blocked-ips',
    method: 'get',
    params,
  }, { paginated: true, timeout: 30000 })
}

export function addSensitiveBlockedIp(data) {
  return request({
    url: '/api/v1/sensitive-path-probes/blocked-ips',
    method: 'post',
    data,
  }, { returnDataOnly: true, timeout: 30000 })
}

export function unblockSensitiveBlockedIp(id) {
  return request({
    url: `/api/v1/sensitive-path-probes/blocked-ips/${id}/unblock`,
    method: 'post',
  }, { returnDataOnly: true, timeout: 30000 })
}

export function cleanupSensitivePathProbeLogs(data) {
  return request({
    url: '/api/v1/sensitive-path-probes/cleanup',
    method: 'post',
    data,
  }, { returnDataOnly: true, timeout: 30000 })
}
