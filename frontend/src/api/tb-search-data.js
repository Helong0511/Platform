/**
 * TB搜索数据管理 API
 * 已统一使用 request 函数，保持代码一致性
 * 包含特殊逻辑：超时控制、文件导入、批量操作等
 */
import { request, requestUpload } from '../utils/api';
import { getAdDataListTimeout } from '../utils/adDataRequest';
import { withCsrfMutate } from '../utils/csrfMutate';
import { createWithDataFilterApi } from './helpers/withDataFilters';

const tbWithDataFilters = createWithDataFilterApi('tb-search-data', { returnRaw: true });

// 获取TB搜索数据列表
/**
 * 分页获取 TB 搜索数据列表（支持数据权限过滤）。
 */
export const getTBSearchDataList = async (params) => {
  const timeout = getAdDataListTimeout();

  return request(
    {
      url: '/api/v1/tb-search-data/',
      method: 'get',
      params
    },
    { paginated: true, timeout }
  );
};

// 更新TB搜索数据
/**
 * 更新T B Search Data。
 */
export const updateTBSearchData = async (data) => {
  const { id, ...updateData } = data;
  return withCsrfMutate(() =>
    request(
      { url: `/api/v1/tb-search-data/${id}`, method: 'post', data: updateData },
      { returnDataOnly: true }
    )
  );
};

// 删除TB搜索数据
/**
 * 删除T B Search Data。
 */
export const deleteTBSearchData = async (dataId) =>
  withCsrfMutate(() =>
    request(
      { url: `/api/v1/tb-search-data/${dataId}`, method: 'delete' },
      { returnDataOnly: true }
    )
  );

// 批量删除TB搜索数据
/**
 * 批量Delete T B Search Data。
 */
export const batchDeleteTBSearchData = async (dataIds) =>
  withCsrfMutate(() =>
    request(
      { url: '/api/v1/tb-search-data/batch', method: 'delete', data: dataIds },
      { returnDataOnly: true }
    )
  );

// 导入TB搜索数据
/**
 * 导入T B Search Data。
 */
export const importTBSearchData = async (formData) =>
  requestUpload(
    {
      url: '/api/v1/tb-search-data/import',
      method: 'post',
      data: formData
    },
    { returnDataOnly: false, timeout: 60000 }
  );

export const getClientsWithTBSearchData = tbWithDataFilters.getClientsWithData;
export const getProductsWithTBSearchData = tbWithDataFilters.getProductsWithData;
export const getCountriesWithTBSearchData = tbWithDataFilters.getCountriesWithData;
