/**
 * 客户管理 API（CRUD + 详情缓存 + 导出）
 */
import { createCrudApi } from '@/utils/crudApi';
import { createCachedDetailFetcher } from '@/utils/cachedDetailFetch';
import { request, handleError } from '../utils/api';
import { requestListExport } from './helpers/exportDownload';
import { prepareCsrfMutate, CSRF_REFRESH_CLIENTS } from '../utils/csrfMutate';
import { ElMessage } from 'element-plus';
import { getSuccessMessage } from '../utils/messages';

const {
  getClientList,
  createClient,
  updateClient: updateClientBase,
  deleteClient: deleteClientBase
} = createCrudApi('/api/v1/clients', {
  methodNames: {
    list: 'getClientList',
    create: 'createClient',
    update: 'updateClient',
    delete: 'deleteClient'
  },
  include: ['list', 'create', 'update', 'delete'],
  csrfOnMutate: true,
  csrfEndpoint: CSRF_REFRESH_CLIENTS
});

export { getClientList, createClient };

const clientDetailCache = createCachedDetailFetcher();

export const getClientDetail = async (id, options = {}) => {
  const { useCache = true, silent = false } = options;
  try {
    return await clientDetailCache.get(
      id,
      (clientId, opts) =>
        request(
          { url: `/api/v1/clients/${clientId}`, method: 'get' },
          { returnDataOnly: true, timeout: 10000, silent: opts.silent }
        ),
      { useCache, silent }
    );
  } catch (error) {
    if (silent) {
      handleError(error, { showMessage: false });
    } else {
      handleError(error);
    }
    throw error;
  }
};

export const clearClientDetailCache = (id = null) => {
  clientDetailCache.clear(id);
};

export const updateClient = async (id, clientData) => {
  await prepareCsrfMutate(CSRF_REFRESH_CLIENTS);
  const result = await updateClientBase(id, clientData);
  clearClientDetailCache(id);
  return result;
};

export const updateClientSwitches = async (id, switchData) => {
  await prepareCsrfMutate(CSRF_REFRESH_CLIENTS);
  const result = await request(
    {
      url: `/api/v1/clients/${id}/switches`,
      method: 'patch',
      data: switchData
    },
    { returnDataOnly: true }
  );
  clearClientDetailCache(id);
  return result;
};

export const deleteClient = async (id) => {
  await prepareCsrfMutate(CSRF_REFRESH_CLIENTS);
  await deleteClientBase(id);
  return true;
};

export const exportClients = (params = {}) =>
  requestListExport(
    { url: '/api/v1/clients/export', method: 'get', params },
    {
      defaultFilename: '客户数据导出.xlsx',
      onSuccess: () => ElMessage.success(getSuccessMessage('CLIENT_EXPORT_SUCCESS'))
    }
  );
