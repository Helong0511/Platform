import axios from 'axios';
import { normalizeResponse, extractErrorMessage, isErrorHandled } from '../utils/api';
import { ElMessage } from 'element-plus';
import { getWarningMessage } from '../utils/messages';

/**
 * 验证Excel列名映射
 * @param {File} file - Excel文件
 * @returns {Promise<Object>} 验证结果
 */
export const validateExcelData = async (file) => {
  try {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await axios.post('/api/v1/ml-model/validate', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
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

/**
 * 获取映射规则状态
 * @returns {Promise<Object>} 状态信息
 */
export const getModelStatus = async () => {
  try {
    const response = await axios.get('/api/v1/ml-model/status');
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

/**
 * 获取应用时区配置
 * @returns {Promise<string>} 时区字符串
 */
export const getTimezone = async () => {
  try {
    const response = await axios.get('/api/v1/ml-model/timezone');
    const data = normalizeResponse(response, { returnDataOnly: true });
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
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await axios.post('/api/v1/ml-model/parse-excel', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
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

/**
 * 保存用户映射规则
 * @param {Object} mapping - 用户选择的列名映射规则 {excel_column: db_field}
 * @returns {Promise<Object>} 保存结果
 */
export const saveMapping = async (mapping) => {
  try {
    // 确保请求包含认证头
    const token = sessionStorage.getItem('token');
    if (!token) {
      ElMessage.error(getWarningMessage('UNAUTHORIZED') || '请先登录');
      throw new Error('未登录');
    }
    
    const response = await axios.post('/api/v1/ml-model/save-mapping', mapping, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    });
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    // 如果错误已被拦截器处理（如401、429），不再重复显示
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

/**
 * 预览Excel数据（映射后的数据）
 * @param {File} file - Excel文件
 * @param {number} rows - 预览行数，默认10行
 * @returns {Promise<Object>} 预览数据
 */
export const previewExcelData = async (file, rows = 10) => {
  try {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await axios.post(`/api/v1/ml-model/preview?rows=${rows}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
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

/**
 * 导入训练数据
 * @param {File} file - Excel文件
 * @returns {Promise<Object>} 导入结果
 */
export const importTrainingData = async (file) => {
  try {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await axios.post('/api/v1/ml-model/import', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
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