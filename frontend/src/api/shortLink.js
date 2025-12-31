import axios from 'axios';
import { normalizePaginatedResponse, normalizeResponse, ensureCsrfToken, refreshCsrfToken } from '../utils/api';

/**
 * 创建短链接
 */
export const createShortLink = async (linkData) => {
  try {
    // 在保存前刷新CSRF令牌，确保使用最新的令牌
    const { refreshCsrfTokenBeforeRequest, handleError } = await import('../utils/api');
    await refreshCsrfTokenBeforeRequest('/api/v1/short-links/?page_size=1');
    
    const response = await axios.post('/api/v1/short-links/', linkData);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 获取短链接列表
 */
export const getShortLinks = async (params = {}) => {
  try {
    const response = await axios.get('/api/v1/short-links/', { params });
    return normalizePaginatedResponse(response);
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 获取短链接详情
 */
export const getShortLinkDetail = async (linkId) => {
  try {
    const response = await axios.get(`/api/v1/short-links/${linkId}/detail`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 更新短链接
 */
export const updateShortLink = async (linkId, linkData) => {
  try {
    // 在保存前刷新CSRF令牌，确保使用最新的令牌
    const { refreshCsrfTokenBeforeRequest } = await import('../utils/api');
    await refreshCsrfTokenBeforeRequest('/api/v1/short-links/?page_size=1');
    
    const response = await axios.put(`/api/v1/short-links/${linkId}`, linkData);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 删除短链接
 */
export const deleteShortLink = async (linkId) => {
  try {
    // 在删除前刷新CSRF令牌，确保使用最新的令牌
    const { refreshCsrfTokenBeforeRequest } = await import('../utils/api');
    await refreshCsrfTokenBeforeRequest('/api/v1/short-links/?page_size=1');
    
    const response = await axios.delete(`/api/v1/short-links/${linkId}`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 获取短链接统计
 */
export const getShortLinkStats = async () => {
  try {
    const response = await axios.get('/api/v1/short-links/stats/summary');
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 检查短链接代码是否存在
 */
export const checkShortCode = async (shortCode) => {
  try {
    const response = await axios.get(`/api/v1/short-links/check-code/${shortCode}`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 生成短链接代码
 */
export const generateShortCode = async () => {
  try {
    const response = await axios.get('/api/v1/short-links/generate-code');
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

