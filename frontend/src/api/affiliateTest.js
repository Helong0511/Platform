/**
 * 下游测试 API
 */
import { request } from '@/utils/api'

/**
 * 获取下游测试记录列表
 */
export function getAffiliateTests(params) {
  return request({
    url: '/api/v1/affiliate-tests/',
    method: 'get',
    params
  })
}

/**
 * 获取下游测试记录详情
 */
export function getAffiliateTest(id) {
  return request({
    url: `/api/v1/affiliate-tests/${id}`,
    method: 'get'
  })
}

/**
 * 创建下游测试记录并发送Postback
 */
export function createAffiliateTest(data) {
  return request({
    url: '/api/v1/affiliate-tests/',
    method: 'post',
    data
  })
}

