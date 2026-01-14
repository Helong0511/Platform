/**
 * 仪表盘 API
 * 已统一使用 request 函数，保持代码一致性
 */
import { request } from '../utils/api';

/**
 * 获取仪表盘统计数据
 * @param {string} period - 统计周期，默认为 'week'
 * @returns {Promise<Object>} 统计数据
 */
export const getDashboardStats = async (period = 'week') => {
  return request({
    url: '/api/v1/dashboard/stats',
    method: 'get',
    params: { period }
  }, { returnDataOnly: true });
};

// 注意：getRecentAdData 和 getTodayMetrics 已移除，因为后端API未实现

/**
 * 获取趋势数据
 * @param {string} period - 统计周期，默认为 'week'
 * @returns {Promise<Object>} 趋势数据
 */
export const getTrendData = async (period = 'week') => {
  return request({
    url: '/api/v1/dashboard/trends',
    method: 'get',
    params: { period }
  }, { returnDataOnly: true });
};
