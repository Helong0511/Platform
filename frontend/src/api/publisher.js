/**
 * 渠道管理 API
 * 使用CRUD API生成器，减少重复代码
 */
import { createCrudApi } from '@/utils/crudApi';

// 使用CRUD生成器自动生成所有标准CRUD方法
export const {
  getPublishers,
  getPublisher,
  createPublisher,
  updatePublisher,
  deletePublisher
} = createCrudApi('/api/v1/publishers');

