/**
 * 斗篷配置管理 API
 */
import { request, refreshCsrfTokenBeforeRequest } from '../utils/api';

export const getCloakConfigs = async (params = {}) => {
  return request({
    url: '/api/v1/cloak-configs/',
    method: 'get',
    params
  }, { paginated: true });
};

export const createCloakConfig = async (data) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  return request({
    url: '/api/v1/cloak-configs/',
    method: 'post',
    data
  }, { returnDataOnly: true });
};

export const updateCloakConfig = async (id, data) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  return request({
    url: `/api/v1/cloak-configs/${id}`,
    method: 'put',
    data
  }, { returnDataOnly: true });
};

export const deleteCloakConfig = async (id) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  return request({
    url: `/api/v1/cloak-configs/${id}`,
    method: 'delete'
  }, { returnDataOnly: true });
};

export const testCloakReport = async (id, data) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  return request({
    url: `/api/v1/cloak-configs/${id}/test-report`,
    method: 'post',
    data
  }, { returnDataOnly: true, timeout: 30000 });
};
