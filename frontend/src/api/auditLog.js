/**
 * 操作日志 API
 * 已统一使用 request 函数，保持代码一致性
 */
import { request } from '../utils/api';

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
  return request({
    url: '/api/v1/audit-logs/',
    method: 'get',
    params
  }, { paginated: true });
};

/**
 * 获取操作日志详情
 * @param {number} logId - 日志ID
 * @returns {Promise<Object>} 日志详情
 */
export const getAuditLog = async (logId) => {
  return request({
    url: `/api/v1/audit-logs/${logId}`,
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 获取日志统计摘要
 * @param {Object} params - 查询参数
 * @param {string} [params.start_date] - 开始时间
 * @param {string} [params.end_date] - 结束时间
 * @returns {Promise<Object>} 统计信息
 */
export const getAuditLogStats = async (params = {}) => {
  return request({
    url: '/api/v1/audit-logs/stats/summary',
    method: 'get',
    params
  }, { returnDataOnly: true });
};

