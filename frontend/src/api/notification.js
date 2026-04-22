/**
 * 通知配置管理 API
 * 已统一使用 request 函数，保持代码一致性
 */
import { request, refreshCsrfTokenBeforeRequest } from '../utils/api';

// ==================== 客户通知配置 ====================

/**
 * 获取客户通知配置
 */
export const getClientNotificationConfig = async (clientId) => {
  return request({
    url: `/api/v1/notification-configs/clients/${clientId}/config`,
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 创建或更新客户通知配置
 */
export const saveClientNotificationConfig = async (clientId, configData) => {
  // 在保存前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  
  return request({
    url: `/api/v1/notification-configs/clients/${clientId}/config`,
    method: 'post',
    data: configData
  }, { returnDataOnly: true });
};

/**
 * 删除客户通知配置
 */
export const deleteClientNotificationConfig = async (clientId) => {
  // 在删除前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  
  return request({
    url: `/api/v1/notification-configs/clients/${clientId}/config`,
    method: 'delete'
  }, { returnDataOnly: true });
};

// ==================== 产品通知配置 ====================

/**
 * 获取产品通知配置
 */
export const getProductNotificationConfig = async (productId) => {
  return request({
    url: `/api/v1/notification-configs/products/${productId}/config`,
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 创建或更新产品通知配置
 */
export const saveProductNotificationConfig = async (productId, configData) => {
  // 在保存前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  
  return request({
    url: `/api/v1/notification-configs/products/${productId}/config`,
    method: 'post',
    data: configData
  }, { returnDataOnly: true });
};

/**
 * 删除产品通知配置
 */
export const deleteProductNotificationConfig = async (productId) => {
  // 在删除前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  
  return request({
    url: `/api/v1/notification-configs/products/${productId}/config`,
    method: 'delete'
  }, { returnDataOnly: true });
};

// ==================== 通知记录 ====================

/**
 * 获取通知记录列表
 */
export const getNotificationRecords = async (params = {}) => {
  return request({
    url: '/api/v1/notification-configs/notifications',
    method: 'get',
    params
  }, { paginated: true });
};

/**
 * 获取通知记录详情
 */
export const getNotificationRecord = async (notificationId) => {
  return request({
    url: `/api/v1/notification-configs/notifications/${notificationId}`,
    method: 'get'
  }, { returnDataOnly: true });
};

// ==================== 补发通知 ====================

/**
 * 补发转化通知
 */
export const resendConversionNotification = async (conversionId) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  return request({
    url: `/api/v1/notification-configs/conversions/${conversionId}/resend-notification`,
    method: 'post'
  }, { returnDataOnly: true });
};

/**
 * 批量补发转化通知
 */
export const batchResendConversionNotification = async (conversionIds) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  return request({
    url: '/api/v1/notification-configs/conversions/batch-resend-notification',
    method: 'post',
    data: { conversion_ids: conversionIds }
  }, { returnDataOnly: true });
};

// ==================== 管理员通知配置 ====================

/**
 * 获取管理员通知配置
 */
export const getAdminNotificationConfig = async () => {
  return request({
    url: '/api/v1/notification-configs/admin/config',
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 保存管理员通知配置
 */
export const saveAdminNotificationConfig = async (configData) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  return request({
    url: '/api/v1/notification-configs/admin/config',
    method: 'post',
    data: configData
  }, { returnDataOnly: true });
};

/**
 * 测试 Telegram 连接
 */
export const testTelegramConnection = async (chatId) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  return request({
    url: '/api/v1/notification-configs/admin/test-connection',
    method: 'post',
    data: { telegram_chat_id: chatId }
  }, { returnDataOnly: true });
};

/**
 * 发送测试消息
 */
export const sendTestMessage = async (chatId, messageType = 'conversion') => {
  await refreshCsrfTokenBeforeRequest('/api/v1/dashboard/stats');
  return request({
    url: '/api/v1/notification-configs/admin/test-message',
    method: 'post',
    data: {
      telegram_chat_id: chatId,
      message_type: messageType
    }
  }, { returnDataOnly: true });
};
