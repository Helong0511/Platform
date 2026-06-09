/**
 * 通知配置表单辅助：字段映射与校验
 * @file api/helpers/notificationConfig.js
 */
import { request } from '../../utils/api';
import { withCsrfMutate } from '../../utils/csrfMutate';

function configBase(type, id) {
  return `/api/v1/notification-configs/${type}s/${id}/config`;
}

/**
 * 按资源类型创建通知配置 API 方法集
 * @param {'client'|'product'} type - 资源类型（客户或产品）
 * @returns {{ get: Function, save: Function, delete: Function }}
 */
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

/** 获取客户通知配置 */
export const getClientNotificationConfig = clientConfig.get;
/** 保存客户通知配置 */
export const saveClientNotificationConfig = clientConfig.save;
/** 删除客户通知配置 */
export const deleteClientNotificationConfig = clientConfig.delete;

/** 获取产品通知配置 */
export const getProductNotificationConfig = productConfig.get;
/** 保存产品通知配置 */
export const saveProductNotificationConfig = productConfig.save;
/** 删除产品通知配置 */
export const deleteProductNotificationConfig = productConfig.delete;
