/**
 * TB搜索数据管理 API
 * 已统一使用 request 函数，保持代码一致性
 * 包含特殊逻辑：超时控制、文件导入、批量操作等
 */
import { request, normalizePaginatedResponse, normalizeResponse, ensureCsrfToken, handleError, refreshCsrfTokenBeforeRequest } from '../utils/api';
import { getCsrfToken } from '../utils/csrfToken';
import axios from 'axios'; // 保留用于特殊场景（超时控制、文件上传）

// 获取TB搜索数据列表
export const getTBSearchDataList = async (params) => {
  const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  const timeout = isMobile ? 60000 : 45000;
  
  return request({
    url: '/api/v1/tb-search-data/',
    method: 'get',
    params
  }, { paginated: true, timeout });
};

// 更新TB搜索数据
export const updateTBSearchData = async (data) => {
  await refreshCsrfTokenBeforeRequest();
  
  const { id, ...updateData } = data;
  
  return request({
    url: `/api/v1/tb-search-data/${id}`,
    method: 'post',
    data: updateData
  }, { returnDataOnly: true });
};

// 删除TB搜索数据
export const deleteTBSearchData = async (dataId) => {
  await refreshCsrfTokenBeforeRequest();
  
  return request({
    url: `/api/v1/tb-search-data/${dataId}`,
    method: 'delete'
  }, { returnDataOnly: true });
};

// 批量删除TB搜索数据
export const batchDeleteTBSearchData = async (dataIds) => {
  await refreshCsrfTokenBeforeRequest();
  
  return request({
    url: '/api/v1/tb-search-data/batch',
    method: 'delete',
    data: dataIds
  }, { returnDataOnly: true });
};

// 导入TB搜索数据
export const importTBSearchData = async (formData) => {
  try {
    await refreshCsrfTokenBeforeRequest();
    
    const csrfToken = getCsrfToken();
    const headers = {};
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
    
    const response = await axios.post('/api/v1/tb-search-data/import', formData, {
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      timeout: 60000
    });
    return normalizeResponse(response);
  } catch (error) {
    throw error;
  }
};

// 获取有TB搜索数据的客户列表
export const getClientsWithTBSearchData = async (startDate = null, endDate = null) => {
  try {
    const params = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    
    const result = await request({
      url: '/api/v1/tb-search-data/clients-with-data',
      method: 'get',
      params
    }, { returnDataOnly: false });
    
    // 返回标准格式：{ code: 200, data: [...], count: ... }
    return result;
  } catch (error) {
    handleError(error);
  }
};

// 获取有TB搜索数据的产品列表
export const getProductsWithTBSearchData = async (clientId = null, startDate = null, endDate = null) => {
  try {
    const params = {};
    if (clientId) params.client_id = clientId;
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    
    const result = await request({
      url: '/api/v1/tb-search-data/products-with-data',
      method: 'get',
      params
    }, { returnDataOnly: false });
    
    // 返回标准格式：{ code: 200, data: [...], count: ... }
    return result;
  } catch (error) {
    handleError(error);
  }
};

// 获取有TB搜索数据的国家列表
export const getCountriesWithTBSearchData = async (clientId = null, productId = null, startDate = null, endDate = null) => {
  try {
    const params = {};
    if (clientId) params.client_id = clientId;
    if (productId) params.product_id = productId;
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    
    const result = await request({
      url: '/api/v1/tb-search-data/countries-with-data',
      method: 'get',
      params
    }, { returnDataOnly: false });
    
    // 返回标准格式：{ code: 200, data: [...], count: ... }
    return result;
  } catch (error) {
    handleError(error);
  }
};

