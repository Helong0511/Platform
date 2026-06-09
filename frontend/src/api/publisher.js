/**
 * 渠道（下游/商户）管理 API
 * @file api/publisher.js
 *
 * 通过 createCrudApi 生成标准 CRUD 方法，写操作自动附带 CSRF 令牌。
 */
import { createCrudApi } from '@/utils/crudApi';

/**
 * 渠道（下游/商户）CRUD 接口集合
 * @property {Function} getPublishers - 分页获取渠道列表
 * @property {Function} getPublisher - 按 ID 获取单条渠道
 * @property {Function} createPublisher - 新建渠道
 * @property {Function} updatePublisher - 更新渠道信息
 * @property {Function} deletePublisher - 删除渠道
 */
export const {
  getPublishers,
  getPublisher,
  createPublisher,
  updatePublisher,
  deletePublisher
} = createCrudApi('/api/v1/publishers', { csrfOnMutate: true });

