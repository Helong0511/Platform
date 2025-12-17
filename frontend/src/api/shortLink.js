import axios from 'axios';
import { normalizePaginatedResponse, normalizeResponse, extractErrorMessage, ensureCsrfToken } from '../utils/api';
import { ElMessage } from 'element-plus';

/**
 * 创建短链接
 */
export const createShortLink = async (linkData) => {
  try {
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

