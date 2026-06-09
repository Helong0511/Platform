/**
 * 广告主（上游）管理 API
 * @file api/advertiser.js
 *
 * 通过 createCrudApi 生成标准 CRUD 方法，写操作自动附带 CSRF 令牌。
 */
import { createCrudApi } from '@/utils/crudApi';

/**
 * 广告主 CRUD 接口集合
 * @property {Function} getAdvertisers - 分页获取广告主列表
 * @property {Function} getAdvertiser - 按 ID 获取单条广告主
 * @property {Function} createAdvertiser - 新建广告主
 * @property {Function} updateAdvertiser - 更新广告主信息
 * @property {Function} deleteAdvertiser - 删除广告主
 */
export const {
  getAdvertisers,
  getAdvertiser,
  createAdvertiser,
  updateAdvertiser,
  deleteAdvertiser
} = createCrudApi('/api/v1/advertisers', { csrfOnMutate: true });

