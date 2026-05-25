/**
 * 广告数据管理 API
 * 已统一使用 request 函数，保持代码一致性
 * 包含特殊逻辑：超时控制、文件导入导出、批量操作等
 */
import { request, normalizePaginatedResponse, normalizeResponse, ensureCsrfToken, handleError, refreshCsrfTokenBeforeRequest, requestBlobDownload, extractErrorMessage, requestUpload } from '../utils/api';
import { getCsrfToken } from '../utils/csrfToken';
import axios from 'axios'; // 保留用于特殊场景（超时控制）

// 获取广告数据列表
export const getAdDataList = async (params) => {
  // 检测是否为移动设备，移动端使用更长的超时时间
  const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  // 广告数据查询可能涉及大量数据，使用更长的超时时间
  const timeout = isMobile ? 60000 : 45000; // 移动端60秒，桌面端45秒
  
  return request({
    url: '/api/v1/ad-data/',
    method: 'get',
    params
  }, { paginated: true, timeout });
};

// 获取每日汇总数据
export const getDailySummary = async (params) => {
  // 检测是否为移动设备，移动端使用更长的超时时间
  const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  // 每日汇总查询涉及聚合计算，使用更长的超时时间
  const timeout = isMobile ? 60000 : 45000; // 移动端60秒，桌面端45秒
  
  return request({
    url: '/api/v1/ad-data/daily-summary',
    method: 'get',
    params
  }, { paginated: true, timeout });
};

// 注意：getAdDataDetail 和 getAdDataStats 已移除，因为未在代码中使用

// 导出广告数据
export const exportAdData = async (params) => {
  try {
    return await requestBlobDownload(
      { url: '/api/v1/excel/export/ad-data', method: 'get', params },
      { defaultFilename: '广告数据导出.xlsx' }
    );
  } catch (error) {
    const errorMsg = extractErrorMessage(error) || '导出失败';
    if (errorMsg.includes('无数据') || errorMsg.includes('不能导出') || errorMsg.includes('没有可导出')) {
      throw error;
    }
    handleError(error);
  }
};

// 导入广告数据
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
export const updateAdData = async (adData) => {
  // 确保CSRF令牌存在
  await refreshCsrfTokenBeforeRequest();
  
  // 准备请求数据，排除id字段（id在URL中）
  const { id, ...updateData } = adData;
  
  // 返回标准化的响应
  return request({
    url: `/api/v1/ad-data/${id}`,
    method: 'put',
    data: updateData
  }, { returnDataOnly: true });
};

// 删除广告数据
export const deleteAdData = async (dataId) => {
  return request({
    url: `/api/v1/ad-data/${dataId}`,
    method: 'delete'
  }, { returnDataOnly: true });
};

// 批量删除广告数据
export const batchDeleteAdData = async (dataIds) => {
  // 确保CSRF令牌存在
  await refreshCsrfTokenBeforeRequest();
  
  return request({
    url: '/api/v1/ad-data/batch',
    method: 'delete',
    data: dataIds
  }, { returnDataOnly: true });
};

// 获取用户列表（用于筛选）
export const getUsersForSelect = async () => {
  try {
    // 获取用户列表建立ID到full_name的映射
    const usersData = await request({
      url: '/api/v1/users/',
      method: 'get',
      params: { page_size: 100 }
    }, { paginated: true });
    const users = usersData.data || [];
    
    const userMap = users.reduce((acc, user) => {
      if (user && user.id) {
        acc[user.id] = user.full_name || user.username || '未知用户';
      }
      return acc;
    }, {});

    // 获取客户端数据并关联用户名
    const clientsData = await request({
      url: '/api/v1/clients/',
      method: 'get',
      params: { page_size: 100 }
    }, { paginated: true });
    const clients = clientsData.data || [];
    
    return clients.map(item => {
      if (!item || !item.id) return null;
      return {
        value: item.id,
        label: `${item.id} - ${userMap[item.user_id] || '未知用户'}`
      };
    }).filter(item => item !== null);
  } catch (error) {
    handleError(error, { showMessage: true });
    return [];
  }
};

// 获取产品列表（用于筛选）
// 获取有数据的客户列表（用于下拉选择）
export const getClientsWithData = async (startDate = null, endDate = null) => {
  try {
    const params = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    
    const result = await request({
      url: '/api/v1/ad-data/clients-with-data',
      method: 'get',
      params
    }, { returnDataOnly: false });
    
    // 返回包含data和count的对象，方便前端判断是否有数据
    // result已经是标准格式：{ code: 200, data: [...], count: ... }
    return {
      data: result.data || [],
      count: result.count || 0
    };
  } catch (error) {
    handleError(error);
  }
};

// 获取有数据的产品列表（用于下拉选择）
export const getProductsWithData = async (clientId = null, startDate = null, endDate = null) => {
  try {
    const params = {};
    if (clientId) params.client_id = clientId;
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    
    const result = await request({
      url: '/api/v1/ad-data/products-with-data',
      method: 'get',
      params
    }, { returnDataOnly: false });
    
    // 返回包含data和count的对象，方便前端判断是否有数据
    // result已经是标准格式：{ code: 200, data: [...], count: ... }
    return {
      data: result.data || [],
      count: result.count || 0
    };
  } catch (error) {
    handleError(error);
  }
};

// 获取有数据的国家列表（用于下拉选择）
export const getCountriesWithData = async (clientId = null, productId = null, startDate = null, endDate = null) => {
  try {
    const params = {};
    if (clientId) params.client_id = clientId;
    if (productId) params.product_id = productId;
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    
    const result = await request({
      url: '/api/v1/ad-data/countries-with-data',
      method: 'get',
      params
    }, { returnDataOnly: false });
    
    // 返回包含data和count的对象，方便前端判断是否有数据
    // result已经是标准格式：{ code: 200, data: [...], count: ... }
    return {
      data: result.data || [],
      count: result.count || 0
    };
  } catch (error) {
    handleError(error);
  }
};

export const getProductsForSelect = async (clientId = null) => {
  try {
    const params = { page_size: 100 };
    if (clientId) params.client_id = clientId;
    
    const productsData = await request({
      url: '/api/v1/products/',
      method: 'get',
      params
    }, { paginated: true });
    const products = productsData.data || [];
    
    return products.map(item => {
      if (!item || !item.id) return null;
      return {
        label: `${item.id} - ${item.name || '未知产品'}`,
        value: item.id
      };
    }).filter(item => item !== null);
  } catch (error) {
    // 静默失败，返回空数组
    return [];
  }
};

// 注意：getClientsByUserId 已移除，因为未在代码中使用

// 获取产品详情
export const getProductById = async (productId) => {
  return request({
    url: `/api/v1/products/${productId}`,
    method: 'get'
  }, { returnDataOnly: true });
};

// 注意：getAdDataTrend 已移除，因为未在代码中使用

// 获取数据的日期范围
export const getAdDataDateRange = async (clientId = null) => {
  const params = {};
  if (clientId) params.client_id = clientId;
  
  return request({
    url: '/api/v1/ad-data/date-range',
    method: 'get',
    params
  }, { returnDataOnly: true });
};