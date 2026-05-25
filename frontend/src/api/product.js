/**
 * 产品管理 API
 * 已统一使用 request 函数，保持代码一致性
 * 包含特殊逻辑：产品分配、批量更新、超时处理、CSRF重试等
 */
import { request, extractErrorMessage, refreshCsrfTokenBeforeRequest, handleError } from '../utils/api';
import { ElMessage } from 'element-plus';

// 获取产品列表
export const getProductList = async (params = {}) => {
  return request({
    url: '/api/v1/products/',
    method: 'get',
    params
  }, { paginated: true });
};

// 获取产品详情
export const getProductDetail = async (id, options = {}) => {
  const { silent = false } = options; // 添加 silent 选项，控制是否显示错误消息
  try {
    // 使用request函数，支持自定义超时时间（10秒）
    return await request({
      url: `/api/v1/products/${id}`,
      method: 'get'
    }, { returnDataOnly: true, timeout: 10000, silent });
  } catch (error) {
    throw error;
  }
};

// 创建产品
export const createProduct = async (productData) => {
  // 在保存前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/products/?page_size=1');
  
  return request({
    url: '/api/v1/products/',
    method: 'post',
    data: productData
  }, { returnDataOnly: true });
};

// 更新产品
export const updateProduct = async (id, productData) => {
  // 在保存前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/products/?page_size=1');
  
  return request({
    url: `/api/v1/products/${id}`,
    method: 'put',
    data: productData
  }, { returnDataOnly: true });
};

// 删除产品
export const deleteProduct = async (id) => {
  // 在删除前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/products/?page_size=1');
  
  return request({
    url: `/api/v1/products/${id}`,
    method: 'delete'
  }, { returnDataOnly: true });
};

// 获取可用的产品名称列表（用于添加产品时选择）
export const getAvailableProductNames = async (excludeClientId = null, search = null) => {
  try {
    const params = {};
    if (excludeClientId) params.exclude_client_id = excludeClientId;
    if (search) params.search = search;
    
    const normalized = await request({
      url: '/api/v1/products/available-names',
      method: 'get',
      params
    }, { returnDataOnly: false });
    
    // 返回包含data和count的对象，方便前端判断是否有数据
    return {
      data: normalized.data || [],
      count: normalized.count || 0
    };
  } catch (error) {
    // 获取产品名称列表失败，错误已通过ElMessage显示
    return { data: [], count: 0 };
  }
};

// 获取产品的分配历史
export const getProductAssignments = async (productId) => {
  try {
    // 增加超时时间，因为第一次查询可能需要建立数据库连接（30秒超时）
    return await request({
      url: `/api/v1/product-assignments/products/${productId}/assignments`,
      method: 'get'
    }, { returnDataOnly: true, timeout: 30000 });
  } catch (error) {
    // 如果是超时错误，提供更友好的提示
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      const { ElMessage } = await import('element-plus');
      ElMessage.error('请求超时，请稍后重试。如果问题持续，请联系管理员。');
    }
    throw error;
  }
};

// 获取客户的分配历史（管理员）
export const getClientAssignments = async (clientId) => {
  return request({
    url: `/api/v1/product-assignments/clients/${clientId}/assignments`,
    method: 'get'
  }, { returnDataOnly: true });
};

// 更新产品分配历史的日期（管理员）
export const updateAssignmentDates = async (assignmentId, dateUpdate) => {
  await refreshCsrfTokenBeforeRequest('/api/v1/products/');
  return request({
    url: `/api/v1/product-assignments/assignments/${assignmentId}/dates`,
    method: 'put',
    data: dateUpdate
  }, { returnDataOnly: true, timeout: 30000 });
};

// 批量更新产品分配历史的日期（管理员）
export const batchUpdateAssignmentDates = async (updates) => {
  try {
    await refreshCsrfTokenBeforeRequest('/api/v1/products/');
    return await request({
      url: '/api/v1/product-assignments/assignments/batch-update-dates',
      method: 'put',
      data: { updates }
    }, { returnDataOnly: true, timeout: 60000 });
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    if (error.response?.status === 403 && /csrf|令牌/i.test(errorMsg)) {
      ElMessage.error('安全验证失败，请刷新页面后重试');
      sessionStorage.removeItem('csrf_token');
    } else {
      handleError(error, {
        customErrorHandler: () => {
          ElMessage.error(errorMsg || '批量更新失败，请稍后重试');
        }
      });
    }
    throw error;
  }
};

