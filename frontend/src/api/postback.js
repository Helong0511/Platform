/**
 * Postback 回传管理 API
 *
 * 职责：转化记录查询与统计、转化状态更新、IP 白名单 CRUD 及批量导入。
 * @file api/postback.js
 */
import { request } from '../utils/api';
import { createCrudApi } from '@/utils/crudApi';
import { withCsrfMutate } from '../utils/csrfMutate';

/**
 * 分页获取 Postback 转化记录列表。
 * @param {Object} params 分页与筛选参数
 */
export const getPostbackConversions = async (params) => {
  return request({
    url: '/api/v1/postback/conversions',
    method: 'get',
    params
  }, { paginated: true });
};

/**
 * 获取 Postback 转化汇总统计。
 */
export const getPostbackStats = async (params = {}) => {
  return request({
    url: '/api/v1/postback/stats',
    method: 'get',
    params
  }, { returnDataOnly: true });
};

/**
 * 更新指定转化记录的处理状态。
 */
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
  getIpWhitelist,
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

/**
 * 批量创建 Postback IP 白名单条目。
 */
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

