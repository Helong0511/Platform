/**
 * 斗篷配置管理 API
 */
import { createCrudApi } from '@/utils/crudApi';
import { request } from '../utils/api';
import { withCsrfMutate } from '../utils/csrfMutate';
const {
  getCloakConfigs,
  createCloakConfig,
  updateCloakConfig,
  deleteCloakConfig
} = createCrudApi('/api/v1/cloak-configs', {
  methodNames: {
    list: 'getCloakConfigs',
    create: 'createCloakConfig',
    update: 'updateCloakConfig',
    delete: 'deleteCloakConfig'
  },
  include: ['list', 'create', 'update', 'delete'],
  csrfOnMutate: true
});

export {
  getCloakConfigs,
  createCloakConfig,
  updateCloakConfig,
  deleteCloakConfig
};

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
