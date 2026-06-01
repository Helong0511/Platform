/**
 * 广告数据页 — 产品管理侧栏/弹窗状态与加载
 */
import { ref } from 'vue';
import { getProductById, getProductsWithData } from '../api/ad-data';

/**
 * @param {Object} [options]
 * @param {(id: string|number) => Promise<Object>} [options.getProductById]
 * @param {(clientId: string|number) => Promise<{data: Array}>} [options.fetchProductsForClient]
 */
export function useAdDataProductPanel(options = {}) {
  const fetchProductById = options.getProductById ?? getProductById;
  const fetchProductsForClient =
    options.fetchProductsForClient ??
    ((clientId) => getProductsWithData(clientId).then((r) => r.data || []));
  const productManagementVisible = ref(false);
  const selectedClientId = ref(null);
  const selectedClientName = ref('');
  const selectedClientProducts = ref([]);
  const loadingProducts = ref(false);
  const selectedProductId = ref('');
  const selectedProductName = ref('');

  const loadClientProducts = async (clientId, preferredProductId = null) => {
    loadingProducts.value = true;
    try {
      selectedClientProducts.value = [];
      if (preferredProductId) {
        try {
          const product = await fetchProductById(preferredProductId);
          if (product) {
            selectedClientProducts.value = [product];
            return;
          }
        } catch {
          /* 回退到列表接口 */
        }
      }
      const list = await fetchProductsForClient(clientId);
      if (preferredProductId) {
        selectedClientProducts.value = list.filter(
          (p) => String(p.id) === String(preferredProductId)
        );
      } else {
        selectedClientProducts.value = list;
      }
    } finally {
      loadingProducts.value = false;
    }
  };

  const openProductPanel = (row, defaults = {}) => {
    selectedClientId.value =
      row.client_id ?? row.user_id ?? defaults.defaultClientId ?? null;
    selectedClientName.value =
      row.user_name || row.client_name || defaults.defaultClientName || '';
    selectedProductId.value = row.product_id ? String(row.product_id) : '';
    selectedProductName.value = row.product_name || '';
    productManagementVisible.value = true;
    loadClientProducts(selectedClientId.value, row.product_id);
  };

  const resetProductPanelSelection = () => {
    selectedProductId.value = '';
    selectedProductName.value = '';
  };

  return {
    productManagementVisible,
    selectedClientId,
    selectedClientName,
    selectedClientProducts,
    loadingProducts,
    selectedProductId,
    selectedProductName,
    loadClientProducts,
    openProductPanel,
    resetProductPanelSelection
  };
}
