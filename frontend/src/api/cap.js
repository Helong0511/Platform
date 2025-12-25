/**
 * Cap 管理 API
 */
import { request } from '@/utils/api'

/**
 * 获取Cap配置列表
 */
export function getCaps(params) {
  return request({
    url: '/api/v1/caps/',
    method: 'get',
    params
  })
}

/**
 * 获取Cap配置详情
 */
export function getCap(id) {
  return request({
    url: `/api/v1/caps/${id}`,
    method: 'get'
  })
}

/**
 * 创建Cap配置
 */
export function createCap(data) {
  return request({
    url: '/api/v1/caps/',
    method: 'post',
    data
  })
}

/**
 * 更新Cap配置
 */
export function updateCap(id, data) {
  return request({
    url: `/api/v1/caps/${id}`,
    method: 'put',
    data
  })
}

/**
 * 删除Cap配置
 */
export function deleteCap(id) {
  return request({
    url: `/api/v1/caps/${id}`,
    method: 'delete'
  })
}

/**
 * 检查Cap一致性
 */
export function checkConsistency() {
  return request({
    url: '/api/v1/caps/check-consistency',
    method: 'post'
  })
}

