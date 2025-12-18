/**
 * 渠道管理 API
 */
import { request } from '@/utils/api'

/**
 * 获取渠道列表
 */
export function getPublishers(params) {
  return request({
    url: '/api/v1/publishers/',
    method: 'get',
    params
  })
}

/**
 * 获取渠道详情
 */
export function getPublisher(id) {
  return request({
    url: `/api/v1/publishers/${id}`,
    method: 'get'
  })
}

/**
 * 创建渠道
 */
export function createPublisher(data) {
  return request({
    url: '/api/v1/publishers/',
    method: 'post',
    data
  })
}

/**
 * 更新渠道
 */
export function updatePublisher(id, data) {
  return request({
    url: `/api/v1/publishers/${id}`,
    method: 'put',
    data
  })
}

/**
 * 删除渠道
 */
export function deletePublisher(id) {
  return request({
    url: `/api/v1/publishers/${id}`,
    method: 'delete'
  })
}

