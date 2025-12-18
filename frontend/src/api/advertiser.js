/**
 * 广告主管理 API
 */
import { request } from '@/utils/api'

/**
 * 获取广告主列表
 */
export function getAdvertisers(params) {
  return request({
    url: '/api/v1/advertisers/',
    method: 'get',
    params
  })
}

/**
 * 获取广告主详情
 */
export function getAdvertiser(id) {
  return request({
    url: `/api/v1/advertisers/${id}`,
    method: 'get'
  })
}

/**
 * 创建广告主
 */
export function createAdvertiser(data) {
  return request({
    url: '/api/v1/advertisers/',
    method: 'post',
    data
  })
}

/**
 * 更新广告主
 */
export function updateAdvertiser(id, data) {
  return request({
    url: `/api/v1/advertisers/${id}`,
    method: 'put',
    data
  })
}

/**
 * 删除广告主
 */
export function deleteAdvertiser(id) {
  return request({
    url: `/api/v1/advertisers/${id}`,
    method: 'delete'
  })
}

