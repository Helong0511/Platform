import axios from 'axios';
import { normalizePaginatedResponse, normalizeResponse, extractErrorMessage, ensureCsrfToken } from '../utils/api';
import { ElMessage } from 'element-plus';

/**
 * 刷新CSRF令牌（通过发送GET请求）
 */
const refreshCsrfToken = async () => {
  try {
    // 发送一个轻量级的GET请求来刷新CSRF令牌
    const response = await axios.get('/api/v1/short-links/?page_size=1');
    
    // 直接从响应头获取CSRF令牌（不依赖响应拦截器）
    const csrfToken = response.headers['x-csrf-token'] || response.headers['X-CSRF-Token'];
    if (csrfToken) {
      sessionStorage.setItem('csrf_token', csrfToken);
    }
    
    // 额外等待一小段时间，确保响应拦截器也处理完成
    await new Promise(resolve => setTimeout(resolve, 50));
  } catch (error) {
    // 即使请求失败，响应头中也可能有CSRF令牌
    if (error.response?.headers) {
      const csrfToken = error.response.headers['x-csrf-token'] || error.response.headers['X-CSRF-Token'];
      if (csrfToken) {
        sessionStorage.setItem('csrf_token', csrfToken);
      }
    }
  }
};

/**
 * 创建短链接
 */
export const createShortLink = async (linkData) => {
  try {
    // 在保存前刷新CSRF令牌，确保使用最新的令牌
    await refreshCsrfToken();
    await ensureCsrfToken();
    const response = await axios.post('/api/v1/short-links/', linkData);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
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
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
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
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

/**
 * 更新短链接
 */
export const updateShortLink = async (linkId, linkData) => {
  try {
    // 在保存前刷新CSRF令牌，确保使用最新的令牌
    await refreshCsrfToken();
    await ensureCsrfToken();
    const response = await axios.put(`/api/v1/short-links/${linkId}`, linkData);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

/**
 * 删除短链接
 */
export const deleteShortLink = async (linkId) => {
  try {
    // 在删除前刷新CSRF令牌，确保使用最新的令牌
    await refreshCsrfToken();
    await ensureCsrfToken();
    const response = await axios.delete(`/api/v1/short-links/${linkId}`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
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
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
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
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
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
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

