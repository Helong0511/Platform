/**
 * Offer 管理 API
 * @file api/offer.js
 *
 * 标准 CRUD 及短链接检查等扩展接口，写操作附带 CSRF 令牌。
 */
import { createCrudApi } from '@/utils/crudApi';
import { request } from '@/utils/api';

/**
 * Offer CRUD 接口集合
 * @property {Function} getOffers - 分页获取 Offer 列表
 * @property {Function} getOffer - 按 ID 获取单条 Offer
 * @property {Function} createOffer - 新建 Offer
 * @property {Function} updateOffer - 更新 Offer
 * @property {Function} deleteOffer - 删除 Offer
 * @property {Function} checkOfferShortLink - 检查关联短链接是否存在
 */
export const {
  getOffers,
  getOffer,
  createOffer,
  updateOffer,
  deleteOffer,
  checkOfferShortLink
} = createCrudApi('/api/v1/offers', {
  csrfOnMutate: true,
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

