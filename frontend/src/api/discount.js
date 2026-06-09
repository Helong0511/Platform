/**
 * 扣量（Discount）配置管理 API
 * @file api/discount.js
 *
 * 通过 createCrudApi 生成标准 CRUD 方法，写操作自动附带 CSRF 令牌。
 */
import { createCrudApi } from '@/utils/crudApi';

/**
 * 扣量（Discount）配置 CRUD 接口集合
 * @property {Function} getDiscounts - 分页获取扣量规则列表
 * @property {Function} getDiscount - 按 ID 获取单条扣量规则
 * @property {Function} createDiscount - 新建扣量规则
 * @property {Function} updateDiscount - 更新扣量规则
 * @property {Function} deleteDiscount - 删除扣量规则
 */
export const {
  getDiscounts,
  getDiscount,
  createDiscount,
  updateDiscount,
  deleteDiscount
} = createCrudApi('/api/v1/discounts', { csrfOnMutate: true });

