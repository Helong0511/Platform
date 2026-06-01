/**
 * 广告数据页筛选下拉：客户（含用户名）、产品
 */
import { request, handleError } from '../../utils/api';

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
