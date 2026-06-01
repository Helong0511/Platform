/**
 * 通知配置管理 API
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

export const getNotificationRecords = async (params = {}) =>
  request(
    {
      url: '/api/v1/notification-configs/notifications',
      method: 'get',
      params
    },
    { paginated: true }
  );

export const getNotificationRecord = async (notificationId) =>
  request(
    {
      url: `/api/v1/notification-configs/notifications/${notificationId}`,
      method: 'get'
    },
    { returnDataOnly: true }
  );

// ==================== 补发通知 ====================

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

export const getAdminNotificationConfig = async () =>
  request(
    { url: '/api/v1/notification-configs/admin/config', method: 'get' },
    { returnDataOnly: true }
  );

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
