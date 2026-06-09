/**
 * 广告数据页筛选下拉选项加载
 * @file api/helpers/adDataSelectOptions.js
 *
 * 将客户与产品数据转换为 el-select 所需的 { value, label } 格式。
 */
import { request, handleError } from '../../utils/api';

/**
 * 获取客户下拉选项（label 含客户 ID 与关联用户名）
 * @returns {Promise<Array<{value: number, label: string}>>}
 */
export async function fetchClientsAsUserSelectOptions() {
  try {
    const usersData = await request(
      {
        url: '/api/v1/users/',
        method: 'get',
        params: { page_size: 100 }
      },
      { paginated: true }
    );
    const users = usersData.data || [];
    const userMap = users.reduce((acc, user) => {
      if (user?.id) {
        acc[user.id] = user.full_name || user.username || '未知用户';
      }
      return acc;
    }, {});

    const clientsData = await request(
      {
        url: '/api/v1/clients/',
        method: 'get',
        params: { page_size: 100 }
      },
      { paginated: true }
    );
    const clients = clientsData.data || [];

    return clients
      .map((item) => {
        if (!item?.id) return null;
        return {
          value: item.id,
          label: `${item.id} - ${userMap[item.user_id] || '未知用户'}`
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
    const params = { page_size: 100 };
    if (clientId) params.client_id = clientId;

    const productsData = await request(
      { url: '/api/v1/products/', method: 'get', params },
      { paginated: true }
    );
    const products = productsData.data || [];

    return products
      .map((item) => {
        if (!item?.id) return null;
        return {
          label: `${item.id} - ${item.name || '未知产品'}`,
          value: item.id
        };
      })
      .filter(Boolean);
  } catch {
    return [];
  }
}
