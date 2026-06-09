/**
 * Cap 限额管理 API：上下游 Offer 流量上限配置
 * @file api/cap.js
 */
import { createCrudApi } from '@/utils/crudApi';

/**
 * Cap 限额 CRUD 接口集合
 * @property {Function} getCaps - 分页获取限额配置列表
 * @property {Function} getCap - 按 ID 获取单条限额配置
 * @property {Function} createCap - 新建限额规则
 * @property {Function} updateCap - 更新限额规则
 * @property {Function} deleteCap - 删除限额规则
 */
export const {
  getCaps,
  getCap,
  createCap,
  updateCap,
  deleteCap
} = createCrudApi('/api/v1/caps', { csrfOnMutate: true });

