/**
 * 上游测试 API
 */
import { request } from '@/utils/api'

/**
 * 获取上游测试记录列表
 */
export function getAdvertiserTests(params) {
  return request({
    url: '/api/v1/advertiser-tests/',
    method: 'get',
    params
  })
}

/**
 * 获取上游测试记录详情
 */
export function getAdvertiserTest(id) {
  return request({
    url: `/api/v1/advertiser-tests/${id}`,
    method: 'get'
  })
}

/**
 * 创建上游测试记录
 */
export function createAdvertiserTest(data) {
  return request({
    url: '/api/v1/advertiser-tests/',
    method: 'post',
    data
  })
}

