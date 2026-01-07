import { request } from '@/utils/api'

/**
 * CPL扣减配置管理API
 * 
 * 后端路径: /api/v1/conversion-deductions
 */

/**
 * 获取扣减配置列表
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页条数
 * @param {string} params.level - 配置层级 (advertiser/offer/publisher)
 * @param {boolean} params.is_active - 是否激活
 * @param {string} params.keyword - 搜索关键词
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
 * @param {Object} data - 配置数据
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
 * @param {number} id - 配置ID
 * @param {Object} data - 更新数据
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
 * @param {number} id - 配置ID
 */
export function deleteDeductionConfig(id) {
  return request({
    url: `/api/v1/conversion-deductions/${id}`,
    method: 'delete'
  })
}

/**
 * 更新扣减配置状态
 * @param {number} id - 配置ID
 * @param {boolean} isActive - 是否激活
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
 * @param {Object} params - 查询参数
 * @param {string} params.start_date - 开始日期 (YYYY-MM-DD)
 * @param {string} params.end_date - 结束日期 (YYYY-MM-DD)
 * @param {string} params.group_by - 分组方式 (time/advertiser/offer/publisher)
 * @param {number} params.advertiser_id - 广告主ID
 * @param {number} params.offer_id - Offer ID
 * @param {number} params.publisher_id - 渠道ID
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
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页条数
 * @param {string} params.start_date - 开始日期 (YYYY-MM-DD)
 * @param {string} params.end_date - 结束日期 (YYYY-MM-DD)
 * @param {number} params.advertiser_id - 广告主ID
 * @param {number} params.offer_id - Offer ID
 * @param {number} params.publisher_id - 渠道ID
 * @param {number} params.conversion_id - 转化ID
 * @param {string} params.click_id - 点击ID
 */
export function getDeductionLogs(params) {
  return request({
    url: '/api/v1/conversion-deductions/logs',
    method: 'get',
    params
  })
}

/**
 * 批量更新扣减配置状态
 * @param {Object} data - 请求数据
 * @param {Array<number>} data.config_ids - 配置ID列表
 * @param {boolean} data.is_active - 是否激活
 */
export function batchUpdateDeductionConfigStatus(data) {
  return request({
    url: '/api/v1/conversion-deductions/batch/update-status',
    method: 'post',
    data
  })
}

/**
 * 批量删除扣减配置
 * @param {Object} data - 请求数据
 * @param {Array<number>} data.config_ids - 配置ID列表
 */
export function batchDeleteDeductionConfigs(data) {
  return request({
    url: '/api/v1/conversion-deductions/batch/delete',
    method: 'post',
    data
  })
}

