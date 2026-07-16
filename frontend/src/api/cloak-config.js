/**
 * 斗篷配置管理 API（对接 /api/v1/cloak-configs）
 *
 * - CRUD：列表、创建、更新、删除
 * - testCloakReport：模拟 CAPI 测试上报（主/备像素）
 * - uploadCloakBridgeHtml：上传 {cloak_name}.html 桥页文件
 */
import { createCrudApi } from '@/utils/crudApi';
import { request } from '../utils/api';
import { withCsrfMutate } from '../utils/csrfMutate';
const {
  getCloakConfigs,
  getCloakConfig,
  createCloakConfig,
  updateCloakConfig,
  deleteCloakConfig
} = createCrudApi('/api/v1/cloak-configs', {
  methodNames: {
    list: 'getCloakConfigs',
    get: 'getCloakConfig',
    create: 'createCloakConfig',
    update: 'updateCloakConfig',
    delete: 'deleteCloakConfig'
  },
  include: ['list', 'get', 'create', 'update', 'delete'],
  csrfOnMutate: true
});

/** 斗篷配置 CRUD：列表、详情、新建、更新、删除 */
export {
  getCloakConfigs,
  getCloakConfig,
  createCloakConfig,
  updateCloakConfig,
  deleteCloakConfig
};

/** 向指定斗篷配置发送测试 Facebook CAPI 事件（超时 30s） */
export const testCloakReport = async (id, data) =>
  withCsrfMutate(() =>
    request(
      {
        url: `/api/v1/cloak-configs/${id}/test-report`,
        method: 'post',
        data
      },
      { returnDataOnly: true, timeout: 30000 }
    )
  );

/** 上传桥页 HTML，服务端保存为 {cloak_name}.html（超时 60s，multipart） */
export const uploadCloakBridgeHtml = async (id, file) => {
  const formData = new FormData();
  formData.append('file', file);
  return withCsrfMutate(() =>
    request(
      {
        url: `/api/v1/cloak-configs/${id}/bridge-html`,
        method: 'post',
        data: formData
      },
      { returnDataOnly: true, timeout: 60000 }
    )
  );
};
