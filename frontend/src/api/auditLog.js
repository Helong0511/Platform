import axios from 'axios';
import { normalizePaginatedResponse, normalizeResponse, extractErrorMessage, isErrorHandled } from '../utils/api';
import { ElMessage } from 'element-plus';

/**
 * 获取操作日志列表
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页条数
 * @param {number} [params.user_id] - 用户ID筛选
 * @param {string} [params.username] - 用户名筛选
 * @param {string} [params.action_type] - 操作类型筛选
 * @param {string} [params.resource_type] - 资源类型筛选
 * @param {string} [params.ip_address] - IP地址筛选
 * @param {boolean} [params.success] - 是否成功筛选
 * @param {string} [params.start_date] - 开始时间
 * @param {string} [params.end_date] - 结束时间
 * @returns {Promise<Object>} 日志列表数据
 */
export const getAuditLogs = async (params) => {
  try {
    const response = await axios.get('/api/v1/audit-logs/', { params });
    return normalizePaginatedResponse(response);
  } catch (error) {
    // 如果错误已被拦截器处理（如429限流），不再重复显示
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

/**
 * 获取操作日志详情
 * @param {number} logId - 日志ID
 * @returns {Promise<Object>} 日志详情
 */
export const getAuditLog = async (logId) => {
  try {
    const response = await axios.get(`/api/v1/audit-logs/${logId}`);
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    // 如果错误已被拦截器处理（如429限流），不再重复显示
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

/**
 * 获取日志统计摘要
 * @param {Object} params - 查询参数
 * @param {string} [params.start_date] - 开始时间
 * @param {string} [params.end_date] - 结束时间
 * @returns {Promise<Object>} 统计信息
 */
export const getAuditLogStats = async (params = {}) => {
  try {
    const response = await axios.get('/api/v1/audit-logs/stats/summary', { params });
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    // 如果错误已被拦截器处理（如429限流），不再重复显示
    if (isErrorHandled(error)) {
      throw error;
    }
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
    throw error;
  }
};

