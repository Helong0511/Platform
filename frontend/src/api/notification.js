/**
 * 通知配置 API：Telegram/产品/客户通知
 * @file api/notification.js
 */
import { request } from '../utils/api';
import { withCsrfMutate } from '../utils/csrfMutate';
export {
  getClientNotificationConfig,
  saveClientNotificationConfig,
  deleteClientNotificationConfig,
  getProductNotificationConfig,
  saveProductNotificationConfig,
  deleteProductNotificationConfig
} from './helpers/notificationConfig';

// ==================== 通知记录 ====================

/**
 * 分页获取通知发送记录。
 */
export const getNotificationRecords = async (params = {}) =>
  request(
    {
      url: '/api/v1/notification-configs/notifications',
      method: 'get',
      params
    },
    { paginated: true }
  );

/**
 * 获取单条通知记录详情。
 */
export const getNotificationRecord = async (notificationId) =>
  request(
    {
      url: `/api/v1/notification-configs/notifications/${notificationId}`,
      method: 'get'
    },
    { returnDataOnly: true }
  );

// ==================== 补发通知 ====================

/**
 * resendConversionNotification 接口。
 */
export const resendConversionNotification = async (conversionId) =>
  withCsrfMutate(() =>
    request(
      {
        url: `/api/v1/notification-configs/conversions/${conversionId}/resend-notification`,
        method: 'post'
      },
      { returnDataOnly: true }
    )
  );

/**
 * 批量Resend Conversion Notification。
 */
export const batchResendConversionNotification = async (conversionIds) =>
  withCsrfMutate(() =>
    request(
      {
        url: '/api/v1/notification-configs/conversions/batch-resend-notification',
        method: 'post',
        data: { conversion_ids: conversionIds }
      },
      { returnDataOnly: true }
    )
  );

// ==================== 管理员通知配置 ====================

/**
 * 获取管理员侧通知配置。
 */
export const getAdminNotificationConfig = async () =>
  request(
    { url: '/api/v1/notification-configs/admin/config', method: 'get' },
    { returnDataOnly: true }
  );

/**
 * 保存Admin Notification Config。
 */
export const saveAdminNotificationConfig = async (configData) =>
  withCsrfMutate(() =>
    request(
      {
        url: '/api/v1/notification-configs/admin/config',
        method: 'post',
        data: configData
      },
      { returnDataOnly: true }
    )
  );

/**
 * testTelegramConnection 接口。
 */
export const testTelegramConnection = async (chatId) =>
  withCsrfMutate(() =>
    request(
      {
        url: '/api/v1/notification-configs/admin/test-connection',
        method: 'post',
        data: { telegram_chat_id: chatId }
      },
      { returnDataOnly: true }
    )
  );

/**
 * 发送Test Message。
 */
export const sendTestMessage = async (chatId, messageType = 'conversion') =>
  withCsrfMutate(() =>
    request(
      {
        url: '/api/v1/notification-configs/admin/test-message',
        method: 'post',
        data: {
          telegram_chat_id: chatId,
          message_type: messageType
        }
      },
      { returnDataOnly: true }
    )
  );
