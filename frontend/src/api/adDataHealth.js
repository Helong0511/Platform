/**
 * 广告数据健康巡检 API（/api/v1/ad-data-health）
 */
import { request } from '../utils/api'

const BASE = '/api/v1/ad-data-health'

export function fetchHealthSettings() {
  return request({ url: `${BASE}/settings`, method: 'get', returnDataOnly: true })
}

export function updateHealthSettings(data) {
  return request({ url: `${BASE}/settings`, method: 'put', data, returnDataOnly: true })
}

export function fetchHealthAlerts(params) {
  return request({ url: `${BASE}/alerts`, method: 'get', params, returnDataOnly: true })
}

export function fetchHealthBaselines(params) {
  return request({ url: `${BASE}/baselines`, method: 'get', params, returnDataOnly: true })
}

export function freezeHealthBaseline(data) {
  return request({ url: `${BASE}/baselines/freeze`, method: 'post', data, returnDataOnly: true })
}

export function runHealthScan(data) {
  return request({ url: `${BASE}/run`, method: 'post', data: data || {}, returnDataOnly: true })
}
