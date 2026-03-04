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

// 注意：getRecentAdData 接口后端已实现，但前端暂未使用（保留接口供未来使用）
// 如需使用，可添加以下代码：
// export const getRecentAdData = async () => {
//   return request({
//     url: '/api/v1/dashboard/recent-ads',
//     method: 'get'
//   }, { returnDataOnly: true });
// };

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
