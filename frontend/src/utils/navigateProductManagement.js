/**
 * 跳转到独立「产品管理」页（管理员）。
 * @file utils/navigateProductManagement.js
 */
import { ElMessage } from 'element-plus';

/**
 * @param {import('vue-router').Router} router
 * @param {{ isAdmin: boolean, clientId?: string|number|null, productId?: string|number|null, productName?: string|null }} opts
 */
export function navigateToProductManagement(router, opts = {}) {
  const { isAdmin, clientId, productId, productName } = opts;
  if (!isAdmin) {
    ElMessage.info('产品管理仅管理员可用，请在「用户管理」中查看本账号产品');
    return false;
  }
  const query = {};
  if (clientId != null && String(clientId).trim() !== '') {
    query.client_id = String(clientId);
  }
  if (productId != null && String(productId).trim() !== '') {
    query.product_id = String(productId);
  }
  if (productName && String(productName).trim()) {
    query.name = String(productName).trim();
  }
  router.push({ name: 'ProductManagement', query });
  return true;
}
