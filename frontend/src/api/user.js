import axios from 'axios';
import { request, normalizePaginatedResponse, normalizeResponse, extractErrorMessage, isErrorHandled, ensureCsrfToken, refreshCsrfTokenBeforeRequest, handleError, handleFileDownload, refreshCsrfToken } from '../utils/api';
import { ElMessage } from 'element-plus';
import { getSuccessMessage, getWarningMessage } from '../utils/messages';

/**
 * 获取用户列表
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页条数
 * @param {string} [params.username] - 用户名筛选
 * @param {string} [params.role] - 角色筛选
 * @returns {Promise<Object>} 用户列表数据
 */
export const getUsers = async (params) => {
  return request({
    url: '/api/v1/users/',
    method: 'get',
    params
  }, { paginated: true });
};

/**
 * 搜索用户（根据用户名或ID）
 * @param {string|number} searchTerm - 搜索关键词（用户名或ID）
 * @returns {Promise<Object|null>} 找到的用户对象，如果未找到返回null
 */
export const searchUser = async (searchTerm) => {
  try {
    if (!searchTerm || searchTerm.toString().trim() === '') {
      return null;
    }

    const term = searchTerm.toString().trim();
    
    // 如果是纯数字，可能是ID，先尝试通过ID查找
    if (/^\d+$/.test(term)) {
      try {
        const response = await axios.get(`/api/v1/users/${term}`);
        const result = normalizeResponse(response, { returnDataOnly: true });
        if (result && result.id) {
          return result;
        }
      } catch (error) {
        // ID查找失败，继续用用户名查找
      }
    }

    // 通过用户名查找
    const response = await axios.get('/api/v1/users/', { 
      params: { 
        username: term,
        page_size: 10 
      } 
    });
    const usersData = normalizePaginatedResponse(response);
    
    if (usersData.data && usersData.data.length > 0) {
      // 精确匹配用户名
      const exactMatch = usersData.data.find(user => 
        user.username && user.username.toLowerCase() === term.toLowerCase()
      );
      if (exactMatch) {
        return exactMatch;
      }
      // 返回第一个匹配结果
      return usersData.data[0];
    }
    
    return null;
  } catch (error) {
    // 静默失败，返回null
    return null;
  }
};

/**
 * 获取用户详情
 * @param {number} id - 用户ID
 * @returns {Promise<Object>} 用户详情数据
 */
export const getUserDetail = async (id) => {
  return request({
    url: `/api/v1/users/${id}`,
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 获取当前用户信息
 * @returns {Promise<Object>} 当前用户信息
 */
export const getCurrentUserInfo = async () => {
  return request({
    url: '/api/v1/users/me',
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 创建用户
 * @param {Object} userData - 用户数据
 * @returns {Promise<Object>} 创建的用户数据
 */
export const createUser = async (userData) => {
  try {
    // 在保存前刷新CSRF令牌，确保使用最新的令牌
    await refreshCsrfTokenBeforeRequest('/api/v1/users/stats');
    
    const response = await axios.post('/api/v1/users/', userData);
    return normalizeResponse(response);
  } catch (error) {
    handleError(error);
  }
};

/**
 * 更新用户
 * @param {number} id - 用户ID
 * @param {Object} userData - 用户数据
 * @returns {Promise<Object>} 更新后的用户数据
 */
export const updateUser = async (id, userData) => {
  try {
    // 在保存前刷新CSRF令牌，确保使用最新的令牌
    await refreshCsrfTokenBeforeRequest('/api/v1/users/stats');
    
    const response = await axios.put(`/api/v1/users/${id}`, userData);
    return normalizeResponse(response);
  } catch (error) {
    handleError(error);
  }
};

/**
 * 删除用户
 * @param {number} id - 用户ID
 * @returns {Promise<boolean>} 是否删除成功
 */
export const deleteUser = async (id) => {
  try {
    // 在删除前刷新CSRF令牌，确保使用最新的令牌
    await refreshCsrfTokenBeforeRequest('/api/v1/users/stats');
    
    await axios.delete(`/api/v1/users/${id}`);
    return true;
  } catch (error) {
    handleError(error);
  }
};

/**
 * 导出用户数据
 * @param {Object} params - 查询参数（与getUsers相同）
 * @returns {Promise<void>}
 */
export const exportUsers = async (params = {}) => {
  try {
    const response = await axios.get('/api/v1/users/export/excel', {
      params,
      responseType: 'blob'
    });
    
    // 处理文件下载
    handleFileDownload(response, '用户数据.xlsx', () => {
      ElMessage.success(getSuccessMessage('USER_EXPORT_SUCCESS'));
    });
  } catch (error) {
    // 提取错误消息，优先使用 detail，然后是 message
    const errorMsg = extractErrorMessage(error) || '导出失败';
    
    // 如果是"无数据，不能导出"的错误，直接显示该消息
    if (errorMsg.includes('无数据') || errorMsg.includes('不能导出')) {
      ElMessage.warning(getWarningMessage('NO_DATA_TO_EXPORT'));
    } else {
      handleError(error);
    }
  }
};

/**
 * 获取用户统计信息
 * @returns {Promise<Object>} 统计信息
 */
export const getUserStats = async () => {
  return request({
    url: '/api/v1/users/stats',
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 修改当前用户密码
 * @param {Object} passwordData - 密码数据
 * @param {string} passwordData.old_password - 当前密码
 * @param {string} passwordData.new_password - 新密码
 * @returns {Promise<Object>} 更新结果
 */
export const changePassword = async (passwordData) => {
  try {
    // 在保存前刷新CSRF令牌，确保使用最新的令牌
    await refreshCsrfToken('/api/v1/users/stats');
    await ensureCsrfToken();
    
    const response = await axios.put('/api/v1/users/me/password', passwordData);
    return normalizeResponse(response);
  } catch (error) {
    handleError(error);
  }
};

/**
 * 退出登录
 * @returns {Promise<void>}
 */
export const logout = async () => {
  try {
    await axios.post('/api/v1/auth/logout');
    // 退出登录成功，不显示消息（由store处理）
  } catch (error) {
    // 即使API调用失败，也要清除本地状态
    // 不显示错误消息，避免影响用户体验
    // 错误可能是token已过期，这是正常的
  }
};
