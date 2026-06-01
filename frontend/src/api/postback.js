/**
 * Postback 管理 API
 */
import { request } from '../utils/api';
import { createCrudApi } from '@/utils/crudApi';
import { withCsrfMutate } from '../utils/csrfMutate';

export const getPostbackConversions = async (params) => {
  return request({
    url: '/api/v1/postback/conversions',
    method: 'get',
    params
  }, { paginated: true });
};

export const getPostbackStats = async (params = {}) => {
  return request({
    url: '/api/v1/postback/stats',
    method: 'get',
    params
  }, { returnDataOnly: true });
};

export const updateConversionStatus = async (conversionId, status) =>
  withCsrfMutate(() =>
    request(
      {
        url: `/api/v1/postback/conversions/${conversionId}/status`,
        method: 'put',
        params: { status }
      },
      { returnDataOnly: true }
    )
  );

const {
  getIpWhitelists: getIpWhitelist,
  createIpWhitelist,
  updateIpWhitelist,
  deleteIpWhitelist
} = createCrudApi('/api/v1/postback/ip-whitelist', {
  listTrailingSlash: false,
  resourceName: 'IpWhitelist',
  methodNames: {
    list: 'getIpWhitelist',
    create: 'createIpWhitelist',
    update: 'updateIpWhitelist',
    delete: 'deleteIpWhitelist'
  },
  include: ['list', 'create', 'update', 'delete'],
  csrfOnMutate: true
});

export { getIpWhitelist, createIpWhitelist, updateIpWhitelist, deleteIpWhitelist };

export const batchCreateIpWhitelist = async (data) =>
  withCsrfMutate(() =>
    request(
      {
        url: '/api/v1/postback/ip-whitelist/batch',
        method: 'post',
        data
      },
      { returnDataOnly: true }
    )
  );
