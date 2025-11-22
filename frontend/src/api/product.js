import axios from 'axios';
import { normalizePaginatedResponse, normalizeResponse, extractErrorMessage, isErrorHandled } from '../utils/api';
import { ElMessage } from 'element-plus';

// 获取产品列表
export const getProductList = async (params = {}) => {
  try {
    const response = await axios.get('/api/v1/products/', { params });
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

// 获取产品详情
export const getProductDetail = async (id, options = {}) => {
  const { silent = false } = options; // 添加 silent 选项，控制是否显示错误消息
  try {
    const response = await axios.get(`/api/v1/products/${id}`, {
      timeout: 10000 // 设置10秒超时
    });
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    // 如果 silent 为 true，不显示错误消息
    if (!silent) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
    throw error;
  }
};

import { logger } from '../utils/logger';

// 创建产品
export const createProduct = async (productData) => {
  try {
    // 确保CSRF令牌存在
    const csrfToken = sessionStorage.getItem('csrf_token');
    if (!csrfToken) {
      logger.error('[createProduct] CSRF令牌缺失，无法创建产品');
      throw new Error('CSRF令牌缺失，请刷新页面后重试');
    }
    
    const response = await axios.post('/api/v1/products/', productData);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    throw error;
  }
};

// 更新产品
export const updateProduct = async (id, productData) => {
  try {
    // 确保CSRF令牌存在
    const csrfToken = sessionStorage.getItem('csrf_token');
    if (!csrfToken) {
      logger.error(`[updateProduct] CSRF令牌缺失，无法更新产品 ${id}`);
      throw new Error('CSRF令牌缺失，请刷新页面后重试');
    }
    
    const response = await axios.put(`/api/v1/products/${id}`, productData);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    throw error;
  }
};

// 删除产品
export const deleteProduct = async (id) => {
  try {
    // 确保CSRF令牌存在
    const csrfToken = sessionStorage.getItem('csrf_token');
    if (!csrfToken) {
      logger.error(`[deleteProduct] CSRF令牌缺失，无法删除产品 ${id}`);
      throw new Error('CSRF令牌缺失，请刷新页面后重试');
    }
    
    const response = await axios.delete(`/api/v1/products/${id}`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    throw error;
  }
};

// 获取可用的产品名称列表（用于添加产品时选择）
export const getAvailableProductNames = async (excludeClientId = null, search = null) => {
  try {
    const params = {};
    if (excludeClientId) params.exclude_client_id = excludeClientId;
    if (search) params.search = search;
    const response = await axios.get('/api/v1/products/available-names', { params });
    const normalized = normalizeResponse(response, { returnDataOnly: false });
    // 返回包含data和count的对象，方便前端判断是否有数据
    return {
      data: normalized.data || [],
      count: normalized.count || 0
    };
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    // 获取产品名称列表失败，错误已通过ElMessage显示
    return { data: [], count: 0 };
  }
};

// 获取产品的分配历史
export const getProductAssignments = async (productId) => {
  try {
    // 增加超时时间，因为第一次查询可能需要建立数据库连接
    const response = await axios.get(`/api/v1/product-assignments/products/${productId}/assignments`, {
      timeout: 30000 // 30秒超时
    });
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    // 如果是超时错误，提供更友好的提示
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      ElMessage.error('请求超时，请稍后重试。如果问题持续，请联系管理员。');
    } else {
      ElMessage.error(errorMsg);
    }
    throw error;
  }
};

// 获取客户的分配历史（管理员）
export const getClientAssignments = async (clientId) => {
  try {
    const response = await axios.get(`/api/v1/product-assignments/clients/${clientId}/assignments`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

// 更新产品分配历史的日期（管理员）
export const updateAssignmentDates = async (assignmentId, dateUpdate) => {
  // 重试函数，用于在CSRF token失败时自动重试
  const attemptUpdate = async (retryCount = 0) => {
    try {
      // 如果是重试，先获取新的CSRF token
      if (retryCount > 0) {
        try {
          // 发送一个GET请求来获取最新的CSRF token
          // 注意：使用productId可能不存在，使用一个通用的端点
          await axios.get('/api/v1/products/', {
            params: { page_size: 1 },
            timeout: 5000,
            validateStatus: () => true // 接受任何状态码
          });
          // 等待响应拦截器处理完响应头
          await new Promise(resolve => setTimeout(resolve, 200));
        } catch (tokenError) {
          logger.warn(`[updateAssignmentDates] 获取CSRF token时出错: ${tokenError.message}`);
        }
      }
      
      // 检查CSRF token是否存在
      const csrfToken = sessionStorage.getItem('csrf_token');
      if (!csrfToken) {
        throw new Error('CSRF令牌缺失，请刷新页面后重试');
      }
      
      // 发送PUT请求
      const response = await axios.put(`/api/v1/product-assignments/assignments/${assignmentId}/dates`, dateUpdate);
      
      // 请求成功后，等待一小段时间，确保响应拦截器已处理完CSRF令牌更新
      await new Promise(resolve => setTimeout(resolve, 100));
      
      return normalizeResponse(response, { returnDataOnly: true });
    } catch (error) {
      // 如果是CSRF相关错误（403），且还没有重试过，尝试重试一次
      if (error.response?.status === 403 && retryCount === 0) {
        const errorMsg = extractErrorMessage(error);
        if (errorMsg.includes('CSRF') || errorMsg.includes('csrf') || errorMsg.includes('令牌')) {
          logger.warn(`[updateAssignmentDates] CSRF token验证失败，尝试重新获取token并重试`);
          // 清除旧的token
          sessionStorage.removeItem('csrf_token');
          // 重试一次
          return attemptUpdate(1);
        }
      }
      // 其他错误或重试后仍然失败，抛出错误
      throw error;
    }
  };
  
  try {
    return await attemptUpdate(0);
  } catch (error) {
    if (isErrorHandled(error)) {
      throw error;
    }
    
    const errorMsg = extractErrorMessage(error);
    
    // 如果是CSRF相关错误，提供更友好的提示（但不显示错误消息，由调用方处理）
    if (error.response?.status === 403) {
      if (errorMsg.includes('CSRF') || errorMsg.includes('csrf') || errorMsg.includes('令牌')) {
        // 不在这里显示错误消息，由批量保存函数统一处理
        // 清除旧的token
        sessionStorage.removeItem('csrf_token');
      }
    }
    throw error;
  }
};

