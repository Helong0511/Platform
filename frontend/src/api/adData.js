/**
 * 广告数据管理 API
 * 已统一使用 request 函数，保持代码一致性
 * 包含特殊逻辑：超时控制、文件导入导出、批量操作等
 */
import { request, normalizePaginatedResponse, normalizeResponse, ensureCsrfToken, handleError, refreshCsrfTokenBeforeRequest } from '../utils/api';
import axios from 'axios'; // 保留用于特殊场景（超时控制、文件上传下载）

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
    const response = await axios.get('/api/v1/excel/export/ad-data', {
      params,
      responseType: 'blob' // 默认使用blob，因为成功时返回Excel文件
    });

    // 检查响应类型和大小
    const contentType = response.headers['content-type'] || '';
    const blobSize = response.data.size || 0;
    
    // 如果响应是JSON格式，说明是错误响应（业务错误返回HTTP 200，但响应体是JSON）
    if (contentType.includes('application/json')) {
      // 解析JSON错误响应
      const text = await response.data.text();
      const errorData = JSON.parse(text);
      if (errorData.code !== undefined && errorData.code !== 200) {
        const errorMsg = errorData.detail || errorData.message || '导出失败';
        const error = new Error(errorMsg);
        error.code = errorData.code;
        error.response = {
          data: errorData,
          status: 200,
          statusText: 'OK'
        };
        throw error;
      }
    }

    // 检查blob大小，如果很小（小于5KB）可能是错误JSON（错误响应可能被当作blob）
    // Excel文件通常至少几KB，而JSON错误响应通常只有几百字节
    // 注意：需要克隆blob，因为读取后不能再次使用
    if (blobSize > 0 && blobSize < 5000) {
      try {
        // 克隆blob以便读取后仍可使用
        const blobClone = response.data.slice(0);
        const text = await blobClone.text();
        // 尝试解析为JSON
        const errorData = JSON.parse(text);
        if (errorData.code !== undefined && errorData.code !== 200) {
          const errorMsg = errorData.detail || errorData.message || '导出失败';
          const error = new Error(errorMsg);
          error.code = errorData.code;
          error.response = {
            data: errorData,
            status: 200,
            statusText: 'OK'
          };
          throw error;
        }
      } catch (parseError) {
        // 解析失败，可能是正常的Excel文件（虽然很小），继续使用原始blob
      }
    }

    // 创建下载链接
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;

    // 从响应头获取文件名
    const contentDisposition = response.headers['content-disposition'];
    let fileName = '广告数据导出.xlsx';
    if (contentDisposition) {
      // 支持 UTF-8 编码的文件名
      const utf8Match = contentDisposition.match(/filename\*=UTF-8''(.+)/);
      if (utf8Match && utf8Match[1]) {
        fileName = decodeURIComponent(utf8Match[1]);
      } else {
        const match = contentDisposition.match(/filename=(.*)/);
        if (match && match[1]) {
          fileName = decodeURIComponent(match[1]);
        }
      }
    }

    link.setAttribute('download', fileName);
    document.body.appendChild(link);
    link.click();

    // 清理
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);

    // 不在这里显示成功消息，由调用方处理
    return true;
  } catch (error) {
    // 如果是blob响应但实际是错误，尝试解析
    if (error.response && error.response.data instanceof Blob) {
      try {
        const text = await error.response.data.text();
        const errorData = JSON.parse(text);
        if (errorData.code !== undefined && errorData.code !== 200) {
          const errorMsg = errorData.detail || errorData.message || '导出失败';
          const customError = new Error(errorMsg);
          customError.code = errorData.code;
          customError.response = {
            data: errorData,
            status: 200,
            statusText: 'OK'
          };
          throw customError;
        }
      } catch (parseError) {
        // 解析失败，使用原始错误
      }
    }
    
    handleError(error);
  }
};

// 导入广告数据
export const importAdData = async (formData) => {
  try {
    // 确保CSRF令牌存在
    await refreshCsrfTokenBeforeRequest();
    
    // 获取CSRF令牌（如果存在）
    const csrfToken = sessionStorage.getItem('csrf_token');
    
    // 构建headers，确保包含CSRF令牌
    // 注意：不要手动设置 Content-Type，让 axios 自动处理 multipart/form-data 的 boundary
    const headers = {};
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
    
    const response = await axios.post('/api/v1/excel/import/ad-data', formData, {
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      timeout: 60000  // 导入可能需要较长时间，设置60秒超时
    });
    
    // 响应结构: { code: 200, message: "success", data: ExcelImportResponse }
    // ExcelImportResponse 包含: { message, status, imported_rows, failed_rows, error_details }
    const normalized = normalizeResponse(response, { returnDataOnly: false });
    
    // 返回 data 字段中的 ExcelImportResponse 对象
    return normalized?.data || normalized;
  } catch (error) {
    // 不在API层显示错误消息，由调用方处理
    throw error;
  }
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