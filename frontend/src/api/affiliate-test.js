/**
 * 下游测试 API
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

export { getAffiliateTests, getAffiliateTest, createAffiliateTest };
