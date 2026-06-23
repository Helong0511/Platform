/**
 * 性能优化 API（对接 /api/v1/optimization）。
 */
import { request } from '../utils/api';

const BASE = '/api/v1/optimization';

export function getBottlenecks() {
  return request({ url: `${BASE}/bottlenecks`, method: 'get' }, { returnDataOnly: true });
}

export function detectBottlenecks() {
  return request({ url: `${BASE}/bottlenecks/detect`, method: 'post' }, { returnDataOnly: true });
}

export function getOptimizationPlans() {
  return request({ url: `${BASE}/plans`, method: 'get' }, { returnDataOnly: true });
}

export function getOptimizationEffectiveness() {
  return request({ url: `${BASE}/effectiveness`, method: 'get' }, { returnDataOnly: true });
}

export function createOptimizationPlan(data) {
  return request({
    url: `${BASE}/plans`,
    method: 'post',
    data,
  }, { returnDataOnly: true });
}

export function approveOptimizationPlan(planId) {
  return request({
    url: `${BASE}/plans/${encodeURIComponent(planId)}/approve`,
    method: 'put',
  }, { returnDataOnly: true });
}

export function startOptimizationPlan(planId) {
  return request({
    url: `${BASE}/plans/${encodeURIComponent(planId)}/start`,
    method: 'put',
  }, { returnDataOnly: true });
}

export function completeOptimizationPlan(planId) {
  return request({
    url: `${BASE}/plans/${encodeURIComponent(planId)}/complete`,
    method: 'put',
  }, { returnDataOnly: true });
}

export function verifyOptimizationPlan(planId) {
  return request({
    url: `${BASE}/plans/${encodeURIComponent(planId)}/verify`,
    method: 'put',
  }, { returnDataOnly: true });
}

export function rejectOptimizationPlan(planId, reason) {
  return request({
    url: `${BASE}/plans/${encodeURIComponent(planId)}/reject`,
    method: 'put',
    data: { reason },
  }, { returnDataOnly: true });
}
