/**
 * 通知配置 CRUD 辅助（客户/产品维度）
 */
import { request } from '../../utils/api';
import { withCsrfMutate } from '../../utils/csrfMutate';

function configBase(type, id) {
  return `/api/v1/notification-configs/${type}s/${id}/config`;
}

export function createNotificationConfigApi(type) {
  return {
    get: (id) =>
      request({ url: configBase(type, id), method: 'get' }, { returnDataOnly: true }),

    save: (id, configData) =>
      withCsrfMutate(() =>
        request(
          { url: configBase(type, id), method: 'post', data: configData },
          { returnDataOnly: true }
        )
      ),

    delete: (id) =>
      withCsrfMutate(() =>
        request({ url: configBase(type, id), method: 'delete' }, { returnDataOnly: true })
      )
  };
}

const clientConfig = createNotificationConfigApi('client');
const productConfig = createNotificationConfigApi('product');

export const getClientNotificationConfig = clientConfig.get;
export const saveClientNotificationConfig = clientConfig.save;
export const deleteClientNotificationConfig = clientConfig.delete;

export const getProductNotificationConfig = productConfig.get;
export const saveProductNotificationConfig = productConfig.save;
export const deleteProductNotificationConfig = productConfig.delete;
