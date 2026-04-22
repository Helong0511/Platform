/**
 * 短链接访问记录 API
 */
import { request } from '@/utils/api'

/**
 * 获取短链接访问记录列表
 */
export function getClicks(params) {
  return request({
    url: '/api/v1/clicks/',
    method: 'get',
    params
  }, {
    paginated: true,
    timeout: 45000
  })
}

/**
 * 获取短链接访问记录详情
 */
export function getClickDetail(clickRecordId) {
  return request({
    url: `/api/v1/clicks/${clickRecordId}`,
    method: 'get'
  }, { returnDataOnly: true })
}
