/**
 * ML模型管理 API
 * 已统一使用 request 函数，保持代码一致性
 * 包含特殊逻辑：文件上传、FormData处理等
 */
import { request, normalizeResponse, extractErrorMessage, isErrorHandled, ensureCsrfToken, handleError, refreshCsrfTokenBeforeRequest } from '../utils/api';
import { ElMessage } from 'element-plus';
import { getWarningMessage } from '../utils/messages';
import { logger } from '../utils/logger';
import axios from 'axios'; // 保留用于特殊场景（文件上传、FormData处理）

/**
 * 验证Excel列名映射
 * @param {File} file - Excel文件
 * @returns {Promise<Object>} 验证结果
 */
export const validateExcelData = async (file) => {
  try {
    // 确保CSRF令牌存在
    await refreshCsrfTokenBeforeRequest();

    const formData = new FormData();
    formData.append('file', file);

    // 获取CSRF令牌（如果存在）
    const csrfToken = sessionStorage.getItem('csrf_token');

    // 构建headers，确保包含CSRF令牌
    // 注意：不要手动设置 Content-Type，让 axios 自动处理 multipart/form-data 的 boundary
    const headers = {};
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }

    const response = await axios.post('/api/v1/ml-model/validate', formData, {
      headers: Object.keys(headers).length > 0 ? headers : undefined
    });
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    handleError(error);
  }
};

/**
 * 获取映射规则状态
 * @returns {Promise<Object>} 状态信息
 */
export const getModelStatus = async () => {
  return request({
    url: '/api/v1/ml-model/status',
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 获取应用时区配置
 * @returns {Promise<string>} 时区字符串
 */
export const getTimezone = async () => {
  try {
    const data = await request({
      url: '/api/v1/ml-model/timezone',
      method: 'get'
    }, { returnDataOnly: true });
    return data.timezone || 'Asia/Shanghai'; // 默认值
  } catch (error) {
    // 如果获取失败（可能是 401 未授权或其他错误），返回默认值
    // 不显示错误信息，因为这是非关键功能
    return 'Asia/Shanghai';
  }
};

/**
 * 解析Excel列名
 * @param {File} file - Excel文件
 * @returns {Promise<Object>} Excel列名和推荐映射
 */
export const parseExcelColumns = async (file) => {
  try {
    // 确保CSRF令牌存在
    await refreshCsrfTokenBeforeRequest();

    const formData = new FormData();
    formData.append('file', file);

    // 获取CSRF令牌（如果存在）
    const csrfToken = sessionStorage.getItem('csrf_token');

    // 构建headers，确保包含CSRF令牌
    // 注意：不要手动设置 Content-Type，让 axios 自动处理 multipart/form-data 的 boundary
    const headers = {};
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }

    const response = await axios.post('/api/v1/ml-model/parse-excel', formData, {
      headers: Object.keys(headers).length > 0 ? headers : undefined
    });
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    handleError(error);
  }
};

/**
 * 保存用户映射规则
 * @param {Object} mapping - 用户选择的列名映射规则 {excel_column: db_field}
 * @returns {Promise<Object>} 保存结果
 */
export const saveMapping = async (mapping) => {
  // 确保CSRF令牌存在（如果不存在，会通过GET请求获取）
  await refreshCsrfTokenBeforeRequest();

  return request({
    url: '/api/v1/ml-model/save-mapping',
    method: 'post',
    data: mapping
  }, { returnDataOnly: true });
};

/**
 * 预览Excel数据（映射后的数据）
 * @param {File} file - Excel文件
 * @param {number} rows - 预览行数，默认10行
 * @returns {Promise<Object>} 预览数据
 */
export const previewExcelData = async (file, rows = 10) => {
  try {
    // 确保CSRF令牌存在
    await refreshCsrfTokenBeforeRequest();

    const formData = new FormData();
    formData.append('file', file);

    // 获取CSRF令牌（如果存在）
    const csrfToken = sessionStorage.getItem('csrf_token');

    // 构建headers，确保包含CSRF令牌
    // 注意：不要手动设置 Content-Type，让 axios 自动处理 multipart/form-data 的 boundary
    const headers = {};
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }

    const response = await axios.post(`/api/v1/ml-model/preview?rows=${rows}`, formData, {
      headers: Object.keys(headers).length > 0 ? headers : undefined
    });
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    handleError(error);
  }
};

/**
 * 导入训练数据
 * @param {File} file - Excel文件
 * @returns {Promise<Object>} 导入结果
 */
export const importTrainingData = async (file) => {
  // 重试函数，用于在CSRF token失败时自动重试
  const attemptImport = async (retryCount = 0) => {
    try {
      // 如果是重试，先强制获取新的CSRF令牌
      if (retryCount > 0) {
        // 清除旧的token
        sessionStorage.removeItem('csrf_token');
        // 强制获取新的CSRF令牌
        await ensureCsrfToken();
        // 等待一小段时间，确保令牌已更新
        await new Promise(resolve => setTimeout(resolve, 200));
      } else {
        // 首次尝试，确保CSRF令牌存在
        await ensureCsrfToken();
      }

      const formData = new FormData();
      formData.append('file', file);

      // 获取CSRF令牌（如果存在）
      const csrfToken = sessionStorage.getItem('csrf_token');

      if (!csrfToken) {
        throw new Error('CSRF令牌缺失，请刷新页面后重试');
      }

      // 构建headers，确保包含CSRF令牌
      // 注意：不要手动设置 Content-Type，让 axios 自动处理 multipart/form-data 的 boundary
      const headers = {
        'X-CSRF-Token': csrfToken
      };

      const response = await axios.post('/api/v1/ml-model/import', formData, {
        headers
      });
      return normalizeResponse(response, { returnDataOnly: true });
    } catch (error) {
      // 如果是CSRF相关错误（403），且还没有重试过，尝试重试一次
      if (error.response?.status === 403 && retryCount === 0) {
        const errorMsg = extractErrorMessage(error);
        if (errorMsg.includes('CSRF') || errorMsg.includes('csrf') || errorMsg.includes('令牌')) {
          logger.warn(`[importTrainingData] CSRF token验证失败，尝试重新获取token并重试`);
          // 重试一次
          return attemptImport(1);
        }
      }
      // 其他错误或重试后仍然失败，抛出错误
      throw error;
    }
  };

  try {
    return await attemptImport(0);
  } catch (error) {
    handleError(error);
  }
};