import axios from 'axios';
import { normalizePaginatedResponse, normalizeResponse, extractErrorMessage, isErrorHandled } from '../utils/api';
import { ElMessage } from 'element-plus';

/**
 * 获取 Postback 转化记录列表
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页条数
 * @param {string} [params.platform] - 平台名称筛选
 * @param {number} [params.product_id] - 产品ID筛选
 * @param {number} [params.client_id] - 客户ID筛选
 * @param {string} [params.event_name] - 事件名称筛选
 * @param {string} [params.start_date] - 开始日期（YYYY-MM-DD）
 * @param {string} [params.end_date] - 结束日期（YYYY-MM-DD）
 * @returns {Promise<Object>} 转化记录列表数据
 */
export const getPostbackConversions = async (params) => {
  try {
    const response = await axios.get('/api/v1/postback/conversions', { params });
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

/**
 * 获取 Postback 统计信息
 * @param {Object} params - 查询参数
 * @param {string} [params.platform] - 平台名称筛选
 * @param {string} [params.start_date] - 开始日期（YYYY-MM-DD）
 * @param {string} [params.end_date] - 结束日期（YYYY-MM-DD）
 * @returns {Promise<Array>} 统计信息列表
 */
export const getPostbackStats = async (params = {}) => {
  try {
    const response = await axios.get('/api/v1/postback/stats', { params });
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

