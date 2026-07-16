/**
 * 广告数据页筛选下拉选项加载
 * @file api/helpers/adDataSelectOptions.js
 *
 * 将客户与产品数据转换为 el-select 所需的 { value, label } 格式。
 */
import { request, handleError } from '../../utils/api';

/**
 * 分页拉取全部列表（后端 MAX_PAGE_SIZE=100）。
 * @param {string} url
 * @param {Object} [baseParams]
 * @returns {Promise<Array>}
 */
async function fetchAllPages(url, baseParams = {}) {
  const pageSize = 100;
  const maxPages = 50;
  let page = 1;
  let total = Infinity;
  const all = [];

  while (all.length < total && page <= maxPages) {
    const data = await request(
      {
        url,
        method: 'get',
        params: { ...baseParams, page, page_size: pageSize },
      },
      { paginated: true }
    );
    const items = data.data || [];
    total = data.total ?? data.count ?? all.length + items.length;
    all.push(...items);
    if (items.length === 0 || items.length < pageSize) {
      break;
    }
    page += 1;
  }
  return all;
}

/**
 * 获取客户下拉选项（label 含客户 ID 与关联用户名）
 * @returns {Promise<Array<{value: number, label: string}>>}
 */
export async function fetchClientsAsUserSelectOptions() {
  try {
    const users = await fetchAllPages('/api/v1/users/');
    const userMap = users.reduce((acc, user) => {
      if (user?.id) {
        acc[user.id] = user.full_name || user.username || '未知用户';
      }
      return acc;
    }, {});

    const clients = await fetchAllPages('/api/v1/clients/');

    return clients
      .map((item) => {
        if (!item?.id) return null;
        return {
          value: item.id,
          label: `${item.id} - ${userMap[item.user_id] || item.company_name || '未知用户'}`,
        };
      })
      .filter(Boolean);
  } catch (error) {
    handleError(error, { showMessage: true });
    return [];
  }
}

/**
 * 获取产品下拉选项，可按客户 ID 过滤
 * @param {number|null} [clientId] - 客户 ID，为空则返回全部产品
 * @returns {Promise<Array<{value: number, label: string}>>}
 */
export async function fetchProductsAsSelectOptions(clientId = null) {
  try {
    const baseParams = {};
    if (clientId) baseParams.client_id = clientId;

    const products = await fetchAllPages('/api/v1/products/', baseParams);

    return products
      .map((item) => {
        if (!item?.id) return null;
        return {
          label: `${item.id} - ${item.name || '未知产品'}`,
          value: item.id,
        };
      })
      .filter(Boolean);
  } catch {
    return [];
  }
}
