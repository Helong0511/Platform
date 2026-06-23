/**
 * 系统监控 API（对接 /api/v1/monitoring）。
 * 使用统一 request 封装，自动携带 Cookie 与 CSRF。
 */
import { request } from '../utils/api';

const BASE = '/api/v1/monitoring';

const MONITORING_TIMEOUT = 30000;

export function getMonitoringMetrics() {
  return request({ url: `${BASE}/metrics`, method: 'get' }, { returnDataOnly: true, timeout: MONITORING_TIMEOUT });
}

export function getTrendData(hours) {
  return request({
    url: `${BASE}/metrics/trends`,
    method: 'get',
    params: { hours },
  }, { returnDataOnly: true });
}

export function getTrendPredict(steps = 60) {
  return request({
    url: `${BASE}/metrics/predict`,
    method: 'get',
    params: { steps },
  }, { returnDataOnly: true });
}

export function getTrendSummary(hours) {
  return request({
    url: `${BASE}/metrics/trends/summary`,
    method: 'get',
    params: { hours },
  }, { returnDataOnly: true });
}

export function getAlertRules() {
  return request({ url: `${BASE}/alerts/rules`, method: 'get' }, { returnDataOnly: true });
}

export function getAlerts(params = {}) {
  return request({
    url: `${BASE}/alerts`,
    method: 'get',
    params,
  }, { returnDataOnly: true });
}

export function createAlertRule(data) {
  return request({
    url: `${BASE}/alerts/rules`,
    method: 'post',
    data,
  }, { returnDataOnly: true });
}

export function toggleAlertRule(ruleId) {
  return request({
    url: `${BASE}/alerts/rules/${encodeURIComponent(ruleId)}/toggle`,
    method: 'put',
  }, { returnDataOnly: true });
}

export function deleteAlertRule(ruleId) {
  return request({
    url: `${BASE}/alerts/rules/${encodeURIComponent(ruleId)}`,
    method: 'delete',
  }, { returnDataOnly: true });
}

export function acknowledgeAlert(alertId) {
  return request({
    url: `${BASE}/alerts/${encodeURIComponent(alertId)}/acknowledge`,
    method: 'put',
  }, { returnDataOnly: true });
}

export function acknowledgeAllAlerts() {
  return request({
    url: `${BASE}/alerts/acknowledge-all`,
    method: 'put',
  }, { returnDataOnly: true });
}
