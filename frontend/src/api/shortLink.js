/**
 * 短链接管理 API
 * 已统一使用 request 函数，保持代码一致性
 */
import { request } from '../utils/api';
import { refreshCsrfTokenBeforeRequest } from '../utils/api';

/**
 * 创建短链接
 */
export const createShortLink = async (linkData) => {
  // 在保存前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/short-links/?page_size=1');
  
  return request({
    url: '/api/v1/short-links/',
    method: 'post',
    data: linkData
  }, { returnDataOnly: true });
};

/**
 * 获取短链接列表
 */
export const getShortLinks = async (params = {}) => {
  return request({
    url: '/api/v1/short-links/',
    method: 'get',
    params
  }, { paginated: true });
};

/**
 * 获取短链接详情
 */
export const getShortLinkDetail = async (linkId) => {
  return request({
    url: `/api/v1/short-links/${linkId}/detail`,
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 更新短链接
 */
export const updateShortLink = async (linkId, linkData) => {
  // 在保存前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/short-links/?page_size=1');
  
  return request({
    url: `/api/v1/short-links/${linkId}`,
    method: 'put',
    data: linkData
  }, { returnDataOnly: true });
};

/**
 * 删除短链接
 */
export const deleteShortLink = async (linkId) => {
  // 在删除前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/short-links/?page_size=1');
  
  return request({
    url: `/api/v1/short-links/${linkId}`,
    method: 'delete'
  }, { returnDataOnly: true });
};

/**
 * 获取短链接统计
 */
export const getShortLinkStats = async () => {
  return request({
    url: '/api/v1/short-links/stats/summary',
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 检查短链接代码是否存在
 */
export const checkShortCode = async (shortCode) => {
  return request({
    url: `/api/v1/short-links/check-code/${shortCode}`,
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 生成短链接代码
 */
export const generateShortCode = async () => {
  return request({
    url: '/api/v1/short-links/generate-code',
    method: 'get'
  }, { returnDataOnly: true });
};
