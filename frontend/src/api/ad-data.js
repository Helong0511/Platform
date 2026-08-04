/**
 * 广告数据管理 API
 * 已统一使用 request 函数，保持代码一致性
 * 包含特殊逻辑：超时控制、文件导入导出、批量操作等
 */
import { request, requestUpload } from '../utils/api';
import { requestListExport } from './helpers/exportDownload';
import { getAdDataListTimeout } from '../utils/adDataRequest';
import { withCsrfMutate } from '../utils/csrfMutate';
import { createWithDataFilterApi } from './helpers/withDataFilters';
import {
  fetchClientsAsUserSelectOptions,
  fetchProductsAsSelectOptions
} from './helpers/adDataSelectOptions';

const adDataWithDataFilters = createWithDataFilterApi('ad-data');

// 获取广告数据列表
/**
 * 分页获取广告数据列表。
 */
export const getAdDataList = async (params) => {
  const timeout = getAdDataListTimeout();

  return request({
    url: '/api/v1/ad-data/',
    method: 'get',
    params
  }, { paginated: true, timeout });
};

// 获取每日汇总数据
/**
 * 获取广告数据按日汇总。
 */
export const getDailySummary = async (params) => {
  const timeout = getAdDataListTimeout();

  return request({
    url: '/api/v1/ad-data/daily-summary',
    method: 'get',
    params
  }, { paginated: true, timeout });
};

// 注意：getAdDataDetail 和 getAdDataStats 已移除，因为未在代码中使用

// 导出广告数据（无数据错误由调用方展示提示）
/**
 * 导出Ad Data。
 */
export const exportAdData = (params) =>
  requestListExport(
    { url: '/api/v1/excel/export/ad-data', method: 'get', params },
    { defaultFilename: '广告数据导出.xlsx', warnOnNoData: false }
  );

// 导入广告数据
/**
 * 导入Ad Data。
 */
export const importAdData = async (formData) => {
  const result = await requestUpload(
    {
      url: '/api/v1/excel/import/ad-data',
      method: 'post',
      data: formData
    },
    { returnDataOnly: false, timeout: 60000 }
  );
  return result?.data ?? result;
};

// 更新广告数据
/**
 * 更新Ad Data。
 */
export const updateAdData = async (adData) => {
  const { id, ...updateData } = adData;
  return withCsrfMutate(() =>
    request(
      { url: `/api/v1/ad-data/${id}`, method: 'put', data: updateData },
      { returnDataOnly: true }
    )
  );
};

// 删除广告数据
/**
 * 删除Ad Data。
 */
export const deleteAdData = async (dataId) =>
  withCsrfMutate(() =>
    request(
      { url: `/api/v1/ad-data/${dataId}`, method: 'delete' },
      { returnDataOnly: true }
    )
  );

// 批量删除广告数据
/**
 * 批量Delete Ad Data。
 */
export const batchDeleteAdData = async (dataIds) =>
  withCsrfMutate(() =>
    request(
      { url: '/api/v1/ad-data/batch', method: 'delete', data: dataIds },
      { returnDataOnly: true }
    )
  );

export const getUsersForSelect = fetchClientsAsUserSelectOptions;

export const {
  getClientsWithData,
  getProductsWithData,
  getCountriesWithData,
  getAdUnitsWithData
} = adDataWithDataFilters;

export const getProductsForSelect = fetchProductsAsSelectOptions;

// 注意：getClientsByUserId 已移除，因为未在代码中使用

// 获取产品详情
/**
 * 根据 ID 获取产品信息。
 */
export const getProductById = async (productId) => {
  return request({
    url: `/api/v1/products/${productId}`,
    method: 'get'
  }, { returnDataOnly: true });
};

// 注意：getAdDataTrend 已移除，因为未在代码中使用

// 获取数据的日期范围
/**
 * 获取广告数据可用日期范围。
 */
export const getAdDataDateRange = async (clientId = null) => {
  const params = {};
  if (clientId) params.client_id = clientId;
  
  return request({
    url: '/api/v1/ad-data/date-range',
    method: 'get',
    params
  }, { returnDataOnly: true });
};

/**
 * 明细维护：数据来源 / 报表类型下拉目录（后端 ad_data_metadata 为真相源）
 */
export const getAdDataMetadataOptions = async () =>
  request(
    { url: '/api/v1/ad-data/metadata-options', method: 'get' },
    { returnDataOnly: true }
  );