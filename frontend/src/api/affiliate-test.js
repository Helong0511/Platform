/**
 * 下游联调测试 API：模拟转化回传与结果查询
 * @file api/affiliate-test.js
 */
import { createCrudApi } from '@/utils/crudApi';

const { getAffiliateTests, getAffiliateTest, createAffiliateTest } = createCrudApi(
  '/api/v1/affiliate-tests',
  {
    csrfOnMutate: true,
    include: ['list', 'get', 'create'],
    methodNames: {
      list: 'getAffiliateTests',
      get: 'getAffiliateTest',
      create: 'createAffiliateTest'
    }
  }
);

/**
 * 下游联调测试接口
 * @property {Function} getAffiliateTests - 分页获取联调记录
 * @property {Function} getAffiliateTest - 获取单条联调详情
 * @property {Function} createAffiliateTest - 发起新的联调测试
 */
export { getAffiliateTests, getAffiliateTest, createAffiliateTest };
