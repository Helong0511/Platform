/**
 * 客户管理 API
 * 已统一使用 request 函数，保持代码一致性
 * 包含特殊逻辑：缓存机制、请求去重、文件导出等
 */
import { request, normalizeResponse, extractErrorMessage, ensureCsrfToken, handleError, refreshCsrfTokenBeforeRequest, refreshCsrfToken, handleFileDownload } from '../utils/api';
import { ElMessage } from 'element-plus';
import { getSuccessMessage, getWarningMessage } from '../utils/messages';
import axios from 'axios'; // 保留用于特殊场景（缓存、超时控制、文件下载）

// 全局缓存和请求去重机制
const clientDetailCache = new Map(); // 客户详情缓存
const fetchingClientDetails = new Set(); // 正在获取的客户详情ID集合
const CACHE_TTL = 5 * 60 * 1000; // 缓存有效期：5分钟

// 获取客户列表
export const getClientList = async (params = {}) => {
  return request({
    url: '/api/v1/clients/',
    method: 'get',
    params
  }, { paginated: true });
};

// 获取客户详情（带缓存和请求去重）
export const getClientDetail = async (id, options = {}) => {
  const { useCache = true, silent = false } = options;
  
  // 检查缓存
  if (useCache && clientDetailCache.has(id)) {
    const cached = clientDetailCache.get(id);
    const now = Date.now();
    // 检查缓存是否过期
    if (cached.expiresAt > now) {
      return cached.data;
    } else {
      // 缓存过期，删除
      clientDetailCache.delete(id);
    }
  }
  
  // 如果正在获取中，等待
  if (fetchingClientDetails.has(id)) {
    let retries = 0;
    while (fetchingClientDetails.has(id) && retries < 20) {
      await new Promise(resolve => setTimeout(resolve, 100));
      retries++;
      // 检查缓存（可能在等待期间已获取完成）
      if (clientDetailCache.has(id)) {
        const cached = clientDetailCache.get(id);
        if (cached.expiresAt > Date.now()) {
          return cached.data;
        }
      }
    }
  }
  
  // 标记为正在获取
  fetchingClientDetails.add(id);
  
  try {
    const data = await request({
      url: `/api/v1/clients/${id}`,
      method: 'get'
    }, { returnDataOnly: true, timeout: 10000, silent });
    
    // 缓存结果（最多缓存50个客户）
    if (clientDetailCache.size >= 50) {
      // 删除最旧的缓存（FIFO）
      const firstKey = clientDetailCache.keys().next().value;
      clientDetailCache.delete(firstKey);
    }
    clientDetailCache.set(id, {
      data,
      expiresAt: Date.now() + CACHE_TTL
    });
    
    return data;
  } catch (error) {
    // 429错误不缓存，其他错误可以缓存空值避免重复请求（但429错误不应该缓存）
    if (error.response?.status !== 429 && error.response?.status !== 500) {
      // 缓存空值，避免重复请求（但设置较短的过期时间）
      clientDetailCache.set(id, {
        data: null,
        expiresAt: Date.now() + 30000 // 30秒
      });
    }
    
    // 如果是429错误且silent为true，不显示错误消息
    if (error.response?.status === 429 && silent) {
      throw error;
    }
    
    // 使用统一的错误处理，但支持silent模式
    if (silent) {
      handleError(error, { showMessage: false });
    } else {
      handleError(error);
    }
    throw error;
  } finally {
    fetchingClientDetails.delete(id);
  }
};

// 创建客户
export const createClient = async (clientData) => {
  // 在保存前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfTokenBeforeRequest('/api/v1/clients/?page_size=1');
  
  // 不在这里显示成功消息，由调用方处理
  return request({
    url: '/api/v1/clients/',
    method: 'post',
    data: clientData
  }, { returnDataOnly: true });
};

// 清除客户详情缓存
export const clearClientDetailCache = (id = null) => {
  if (id) {
    clientDetailCache.delete(id);
  } else {
    clientDetailCache.clear();
  }
};

// 更新客户
export const updateClient = async (id, clientData) => {
  // 在保存前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfToken('/api/v1/clients/?page_size=1');
  await ensureCsrfToken();
  
  const result = await request({
    url: `/api/v1/clients/${id}`,
    method: 'put',
    data: clientData
  }, { returnDataOnly: true });
  
  // 清除该客户的缓存，因为信息已更新
  clearClientDetailCache(id);
  // 不在这里显示成功消息，由调用方处理
  return result;
};

// 快速更新客户开关
export const updateClientSwitches = async (id, switchData) => {
  // 在保存前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfToken('/api/v1/clients/?page_size=1');
  await ensureCsrfToken();
  
  const result = await request({
    url: `/api/v1/clients/${id}/switches`,
    method: 'patch',
    data: switchData
  }, { returnDataOnly: true });
  
  // 清除该客户的缓存，因为开关状态已更新
  clearClientDetailCache(id);
  return result;
};

// 删除客户
export const deleteClient = async (id) => {
  // 在删除前刷新CSRF令牌，确保使用最新的令牌
  await refreshCsrfToken('/api/v1/clients/?page_size=1');
  await ensureCsrfToken();
  
  await request({
    url: `/api/v1/clients/${id}`,
    method: 'delete'
  });
  // 不在这里显示成功消息，由调用方处理
  return true;
};

// 导出客户数据
export const exportClients = async (params = {}) => {
  try {
    const response = await axios.get('/api/v1/clients/export', {
      params,
      responseType: 'blob'
    });

    // 处理文件下载
    handleFileDownload(response, '客户数据导出.xlsx', () => {
      ElMessage.success(getSuccessMessage('CLIENT_EXPORT_SUCCESS'));
    });
    
    return true;
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    
    // 特殊处理：无数据时的警告提示
    if (errorMsg.includes('无数据') || errorMsg.includes('不能导出')) {
      ElMessage.warning(getWarningMessage('NO_DATA_TO_EXPORT'));
    } else {
      handleError(error);
    }
  }
};
