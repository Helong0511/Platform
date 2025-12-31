import axios from 'axios';
import { normalizePaginatedResponse, normalizeResponse, ensureCsrfToken } from '../utils/api';

// ==================== 客户通知配置 ====================

/**
 * 获取客户通知配置
 */
export const getClientNotificationConfig = async (clientId) => {
  try {
    const response = await axios.get(`/api/v1/notification-configs/clients/${clientId}/config`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 创建或更新客户通知配置
 */
export const saveClientNotificationConfig = async (clientId, configData) => {
  try {
    // 在保存前刷新CSRF令牌，确保使用最新的令牌
    const { refreshCsrfTokenBeforeRequest } = await import('../utils/api');
    await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
    
    const response = await axios.post(
      `/api/v1/notification-configs/clients/${clientId}/config`,
      configData
    );
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 删除客户通知配置
 */
export const deleteClientNotificationConfig = async (clientId) => {
  try {
    // 在删除前刷新CSRF令牌，确保使用最新的令牌
    const { refreshCsrfTokenBeforeRequest } = await import('../utils/api');
    await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
    
    const response = await axios.delete(`/api/v1/notification-configs/clients/${clientId}/config`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

// ==================== 产品通知配置 ====================

/**
 * 获取产品通知配置
 */
export const getProductNotificationConfig = async (productId) => {
  try {
    const response = await axios.get(`/api/v1/notification-configs/products/${productId}/config`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 创建或更新产品通知配置
 */
export const saveProductNotificationConfig = async (productId, configData) => {
  try {
    // 在保存前刷新CSRF令牌，确保使用最新的令牌
    const { refreshCsrfTokenBeforeRequest } = await import('../utils/api');
    await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
    
    const response = await axios.post(
      `/api/v1/notification-configs/products/${productId}/config`,
      configData
    );
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 删除产品通知配置
 */
export const deleteProductNotificationConfig = async (productId) => {
  try {
    // 在删除前刷新CSRF令牌，确保使用最新的令牌
    const { refreshCsrfTokenBeforeRequest } = await import('../utils/api');
    await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
    
    const response = await axios.delete(`/api/v1/notification-configs/products/${productId}/config`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

// ==================== 通知记录 ====================

/**
 * 获取通知记录列表
 */
export const getNotificationRecords = async (params = {}) => {
  try {
    const response = await axios.get('/api/v1/notification-configs/notifications', { params });
    return normalizePaginatedResponse(response);
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

/**
 * 获取通知记录详情
 */
export const getNotificationRecord = async (notificationId) => {
  try {
    const response = await axios.get(`/api/v1/notification-configs/notifications/${notificationId}`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const { handleError } = await import('../utils/api');
    handleError(error);
  }
};

