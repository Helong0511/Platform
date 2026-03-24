/**
 * 转化总览统计 API
 */
import { request } from '@/utils/api'

/**
 * 获取转化总览统计
 */
export function getConversionSummary(params) {
  return request({
    url: '/api/v1/conversion-summary/',
    method: 'get',
    params
  })
}

/**
 * 按Offer统计
 */
export function getSummaryByOffer(params) {
  return request({
    url: '/api/v1/conversion-summary/by-offer',
    method: 'get',
    params
  })
}

