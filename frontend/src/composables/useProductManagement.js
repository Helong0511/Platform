/**
 * 独立「产品管理」页：全量列表、筛选分页、增删改与表单上下文客户。
 * @file composables/useProductManagement.js
 */
import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { markRaw } from 'vue';
import { Warning } from '@element-plus/icons-vue';
import {
  createProduct,
  deleteProduct,
  getProductList,
  updateProduct,
} from '../api/product';
import { fetchClientsAsUserSelectOptions } from '../api/helpers/adDataSelectOptions';
import { extractErrorMessage, isErrorHandled } from '../utils/api';
import { ensureCsrfToken } from '../utils/csrfMutate';
import { getCsrfToken } from '../utils/csrfToken';
import { logger } from '../utils/logger';
import { useProductForm } from './useProductForm';

/**
 * @returns {Object} 产品管理页状态与操作
 */
export function useProductManagement() {
  const route = useRoute();
  const router = useRouter();

  const loading = ref(false);
  const products = ref([]);
  const clientOptions = ref([]);
  const clientPickerVisible = ref(false);
  const pendingClientId = ref(null);

  const searchForm = reactive({
    name: '',
    clientId: null,
    isActive: null,
    productId: null,
  });

  const pagination = reactive({
    page: 1,
    pageSize: 20,
    total: 0,
  });

  /** useProductForm 所需的当前操作客户上下文 */
  const formScope = reactive({
    clientId: null,
    clientName: '',
  });

  const clientLabelMap = computed(() => {
    const map = {};
    for (const opt of clientOptions.value) {
      if (opt?.value != null) {
        map[opt.value] = opt.label;
      }
    }
    return map;
  });

  const syncFormScopeFromFilter = () => {
    if (searchForm.clientId == null) {
      return;
    }
    formScope.clientId = searchForm.clientId;
    formScope.clientName =
      clientLabelMap.value[searchForm.clientId] || `客户#${searchForm.clientId}`;
  };

  /**
   * 将路由 query 写入筛选项。
   * @param {Record<string, string|string[]>|null} [queryOverride] 路由更新守卫中传入 to.query
   */
  const applyRouteQuery = (queryOverride = null) => {
    const q = queryOverride || route.query || {};
    // 同页跳入时先清空，避免残留旧筛选
    searchForm.name = '';
    searchForm.clientId = null;
    searchForm.isActive = null;
    searchForm.productId = null;

    if (q.client_id != null && String(q.client_id).trim() !== '') {
      const cid = Number(q.client_id);
      searchForm.clientId = Number.isFinite(cid) ? cid : null;
    }
    if (q.name != null && String(q.name).trim() !== '') {
      searchForm.name = String(q.name).trim();
    }
    if (q.product_id != null && String(q.product_id).trim() !== '') {
      const pid = Number(q.product_id);
      searchForm.productId = Number.isFinite(pid) ? pid : null;
    }
    if (q.is_active === 'true' || q.is_active === '1') {
      searchForm.isActive = true;
    } else if (q.is_active === 'false' || q.is_active === '0') {
      searchForm.isActive = false;
    }
    syncFormScopeFromFilter();
  };

  const syncQueryToRoute = () => {
    const query = {};
    if (searchForm.clientId != null) query.client_id = String(searchForm.clientId);
    if (searchForm.name?.trim()) query.name = searchForm.name.trim();
    if (searchForm.productId != null) query.product_id = String(searchForm.productId);
    if (searchForm.isActive === true) query.is_active = 'true';
    if (searchForm.isActive === false) query.is_active = 'false';
    router.replace({ query }).catch(() => {});
  };

  const loadClientOptions = async () => {
    clientOptions.value = await fetchClientsAsUserSelectOptions();
    syncFormScopeFromFilter();
  };

  const fetchProducts = async () => {
    loading.value = true;
    try {
      const params = {
        page: pagination.page,
        page_size: pagination.pageSize,
      };
      if (searchForm.clientId != null) params.client_id = searchForm.clientId;
      if (searchForm.name?.trim()) params.name = searchForm.name.trim();
      if (searchForm.productId != null) params.product_id = searchForm.productId;
      if (searchForm.isActive !== null && searchForm.isActive !== undefined) {
        params.is_active = searchForm.isActive;
      }
      const response = await getProductList(params);
      products.value = response.data || [];
      pagination.total = response.total ?? 0;
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error) || '加载产品列表失败');
      }
      products.value = [];
      pagination.total = 0;
    } finally {
      loading.value = false;
    }
  };

  const handleSearch = () => {
    pagination.page = 1;
    syncFormScopeFromFilter();
    syncQueryToRoute();
    fetchProducts();
  };

  const handleReset = () => {
    searchForm.name = '';
    searchForm.clientId = null;
    searchForm.isActive = null;
    searchForm.productId = null;
    formScope.clientId = null;
    formScope.clientName = '';
    pagination.page = 1;
    syncQueryToRoute();
    fetchProducts();
  };

  const handleSizeChange = (size) => {
    pagination.pageSize = size;
    pagination.page = 1;
    fetchProducts();
  };

  const handlePageChange = (page) => {
    pagination.page = page;
    fetchProducts();
  };

  const ensureCsrf = async () => {
    let token = getCsrfToken();
    if (token) return true;
    const ok = await ensureCsrfToken(() =>
      getProductList({ page: 1, page_size: 1 }).then(() => undefined)
    );
    token = getCsrfToken();
    return Boolean(ok || token);
  };

  const saveProduct = async ({ id, data, callback }) => {
    try {
      const isTransferProduct =
        id &&
        data.client_id &&
        !data.name &&
        data.ecpm_deduct_ratio === undefined &&
        data.revenue_deduct_ratio === undefined;

      if (!isTransferProduct) {
        if (!data.name || String(data.name).trim() === '') {
          ElMessage.error('产品名称不能为空');
          callback?.(false);
          return false;
        }
        if (data.ecpm_deduct_ratio === undefined || data.ecpm_deduct_ratio === null) {
          ElMessage.error('eCPM减扣比例不能为空');
          callback?.(false);
          return false;
        }
        if (data.revenue_deduct_ratio === undefined || data.revenue_deduct_ratio === null) {
          ElMessage.error('收益减扣比例不能为空');
          callback?.(false);
          return false;
        }
      }

      if (!data.client_id) {
        ElMessage.error('客户ID不能为空');
        callback?.(false);
        return false;
      }

      if (!(await ensureCsrf())) {
        ElMessage.error('无法获取安全令牌，请刷新页面后重试');
        callback?.(false);
        return false;
      }

      if (!id) {
        await createProduct(data);
        ElMessage.success('产品创建成功');
      } else {
        await updateProduct(id, data);
        ElMessage.success('产品更新成功');
      }
      await fetchProducts();
      callback?.(true);
      return true;
    } catch (error) {
      logger.error('saveProduct: 保存失败', error);
      if (!error.message?.includes('取消') && !error.message?.includes('validate')) {
        if (!isErrorHandled(error)) {
          ElMessage.error(extractErrorMessage(error));
        }
      }
      callback?.(false);
      return false;
    }
  };

  const removeProduct = async (id) => {
    try {
      if (!(await ensureCsrf())) {
        ElMessage.error('无法获取安全令牌，请刷新页面后重试');
        return false;
      }
      loading.value = true;
      const result = await deleteProduct(id);
      if (result?.transferred) {
        ElMessage.success(result.message || '产品已转移至临时挂靠（保留关联广告数据）');
      } else {
        ElMessage.success(result?.message || '产品删除成功');
      }
      await fetchProducts();
      return true;
    } catch (error) {
      if (!error.message?.includes('取消') && !isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
      return false;
    } finally {
      loading.value = false;
    }
  };

  const formEmit = (event, payload) => {
    if (event === 'save') {
      saveProduct(payload);
    }
  };

  const productForm = useProductForm(formScope, formEmit);

  const setFormScopeForProduct = (product) => {
    const cid = product?.client_id ?? null;
    formScope.clientId = cid;
    formScope.clientName =
      (cid != null && clientLabelMap.value[cid]) ||
      product?.client_name ||
      (cid != null ? `客户#${cid}` : '');
  };

  const handleAddClick = async () => {
    if (searchForm.clientId != null) {
      syncFormScopeFromFilter();
      await productForm.handleAdd();
      return;
    }
    if (formScope.clientId != null) {
      await productForm.handleAdd();
      return;
    }
    pendingClientId.value = null;
    clientPickerVisible.value = true;
  };

  const confirmClientPicker = async () => {
    if (pendingClientId.value == null) {
      ElMessage.warning('请选择所属客户');
      return;
    }
    formScope.clientId = pendingClientId.value;
    formScope.clientName =
      clientLabelMap.value[pendingClientId.value] || `客户#${pendingClientId.value}`;
    clientPickerVisible.value = false;
    await productForm.handleAdd();
  };

  const handleEditClick = async (product) => {
    setFormScopeForProduct(product);
    await productForm.handleEdit(product);
  };

  const handleDeleteClick = async (id) => {
    try {
      await ElMessageBox.confirm(
        '确定要删除此产品吗？若产品仍有关联广告数据，将转移到「临时挂靠」并保留广告数据；无关联数据时会彻底删除。',
        '确认删除',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning',
          icon: markRaw(Warning),
        }
      );
      await removeProduct(id);
    } catch {
      // 用户取消
    }
  };

  watch(
    () => searchForm.clientId,
    () => {
      syncFormScopeFromFilter();
    }
  );

  return {
    loading,
    products,
    clientOptions,
    clientLabelMap,
    clientPickerVisible,
    pendingClientId,
    searchForm,
    pagination,
    formScope,
    productForm,
    applyRouteQuery,
    loadClientOptions,
    fetchProducts,
    handleSearch,
    handleReset,
    handleSizeChange,
    handlePageChange,
    handleAddClick,
    confirmClientPicker,
    handleEditClick,
    handleDeleteClick,
    saveProduct,
    removeProduct,
  };
}
