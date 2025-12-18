/**
 * 扣量管理 API
 */
import { request } from '@/utils/api'

/**
 * 获取扣量配置列表
 */
export function getDiscounts(params) {
  return request({
    url: '/api/v1/discounts/',
    method: 'get',
    params
  })
}

/**
 * 获取扣量配置详情
 */
export function getDiscount(id) {
  return request({
    url: `/api/v1/discounts/${id}`,
    method: 'get'
  })
}

/**
 * 创建扣量配置
 */
export function createDiscount(data) {
  return request({
    url: '/api/v1/discounts/',
    method: 'post',
    data
  })
}

/**
 * 更新扣量配置
 */
export function updateDiscount(id, data) {
  return request({
    url: `/api/v1/discounts/${id}`,
    method: 'put',
    data
  })
}

/**
 * 删除扣量配置
 */
export function deleteDiscount(id) {
  return request({
    url: `/api/v1/discounts/${id}`,
    method: 'delete'
  })
}

