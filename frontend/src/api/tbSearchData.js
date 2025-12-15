import axios from 'axios';
import { ElMessage } from 'element-plus';
import { normalizePaginatedResponse, normalizeResponse, extractErrorMessage, isErrorHandled, ensureCsrfToken } from '../utils/api';

// 获取TB搜索数据列表
export const getTBSearchDataList = async (params) => {
  try {
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    const timeout = isMobile ? 60000 : 45000;
    
    const response = await axios.get('/api/v1/tb-search-data/', { 
      params,
      timeout: timeout
    });
    return normalizePaginatedResponse(response);
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

// 更新TB搜索数据
export const updateTBSearchData = async (data) => {
  try {
    await ensureCsrfToken();
    const { id, ...updateData } = data;
    const csrfToken = sessionStorage.getItem('csrf_token');
    const headers = { 'Content-Type': 'application/json' };
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
    
    const response = await axios.post(`/api/v1/tb-search-data/${id}`, updateData, { headers });
    return normalizeResponse(response);
  } catch (error) {
    throw error;
  }
};

// 删除TB搜索数据
export const deleteTBSearchData = async (dataId) => {
  try {
    await ensureCsrfToken();
    const csrfToken = sessionStorage.getItem('csrf_token');
    const headers = {};
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;

    const response = await axios.delete(`/api/v1/tb-search-data/${dataId}`, { headers });
    return normalizeResponse(response);
  } catch (error) {
    throw error;
  }
};

// 批量删除TB搜索数据
export const batchDeleteTBSearchData = async (dataIds) => {
  try {
    await ensureCsrfToken();
    const csrfToken = sessionStorage.getItem('csrf_token');
    const headers = { 'Content-Type': 'application/json' };
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
    
    const response = await axios.delete('/api/v1/tb-search-data/batch', {
      data: dataIds,
      headers
    });
    return normalizeResponse(response);
  } catch (error) {
    throw error;
  }
};

// 导入TB搜索数据
export const importTBSearchData = async (formData) => {
  try {
    await ensureCsrfToken();
    const csrfToken = sessionStorage.getItem('csrf_token');
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
    
    const response = await axios.get('/api/v1/tb-search-data/clients-with-data', { params });
    return normalizeResponse(response, { returnDataOnly: false });
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

// 获取有TB搜索数据的产品列表
export const getProductsWithTBSearchData = async (clientId = null, startDate = null, endDate = null) => {
  try {
    const params = {};
    if (clientId) params.client_id = clientId;
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    
    const response = await axios.get('/api/v1/tb-search-data/products-with-data', { params });
    return normalizeResponse(response, { returnDataOnly: false });
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
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
    
    const response = await axios.get('/api/v1/tb-search-data/countries-with-data', { params });
    return normalizeResponse(response, { returnDataOnly: false });
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

