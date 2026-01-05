import { request } from '@/utils/api'

/**
 * 获取扣减配置列表
 */
export function getDeductionConfigs(params) {
  return request({
    url: '/api/v1/conversion-deductions',
    method: 'get',
    params
  })
}

/**
 * 创建扣减配置
 */
export function createDeductionConfig(data) {
  return request({
    url: '/api/v1/conversion-deductions',
    method: 'post',
    data
  })
}

/**
 * 更新扣减配置
 */
export function updateDeductionConfig(id, data) {
  return request({
    url: `/api/v1/conversion-deductions/${id}`,
    method: 'put',
    data
  })
}

/**
 * 删除扣减配置
 */
export function deleteDeductionConfig(id) {
  return request({
    url: `/api/v1/conversion-deductions/${id}`,
    method: 'delete'
  })
}

/**
 * 更新扣减配置状态
 */
export function updateDeductionConfigStatus(id, isActive) {
  return request({
    url: `/api/v1/conversion-deductions/${id}/status`,
    method: 'patch',
    params: { is_active: isActive }
  })
}

/**
 * 获取扣减统计
 */
export function getDeductionStats(params) {
  return request({
    url: '/api/v1/conversion-deductions/stats',
    method: 'get',
    params
  })
}

/**
 * 获取扣减日志
 */
export function getDeductionLogs(params) {
  return request({
    url: '/api/v1/conversion-deductions/logs',
    method: 'get',
    params
  })
}

