/**
 * Offer 管理 API
 */
import { request } from '@/utils/api'

/**
 * 获取Offer列表
 */
export function getOffers(params) {
  return request({
    url: '/api/v1/offers/',
    method: 'get',
    params
  })
}

/**
 * 获取Offer详情
 */
export function getOffer(id) {
  return request({
    url: `/api/v1/offers/${id}`,
    method: 'get'
  })
}

/**
 * 创建Offer
 */
export function createOffer(data) {
  return request({
    url: '/api/v1/offers/',
    method: 'post',
    data
  })
}

/**
 * 更新Offer
 */
export function updateOffer(id, data) {
  return request({
    url: `/api/v1/offers/${id}`,
    method: 'put',
    data
  })
}

/**
 * 删除Offer
 */
export function deleteOffer(id) {
  return request({
    url: `/api/v1/offers/${id}`,
    method: 'delete'
  })
}

