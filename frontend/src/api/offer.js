/**
 * Offer 管理 API
 * 使用CRUD API生成器，减少重复代码
 */
import { createCrudApi } from '@/utils/crudApi';
import { request } from '@/utils/api';

// 使用CRUD生成器自动生成标准CRUD方法
export const {
  getOffers,
  getOffer,
  createOffer,
  updateOffer,
  deleteOffer,
  checkOfferShortLink
} = createCrudApi('/api/v1/offers', {
  customMethods: {
    /**
     * 检查Offer的短链接是否存在
     */
    checkOfferShortLink: (id) => {
      return request({
        url: `/api/v1/offers/${id}/check-short-link`,
        method: 'get'
      }, { returnDataOnly: true });
    }
  }
});

/**
 * Offer 统计（点击、转化、收入、趋势图）
 * @param {number} offerId
 * @param {'day'|'week'|'month'} period
 */
export const getOfferStats = (offerId, period = 'week') => {
  return request({
    url: `/api/v1/offers/${offerId}/stats`,
    method: 'get',
    params: { period }
  }, { returnDataOnly: true });
};

