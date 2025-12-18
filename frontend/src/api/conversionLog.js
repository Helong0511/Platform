/**
 * 转化日志 API
 */
import { request } from '@/utils/api'

/**
 * 获取转化日志列表
 */
export function getConversionLogs(params) {
  return request({
    url: '/api/v1/conversion-logs/',
    method: 'get',
    params
  })
}

/**
 * 更新转化状态
 */
export function updateConversionStatus(conversionId, status) {
  return request({
    url: `/api/v1/conversion-logs/${conversionId}/status`,
    method: 'put',
    params: { status }
  })
}

