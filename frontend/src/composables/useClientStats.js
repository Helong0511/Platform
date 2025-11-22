import { ref } from 'vue';

/**
 * 客户统计信息 Composable
 * 处理统计数据的计算和更新
 */
export function useClientStats() {
  const stats = ref({
    total: 0,
    active: 0,
    inactive: 0,
    products: 0
  });

  /**
   * 更新统计信息
   * @param {Array} clientList - 客户列表
   * @param {number} total - 总记录数
   */
  const updateStats = (clientList, total) => {
    if (!clientList || clientList.length === 0) {
      stats.value = {
        total: total || 0,
        active: 0,
        inactive: 0,
        products: 0
      };
      return;
    }

    stats.value = {
      total: total || clientList.length,
      active: clientList.filter(c => c.is_active).length,
      inactive: clientList.filter(c => !c.is_active).length,
      products: clientList.reduce((sum, c) => sum + (c.product_count || 0), 0)
    };
  };

  return {
    stats,
    updateStats
  };
}

