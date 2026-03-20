/**
 * 第三方上报日志 API
 * 用于查询和管理第三方广告上报日志
 */
import { request } from '../utils/api';

/**
 * 获取第三方上报日志列表
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页条数
 * @param {string} [params.source] - 来源筛选
 * @param {string} [params.adsid] - 广告ID筛选
 * @param {string} [params.event] - 事件类型筛选
 * @param {string} [params.status] - 状态筛选
 * @param {string} [params.start_date] - 开始时间
 * @param {string} [params.end_date] - 结束时间
 * @returns {Promise<Object>} 日志列表数据
 */
export const getThirdPartyReports = async (params) => {
  return request({
    url: '/api/v1/third-party-reports/',
    method: 'get',
    params
  }, { paginated: true });
};

/**
 * 获取第三方上报日志详情
 * @param {number} logId - 日志ID
 * @returns {Promise<Object>} 日志详情
 */
export const getThirdPartyReport = async (logId) => {
  return request({
    url: `/api/v1/third-party-reports/${logId}`,
    method: 'get'
  }, { returnDataOnly: true });
};

/**
 * 获取第三方上报统计摘要
 * @param {Object} params - 查询参数
 * @param {string} [params.start_date] - 开始时间
 * @param {string} [params.end_date] - 结束时间
 * @returns {Promise<Object>} 统计信息
 */
export const getThirdPartyReportStats = async (params = {}) => {
  return request({
    url: '/api/v1/third-party-reports/stats/summary',
    method: 'get',
    params
  }, { returnDataOnly: true });
};

/**
 * 更新第三方上报日志参数
 * @param {number} logId - 日志ID
 * @param {Object} params - 更新参数
 * @param {string} [params.adsid] - 广告ID
 * @param {string} [params.event] - 事件类型
 * @param {string} [params.email] - 邮箱
 * @param {string} [params.ip] - IP地址
 * @param {string} [params.phone] - 手机号
 * @param {string} [params.ua] - 用户代理
 * @returns {Promise<Object>} 更新结果
 */
export const updateThirdPartyReport = async (logId, params) => {
  return request({
    url: `/api/v1/third-party-reports/${logId}`,
    method: 'put',
    data: params
  }, { returnDataOnly: true });
};

/**
 * 重新上报第三方上报日志
 * @param {number} logId - 日志ID
 * @returns {Promise<Object>} 重新上报结果
 */
export const retryThirdPartyReport = async (logId) => {
  return request({
    url: `/api/v1/third-party-reports/${logId}/retry`,
    method: 'post'
  }, { returnDataOnly: true });
};
