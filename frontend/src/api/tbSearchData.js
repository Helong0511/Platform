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

