/**
 * 转化总览统计 API
 */
import { request } from '../utils/api';

const STATS_TIMEOUT = 30000;

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
