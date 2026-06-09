/**
 * 转化总览 API：按维度汇总转化数据
 * @file api/conversion-summary.js
 */
import { request } from '../utils/api';

const STATS_TIMEOUT = 30000;

/**
 * 按筛选条件获取转化总览汇总数据
 * @param {Object} params - 筛选参数（日期、平台、产品等）
 * @returns {Promise<Object>} 汇总统计结果
 */
export function getConversionSummary(params) {
  return request(
    {
      url: '/api/v1/conversion-summary/',
      method: 'get',
      params
    },
    { returnDataOnly: true, timeout: STATS_TIMEOUT }
  );
}

/**
 * 按 Offer 维度获取转化汇总
 * @param {Object} params - 筛选参数
 * @returns {Promise<Object>} 按 Offer 分组的汇总数据
 */
export function getSummaryByOffer(params) {
  return request(
    {
      url: '/api/v1/conversion-summary/by-offer',
      method: 'get',
      params
    },
    { returnDataOnly: true, timeout: STATS_TIMEOUT }
  );
}
