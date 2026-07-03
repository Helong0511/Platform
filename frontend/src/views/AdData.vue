<!--
  广告数据入口：子路由容器
  @file views/AdData.vue
-->
<template>
  <!-- 页面主模板 -->
<div class="ad-data-container">
    <div class="page-header">
      <h2 class="page-title">广告明细维护</h2>
      <div class="action-buttons">
        <el-button 
          type="primary" 
          @click="handleExport" 
          :icon="Download"
          :size="isMobile ? 'default' : 'default'"
        >
          导出数据
        </el-button>
        <el-button 
          v-if="isAdmin && selectedRows.length > 0" 
          type="danger" 
          @click="handleBatchDelete" 
          :icon="Delete"
          :size="isMobile ? 'default' : 'default'"
        >
          <span v-if="!isMobile">批量删除 ({{ selectedRows.length }})</span>
          <span v-else>批量删除</span>
        </el-button>
      </div>
    </div>

    <!-- 筛选控件 -->
    <AdDataFilterCard
      v-model:search-form="searchForm"
      :is-admin="isAdmin"
      :loading="loading"
      :users="users"
      :filter-products="filterProducts"
      :filter-countries="filterCountries"
      :filter-ad-units="filterAdUnits"
      default-hint="行级明细，支持修改与删除。GAM/Addermobi 等交叉数据请选「按广告单元+国家」；Zhisuo 纯国家数据请选「按国家」。"
      @fetch="fetchAdData"
      @reset="resetFilter"
      @date-range-change="handleDateRangeChange"
      @filter-client-change="onFilterClientChange"
      @filter-product-change="onFilterProductChange"
      @dimension-change="onDimensionChange"
      @country-change="onCountryChange"
      @ad-unit-change="onAdUnitChange"
    />

    <AdDataDetailTable
      v-model:pagination="pagination"
      :loading="loading"
      :ad-data-list="adDataList"
      :empty-text="detailEmptyText"
      :column-visibility="effectiveColumnVisibility"
      :is-admin="isAdmin"
      :is-mobile="isMobile"
      :format-percentage="formatPercentage"
      :format-currency="formatCurrency"
      :get-summaries="getSummariesForTable"
      @selection-change="handleSelectionChange"
      @sort-change="handleSortChange"
      @edit="handleEdit"
      @delete="handleDelete"
      @product-click="handleProductClick"
      @open-column-settings="columnSettingVisible = true"
    />

    <AdDataEditDialog
      v-model:visible="editDialogVisible"
      ref="editDialogRef"
      :edit-form="editForm"
      :edit-rules="editRules"
      :users="users"
      :products="products"
      :is-mobile="isMobile"
      @save="saveEdit"
      @cancel="cancelEdit"
      @product-change="handleProductChange"
      @country-help="handleCountryCodeHelp"
    />

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      :append-to-body="true"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="date" :disabled="true">数据日期（固定显示）</el-checkbox>
        <el-checkbox v-if="isAdmin" label="user_name">所属客户</el-checkbox>
        <el-checkbox label="product_name" :disabled="true">产品名称（固定显示）</el-checkbox>
        <el-checkbox label="ad_unit">广告单元</el-checkbox>
        <el-checkbox label="country_name_zh">国家</el-checkbox>
        <el-checkbox label="request_count">请求数</el-checkbox>
        <el-checkbox label="match_count">匹配数</el-checkbox>
        <el-checkbox label="coverage_rate">覆盖率</el-checkbox>
        <el-checkbox label="display_count">展示数</el-checkbox>
        <el-checkbox label="display_rate">展示率</el-checkbox>
        <el-checkbox label="click_count">点击数</el-checkbox>
        <el-checkbox label="click_rate">点击率</el-checkbox>
        <el-checkbox label="viewability_rate">可见率</el-checkbox>
        <el-checkbox label="cpc">CPC</el-checkbox>
        <el-checkbox label="pageviews">PageViews</el-checkbox>
        <el-checkbox label="ecpm_after_deduct">eCPM(扣)</el-checkbox>
        <el-checkbox v-if="isAdmin" label="ecpm_before_deduct">eCPM</el-checkbox>
        <el-checkbox label="revenue_after_deduct">收益(扣)</el-checkbox>
        <el-checkbox v-if="isAdmin" label="revenue_before_deduct">收益</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>

    <!-- 产品管理对话框 -->
    <ProductManagementDialog
      v-model="productManagementVisible"
      :client-id="selectedClientId"
      :client-name="selectedClientName"
      :products="selectedClientProducts"
      :loading="loadingProducts"
      @refresh="handleProductManagementRefresh"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue';
import { useAuthStore } from '../store';
import { ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem, ElSelect, ElOption, ElDatePicker, ElTag, ElIcon, ElLoading, ElMessage, ElMessageBox, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus';
import { Download, Delete, Setting } from '@element-plus/icons-vue';
import { getAdDataList, exportAdData, getProductsForSelect, updateAdData, getProductById, deleteAdData, batchDeleteAdData } from '../api/ad-data';
import { useRouter, useRoute } from 'vue-router';
import { getSuccessMessage, getWarningMessage } from '../utils/messages';
import { extractErrorMessage, isErrorHandled } from '../utils/api';
import { ensureCsrfToken } from '../utils/csrfMutate';
import { useDevice } from '../composables/useDevice';
import { useAdDataTableFormat } from '../composables/useAdDataTableFormat';
import {
  useAdDataColumnVisibility,
  createAdDataDefaultColumns,
  AD_DATA_SAVABLE_COLUMN_KEYS
} from '../composables/useAdDataColumnVisibility';
import { useDataPageFilterCascade } from '../composables/useDataPageFilterCascade';
import { useDebouncedPaginatedFetch } from '../composables/useDebouncedPaginatedFetch';
import { useAdDataDateRangeBootstrap } from '../composables/useAdDataDateRangeBootstrap';
import { useAdDataProductPanel } from '../composables/useAdDataProductPanel';
import {
  appendDimensionAwareFilters,
  applyDimensionColumnDefaults,
  DEFAULT_AD_DATA_DETAIL_DIMENSION,
  loadAdDataDetailDimensionPreference,
  saveAdDataDetailDimensionPreference,
  normalizeAdDataDimension
} from '../constants/adDataDimension';
import ProductManagementDialog from '../components/admin/ProductManagementDialog.vue';
import AdDataFilterCard from '../components/ad-data/AdDataFilterCard.vue';
import AdDataDetailTable from '../components/ad-data/AdDataDetailTable.vue';
import AdDataEditDialog from '../components/ad-data/AdDataEditDialog.vue';

// 路由实例
const router = useRouter();
const route = useRoute();

// 获取用户认证状态
const authStore = useAuthStore();
const isAdmin = computed(() => authStore.isAdmin);

// 设备检测
const { isMobile, isTablet, isDesktop } = useDevice();

// 状态管理
const adDataList = ref([]);
const detailGrandTotal = ref(null);
const products = ref([]);
const loading = ref(false);
const pagination = ref({
  current: 1,
  size: 10,
  total: 0
});

const {
  productManagementVisible,
  selectedClientId,
  selectedClientName,
  selectedClientProducts,
  loadingProducts,
  selectedProductId,
  selectedProductName,
  openProductPanel,
  loadClientProducts
} = useAdDataProductPanel();

// 排序状态
const sortInfo = ref({
  prop: 'date',
  order: 'descending' // 'ascending' 或 'descending'
});

// 筛选表单
const searchForm = ref({
  clientId: '',
  dateRange: [],
  productId: '',
  dimension: loadAdDataDetailDimensionPreference(authStore.userInfo?.id),
  countryCode: '',
  adUnit: ''
});

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility
} = useAdDataColumnVisibility(
  'adData_columnVisibility',
  () => createAdDataDefaultColumns(() => isAdmin.value),
  AD_DATA_SAVABLE_COLUMN_KEYS
);

const { formatPercentage, formatCurrency, getSummaries } = useAdDataTableFormat({
  getIsAdmin: () => isAdmin.value,
  cpcSummaryMode: 'weighted'
});

const getSummariesForTable = (param) => {
  const data = detailGrandTotal.value ? [detailGrandTotal.value] : param.data;
  return getSummaries({ ...param, data });
};

const {
  users,
  filterProducts,
  filterCountries,
  filterAdUnits,
  fetchClientsWithData,
  fetchFilterProducts,
  loadAllFilterOptions,
  handleFilterClientChange,
  handleFilterProductChange,
  handleDimensionChange,
  handleCountryChange,
  handleAdUnitChange,
  reloadFiltersAfterDateChange,
  reloadSecondaryFilters,
  pruneInvalidFilterSelections
} = useDataPageFilterCascade({
  searchForm,
  includeCountry: true,
  includeDimension: true,
  source: 'ad-data',
  getUserId: () => authStore.userInfo?.id,
  defaultDimension: DEFAULT_AD_DATA_DETAIL_DIMENSION,
  loadDimensionPreference: loadAdDataDetailDimensionPreference,
  saveDimensionPreference: saveAdDataDetailDimensionPreference
});

const buildAdDataSearchParams = () => {
  const dimension = searchForm.value.dimension || DEFAULT_AD_DATA_DETAIL_DIMENSION;
  const params = { dimension };
  if (isAdmin.value && searchForm.value.clientId) {
    params.client_id = searchForm.value.clientId;
  }
  if (searchForm.value.productId) {
    params.product_id = searchForm.value.productId;
  }
  appendDimensionAwareFilters(params, {
    dimension,
    countryCode: searchForm.value.countryCode,
    adUnit: searchForm.value.adUnit
  });
  if (searchForm.value.dateRange?.length === 2) {
    params.start_date = searchForm.value.dateRange[0];
    params.end_date = searchForm.value.dateRange[1];
  }
  return params;
};

/** 列设置 + 统计维度：仅影响表格展示 */
const effectiveColumnVisibility = computed(() =>
  applyDimensionColumnDefaults(columnVisibility, searchForm.value.dimension)
);

const detailEmptyText = computed(() => {
  const dim = normalizeAdDataDimension(
    searchForm.value.dimension || DEFAULT_AD_DATA_DETAIL_DIMENSION
  );
  if (dim === 'country') {
    return '当前为「按国家」维度，仅显示无广告单元的纯国家行。若库中均为交叉明细，请切换为「按广告单元+国家」。';
  }
  if (dim === 'ad_unit') {
    return '当前为「按广告单元」维度，仅显示无国家代码的纯广告单元行。若库中均为交叉明细，请切换为「按广告单元+国家」。';
  }
  return '暂无数据';
});

const {
  ensureInitialDateRange,
  handleEmptyWithDateBootstrap,
  resetDateBootstrap
} = useAdDataDateRangeBootstrap({
  searchForm,
  isAdmin,
  pagination,
  refetch: () => fetchAdData(),
  onDateRangeChanged: () => reloadFiltersAfterDateChange(isAdmin.value)
});

const { runFetch: fetchAdData, cancel: cancelAdDataFetch } = useDebouncedPaginatedFetch({
  loading,
  pagination,
  buildParams: () => {
    const params = {
      page: pagination.value.current,
      page_size: pagination.value.size,
      ...buildAdDataSearchParams()
    };
    if (sortInfo.value.prop) {
      params.sort_by = sortInfo.value.prop;
      params.sort_order = sortInfo.value.order === 'ascending' ? 'asc' : 'desc';
    }
    return params;
  },
  fetchPage: (params) => getAdDataList(params),
  applyResponse: (response) => {
    adDataList.value = response.data || [];
    detailGrandTotal.value = response.grand_total || null;
    pagination.value.total =
      typeof response.total === 'number'
        ? response.total
        : parseInt(response.total || 0, 10);
    if (adDataList.value.length > 0) {
      const requiredFields = ['date', 'product_name', 'request_count', 'match_count'];
      const missingFields = requiredFields.filter((field) => !(field in adDataList.value[0]));
      if (missingFields.length > 0) {
        ElMessage.warning(`数据格式不完整，缺少字段: ${missingFields.join(', ')}`);
      }
    }
  },
  checkAuth: () => authStore.isAuthenticated,
  onUnauthenticated: () => {
    ElMessage.warning('登录已过期，请重新登录');
    router.push('/login').catch(() => {
      window.location.href = '/login';
    });
  },
  afterEmpty: handleEmptyWithDateBootstrap
});

// 编辑对话框产品下拉
const fetchProducts = async (clientId) => {
  try {
    const data = await getProductsForSelect(clientId);
    // 移除label中的编号前缀
    products.value = data.map(item => ({
      value: item.value,
      label: item.label.replace(/^\d+\s*-\s*/, '')
    }));
  } catch (error) {
    // 静默失败，使用空数组
    products.value = [];
  }
};

const handleDateRangeChange = async () => {
  await nextTick();
  await reloadFiltersAfterDateChange(isAdmin.value);
  pagination.value.current = 1;
  fetchAdData();
};

const refetchAfterFilterCascade = () => {
  pagination.value.current = 1;
  fetchAdData();
};

const onFilterClientChange = async () => {
  await handleFilterClientChange();
  pruneInvalidFilterSelections(isAdmin.value);
  refetchAfterFilterCascade();
};

const onFilterProductChange = async () => {
  await handleFilterProductChange();
  pruneInvalidFilterSelections(isAdmin.value);
  refetchAfterFilterCascade();
};

const onDimensionChange = async () => {
  await handleDimensionChange();
  pruneInvalidFilterSelections(isAdmin.value);
  refetchAfterFilterCascade();
};

const onCountryChange = async () => {
  await handleCountryChange();
  pruneInvalidFilterSelections(isAdmin.value);
  refetchAfterFilterCascade();
};

const onAdUnitChange = async () => {
  await handleAdUnitChange();
  pruneInvalidFilterSelections(isAdmin.value);
  refetchAfterFilterCascade();
};

// 处理排序变化
const handleSortChange = ({ prop, order }) => {
  if (prop) {
    // 处理特殊字段映射
    let sortProp = prop;
    if (prop === 'product_name') {
      sortProp = 'product'; // 后端使用 'product' 作为产品名称排序字段
    }
    
    sortInfo.value.prop = sortProp;
    sortInfo.value.order = order || 'descending';
    // 重置到第一页
    pagination.value.current = 1;
    // 重新获取数据
    fetchAdData();
  }
};

// 重置筛选条件
const resetFilter = async () => {
  resetDateBootstrap();
  searchForm.value = {
    clientId: '',
    dateRange: [],
    productId: '',
    dimension: loadAdDataDetailDimensionPreference(authStore.userInfo?.id),
    countryCode: '',
    adUnit: ''
  };
  pagination.value.current = 1;
  // 重置排序
  sortInfo.value = {
    prop: 'date',
    order: 'descending'
  };

  await ensureInitialDateRange();
  await reloadFiltersAfterDateChange(isAdmin.value);
  fetchAdData();
};

// 监听分页变化
let isInitializing = true;
let isChangingPageSize = false; // 标记是否正在改变每页条数

watch(
  () => [pagination.value.current, pagination.value.size],
  ([newCurrent, newSize], [oldCurrent, oldSize]) => {
    // 跳过初始化时的触发
    if (isInitializing) {
      return;
    }
    
    // 如果 oldCurrent 或 oldSize 是 undefined，说明是第一次触发，跳过
    if (oldCurrent === undefined || oldSize === undefined) {
      return;
    }
    
    // 如果正在改变每页条数，且页码被重置为1，这是预期的行为，直接刷新数据
    if (isChangingPageSize && newCurrent === 1 && newSize === oldSize) {
      isChangingPageSize = false;
      fetchAdData();
      return;
    }
    
    // 如果只是页码变化，直接刷新
    if (newCurrent !== oldCurrent && newSize === oldSize) {
      fetchAdData();
    }
    // 如果每页条数变化
    else if (newSize !== oldSize) {
      // 标记正在改变每页条数
      isChangingPageSize = true;
      // 如果页码不是第一页，重置到第一页（这会触发 watch 再次执行）
      if (newCurrent !== 1) {
        pagination.value.current = 1;
      } else {
        // 如果已经在第一页，直接刷新
        isChangingPageSize = false;
        fetchAdData();
      }
    }
  },
  { flush: 'post' }
);

// 编辑对话框状态
const editDialogVisible = ref(false);
const editDialogRef = ref(null);
// 表单验证规则
const editRules = ref({
  product_id: [
  { required: true, message: '请选择产品', trigger: ['change', 'submit'] }
]
});

const editForm = ref({
  id: null,
  date: '',
  client_id: '',
  product_id: '',
  ad_unit: '',
  country_code: '',
  request_count: 0,
  match_count: 0,
  coverage_rate: 0,
  display_count: 0,
  display_rate: 0,
  click_count: 0,
  click_rate: 0,
  viewability_rate: 0,
  cpc: 0,
  pageviews: 0,
  ecpm_after_deduct: 0,
  ecpm_before_deduct: 0,
  revenue_after_deduct: 0,
  revenue_before_deduct: 0
});

// 客户ID变化时重新获取产品列表
watch(
  () => editForm.value.client_id,
  async (newVal, oldVal) => {
    // 只有在编辑模式下且客户ID真正变化时才清空产品ID
    // 避免在初始化编辑表单时清空产品ID
    if (newVal !== oldVal && oldVal !== null && oldVal !== undefined && oldVal !== '') {
      // 保存当前产品ID（如果存在）
      const currentProductId = editForm.value.product_id;
      
      if (newVal) {
        try {
          const clientProducts = await getProductsForSelect(newVal);
          products.value = clientProducts.map(item => ({
            value: item.value,
            label: item.label.replace(/^\d+\s*-\s*/, '')
          }));
          
          // 如果新列表中没有当前产品ID，则清空
          const productExists = products.value.some(p => p.value === currentProductId);
          if (!productExists) {
            editForm.value.product_id = null;
          }
        } catch (error) {
          if (!isErrorHandled(error)) {
            const errorMsg = extractErrorMessage(error);
            ElMessage.error(errorMsg);
          }
          products.value = [];
          editForm.value.product_id = null;
        }
      } else {
        products.value = [];
        editForm.value.product_id = null;
      }
    }
  }
);

// 修改数据（仅管理员）
const handleEdit = async (row) => {
  // 确保用户列表已加载（仅管理员需要）
  if (isAdmin.value && users.value.length === 0) {
    await fetchClientsWithData();
  }
  
  // 先设置基本信息，包括产品ID
  const currentProductId = row.product_id;
  
  // 加载产品列表（必须在使用前完成）
  if (row.client_id) {
    await fetchProducts(row.client_id);
    
    // 检查当前产品ID是否在产品列表中
    const productExists = products.value.some(p => p.value === currentProductId);
    if (!productExists && currentProductId) {
      // 如果产品不在列表中（可能已删除），尝试获取产品详情并添加到列表
      try {
        const productDetail = await getProductById(currentProductId);
        if (productDetail && productDetail.name) {
          products.value.push({
            value: currentProductId,
            label: productDetail.name
          });
        }
      } catch (error) {
        // 如果获取失败，至少保留产品ID，让用户知道需要选择新产品
        ElMessage.warning('原产品可能已不存在，请重新选择产品');
      }
    }
  }
  
  // 初始化编辑表单（确保产品列表已加载）
  editForm.value = {
    id: row.id,
    date: row.date,
    client_id: row.client_id,
    product_id: currentProductId, // 确保使用原始产品ID
    ad_unit: row.ad_unit || '',
    country_code: row.country_code ?? '',
    request_count: row.request_count,
    match_count: row.match_count,
    coverage_rate: row.coverage_rate || 0,
    display_count: row.display_count || 0,
    display_rate: row.display_rate || 0,
    click_count: row.click_count || 0,
    click_rate: row.click_rate || 0,
    viewability_rate: row.viewability_rate || 0,
    cpc: row.cpc || 0,
    pageviews: row.pageviews || 0,
    ecpm_after_deduct: row.ecpm_after_deduct || 0,
    ecpm_before_deduct: row.ecpm_before_deduct || 0,
    revenue_after_deduct: row.revenue_after_deduct || 0,
    revenue_before_deduct: row.revenue_before_deduct || 0
  };
  
  // 使用 nextTick 确保 DOM 更新后再打开对话框
  await nextTick();
  editDialogVisible.value = true;
};

// 产品选择变化处理
const handleProductChange = (value) => {
  editForm.value.product_id = value;
};

// 国家代码帮助提示
const handleCountryCodeHelp = () => {
  ElMessage.info({
    message: '支持的国家代码格式：\n1. 二字母代码：US、CN、JP\n2. 三字母代码：USA、CHN、JPN\n3. 数字代码：840、156、392\n4. 英文名称：United States of America、China、Japan\n5. 中文名称：美国、中国、日本',
    duration: 5000,
    showClose: true
  });
};

// 删除广告数据
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除日期为 ${row.date} 的广告数据吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        appendTo: document.body, // 确保弹窗附加到 body，避免被对话框遮挡
        zIndex: 3001 // 确保 z-index 高于对话框
      }
    );
    
    // 确保CSRF令牌存在
    await ensureCsrfToken(() => fetchAdData());
    
    loading.value = true;
    await deleteAdData(row.id);
    ElMessage.success(getSuccessMessage('DATA_DELETE_SUCCESS'));
    await fetchAdData(); // 刷新数据列表
  } catch (error) {
    if (error !== 'cancel') {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
  } finally {
    loading.value = false;
  }
};

// 批量删除广告数据
const handleBatchDelete = async () => {
  if (selectedRows.value.length === 0) {
    ElMessage.warning(getWarningMessage('SELECT_DATA_TO_DELETE'));
    return;
  }
  
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedRows.value.length} 条广告数据吗？此操作不可恢复。`,
      '确认批量删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        appendTo: document.body, // 确保弹窗附加到 body，避免被对话框遮挡
        zIndex: 3001 // 确保 z-index 高于对话框
      }
    );
    
    // 确保CSRF令牌存在
    await ensureCsrfToken(() => fetchAdData());
    
    loading.value = true;
    const dataIds = selectedRows.value.map(row => row.id);
    // batchDeleteAdData使用returnDataOnly: true，成功时直接返回数据，失败时抛出异常
    const response = await batchDeleteAdData(dataIds);
    
    // 如果执行到这里，说明操作成功（失败会抛出异常）
    const deletedCount = response?.deleted_count || selectedRows.value.length;
    ElMessage.success(getSuccessMessage('DATA_BATCH_DELETE_SUCCESS', deletedCount));
    selectedRows.value = []; // 清空选择
    await fetchAdData(); // 刷新数据列表
  } catch (error) {
    if (error !== 'cancel') {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
  } finally {
    loading.value = false;
  }
};

// 保存编辑
const saveEdit = async () => {
  try {
    // 确保CSRF令牌存在
    await ensureCsrfToken(() => fetchAdData());
    
    // 触发表单验证
    const formRef = editDialogRef.value?.formRef;
    if (!formRef) return;
    await formRef.validate();
    
    // 准备提交数据（只提交允许更新的字段）
    const payload = {
      id: editForm.value.id,
      product_id: editForm.value.product_id,
      ad_unit: editForm.value.ad_unit || '',
      country_code: editForm.value.country_code?.trim() || null,
      request_count: editForm.value.request_count,
      match_count: editForm.value.match_count,
      display_count: editForm.value.display_count,
      click_count: editForm.value.click_count,
      viewability_rate: editForm.value.viewability_rate,
      cpc: editForm.value.cpc,
      pageviews: editForm.value.pageviews,
      ecpm_after_deduct: editForm.value.ecpm_after_deduct,
      ecpm_before_deduct: editForm.value.ecpm_before_deduct,
      revenue_after_deduct: editForm.value.revenue_after_deduct,
      revenue_before_deduct: editForm.value.revenue_before_deduct
    };
    
    // 验证产品ID是否存在
    if (!payload.product_id) {
      ElMessage.error('请选择产品');
      return;
    }
    
    // 调用更新API
    const response = await updateAdData(payload);
    
    // updateAdData使用returnDataOnly: true，成功时直接返回数据，失败时抛出异常
    // 如果执行到这里，说明操作成功（失败会抛出异常）
    ElMessage.success(getSuccessMessage('DATA_UPDATE_SUCCESS'));
    editDialogVisible.value = false;
    fetchAdData(); // 刷新数据列表
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
  }
};

// 取消编辑
const cancelEdit = () => {
  editDialogVisible.value = false;
};

// 导出数据
const handleExport = async () => {
  try {
    // 对于客户用户，先检查是否有数据
    if (!isAdmin.value) {
      // 检查总数据量
      if (pagination.value.total === 0) {
        ElMessage.warning('当前没有可导出的数据，请先查询数据或导入数据');
        return;
      }
      
      // 如果当前列表为空但总数不为0，可能是筛选条件导致，仍然允许导出（让后端验证）
      // 但可以给用户一个提示
      if (adDataList.value.length === 0 && pagination.value.total > 0) {
        ElMessage.info('当前筛选条件下当前页无数据，将导出所有符合筛选条件的数据');
      }
    }
    
    const params = { ...buildAdDataSearchParams() };
    if (params.client_id) {
      params.client_id = parseInt(params.client_id, 10);
    }
    if (params.product_id) {
      params.product_id = parseInt(params.product_id, 10);
    }

    await exportAdData(params);
    // 导出成功，显示提示信息
    ElMessage.success(getSuccessMessage('DATA_EXPORT_SUCCESS'));
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    
    // 如果是"无数据，不能导出"的错误，直接显示该消息
    if (errorMsg.includes('无数据') || errorMsg.includes('不能导出')) {
      ElMessage.warning(getWarningMessage('NO_DATA_TO_EXPORT'));
    } else {
      ElMessage.error(errorMsg);
    }
  }
};

// 选中的行
const selectedRows = ref([]);

// 选择项变更
const handleSelectionChange = (selection) => {
  selectedRows.value = selection;
};

// 加载页面数据的函数
const loadPageData = async () => {
  try {
    // 检查认证状态，如果token过期，直接返回
    if (!authStore.isAuthenticated) {
      // token不存在或已过期，跳转到登录页
      ElMessage.warning('登录已过期，请重新登录');
      router.push('/login').catch(() => {
        window.location.href = '/login';
      });
      return;
    }
    
    // 设置加载超时保护（20秒，避免过长等待）
    let timeoutId = null;
    const timeoutPromise = new Promise((_, reject) => {
      timeoutId = setTimeout(() => {
        reject(new Error('页面加载超时，请检查网络连接或刷新页面'));
      }, 20000);
    });
    
    // 优先加载广告数据（关键数据，用户最关心）
    await ensureInitialDateRange();
    const criticalPromises = [
      fetchAdData().catch(error => {
        if (error.response?.status === 401) {
          return;
        }
        // 静默处理错误
      })
    ];
    
    // 先等待关键数据加载完成
    try {
      await Promise.race([
        Promise.allSettled(criticalPromises),
        timeoutPromise
      ]);
    } finally {
      // 清理超时定时器
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    }
    
    // 然后并行加载非关键数据（客户列表、产品列表等）
    // 这些数据可以延迟加载，不影响用户查看主要数据
    const nonCriticalPromises = [];
    
    // 加载筛选下拉（客户 / 产品 / 国家 / 广告单元）
    nonCriticalPromises.push(
      loadAllFilterOptions(isAdmin.value).catch(error => {
        if (error.response?.status === 401) {
          return;
        }
        // 静默处理错误
      })
    );

    // 预加载编辑对话框产品列表（打开编辑时再按客户刷新）
    nonCriticalPromises.push(
      fetchProducts(null).catch(error => {
        if (error.response?.status === 401) {
          return;
        }
        // 静默处理错误
      })
    );
    
    // 非关键数据异步加载，不阻塞页面显示
    Promise.allSettled(nonCriticalPromises).catch(() => {
      // 静默处理错误，不影响用户体验
    });
  } catch (error) {
    // 超时或其他错误
    if (error.message && error.message.includes('超时')) {
      ElMessage.error(error.message);
      // 超时后停止loading
      loading.value = false;
    } else if (error.response?.status === 401) {
      // 401错误已在拦截器中处理，这里不需要额外处理
      loading.value = false;
    } else {
      // 其他错误
      if (!isErrorHandled(error)) {
        const errorMsg = extractErrorMessage(error);
        ElMessage.error(`页面初始化失败: ${errorMsg}`);
      }
      loading.value = false;
    }
  }
};

// 标记是否已经初始化
let isPageInitialized = false;

// 页面挂载时加载数据
let mountedTimeoutId = null;
onMounted(async () => {
  // 路由守卫已经处理了认证检查，这里不需要重复检查
  // 延迟加载数据，让页面先渲染出来
  await nextTick();
  
  // 加载列显示设置
  loadColumnVisibility();
  
  mountedTimeoutId = setTimeout(async () => {
    await loadPageData();
    // 初始化完成后，启用分页 watch
    await nextTick();
    isInitializing = false;
    isPageInitialized = true;
    mountedTimeoutId = null;
  }, 0);
});

// 组件卸载时清理定时器
onUnmounted(() => {
  if (mountedTimeoutId) {
    clearTimeout(mountedTimeoutId);
    mountedTimeoutId = null;
  }
  cancelAdDataFetch();
});

const handleProductClick = (row) => {
  openProductPanel(row, {
    defaultClientId: authStore.userInfo?.id,
    defaultClientName: authStore.userInfo?.full_name || '未知客户'
  });
};

const handleProductManagementRefresh = () => {
  fetchAdData();
};

// 监听路由变化，当从其他页面导航到本页时自动刷新数据
const ADMIN_AD_DATA_ROWS_PATH = '/app/admin/ad-data-rows';

watch(
  () => route.path,
  (newPath, oldPath) => {
    if (
      newPath === ADMIN_AD_DATA_ROWS_PATH &&
      isPageInitialized &&
      oldPath &&
      oldPath !== ADMIN_AD_DATA_ROWS_PATH
    ) {
      pagination.value.current = 1;
      loadPageData();
    }
  },
  { immediate: false }
);

</script>

<style scoped>
.ad-data-container {
  width: 100%;
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xl);
  padding: var(--spacing-xl);
  background-color: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  flex-shrink: 0;
}

.action-buttons {
  display: flex;
  gap: var(--spacing-md);
}

.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

/* 筛选项宽度与响应式样式见 AdDataFilterCard.vue */

.pagination-container {
  margin-top: var(--spacing-lg);
  padding: var(--spacing-lg) 0;
  text-align: right;
  border-top: 1px solid var(--border-lighter);
}

.data-table-card {
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
  overflow: hidden;
}

.data-table-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
}

.edit-form {
  padding: var(--spacing-md) 0;
}

.edit-form :deep(.el-form-item) {
  margin-bottom: var(--spacing-lg);
}

.edit-form :deep(.el-form-item__label) {
  white-space: nowrap;
  line-height: 32px;
  text-align: right;
  padding-right: var(--spacing-md);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

/* 对话框footer按钮优化 */
.dialog-footer {
  display: flex;
  justify-content: center;
  gap: 12px;
  width: 100%;
}

.dialog-footer .el-button {
  min-width: 90px;
  padding: 8px 20px;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .ad-data-container {
    padding: var(--spacing-md);
  }
  
  .page-header {
    flex-direction: column;
    align-items: stretch;
    gap: var(--spacing-md);
    padding: var(--spacing-md);
    margin-bottom: var(--spacing-md);
  }
  
  .action-buttons {
    flex-direction: column;
    width: 100%;
    gap: var(--spacing-sm);
  }
  
  .action-buttons .el-button {
    width: 100%;
    min-height: var(--touch-target-size);
  }
  
  .filter-card {
    margin-bottom: var(--spacing-md);
  }
  
  .filter-card :deep(.el-card__body) {
    padding: var(--spacing-md);
  }
  
  .data-table-card {
    margin-bottom: var(--spacing-md);
  }
  
  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  /* 移动端表格优化 */
  .el-table {
    font-size: var(--font-size-sm);
    min-width: 800px; /* 确保表格有最小宽度，可以横向滚动 */
  }
  
  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-xs) var(--spacing-sm);
    word-break: break-word;
  }
  
  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
  }
  
  .el-table :deep(.el-table-column--selection) {
    width: 50px !important;
  }
  
  .pagination-container {
    margin-top: var(--spacing-md);
    padding: var(--spacing-md) 0;
    text-align: center;
  }
  
  /* 移动端分页组件优化 */
  .pagination-component {
    flex-wrap: wrap;
    justify-content: center;
    font-size: var(--font-size-sm);
  }
  
  .pagination-component :deep(.el-pagination__total) {
    margin-right: var(--spacing-sm);
    font-size: var(--font-size-sm);
  }
  
  .pagination-component :deep(.btn-prev),
  .pagination-component :deep(.btn-next),
  .pagination-component :deep(.el-pager li) {
    min-width: var(--touch-target-size);
    min-height: var(--touch-target-size);
    font-size: var(--font-size-sm);
  }
  
  /* 移动端对话框优化 */
  .el-dialog {
    width: 95% !important;
    margin: var(--spacing-md) auto !important;
  }
  
  .el-dialog :deep(.el-dialog__body) {
    padding: var(--spacing-md);
  }
  
  .edit-form :deep(.el-form-item__label) {
    width: 100px !important;
    text-align: left;
  }
  
  /* 移动端表格操作按钮优化 */
  .el-table :deep(.el-table-column--action) {
    width: 120px !important;
  }
  
  .el-table :deep(.el-table-column--action .el-button) {
    padding: 4px 8px;
    font-size: var(--font-size-xs);
    min-width: 50px;
    min-height: 32px;
  }
}

/* ====== 平板端优化 (768px - 1024px) ====== */
@media (min-width: 768px) and (max-width: 1024px) {
  .ad-data-container {
    padding: var(--spacing-lg);
  }
  
  .page-header {
    padding: var(--spacing-lg);
    margin-bottom: var(--spacing-lg);
  }
  
  .action-buttons {
    gap: var(--spacing-md);
  }
  
  .action-buttons .el-button {
    min-height: 40px;
  }
  
  .filter-card {
    margin-bottom: var(--spacing-lg);
  }
  
  .filter-card :deep(.el-card__body) {
    padding: var(--spacing-lg);
  }
  
  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-lg);
  }
  
  /* 平板端表格优化 */
  .el-table {
    font-size: var(--font-size-sm);
  }
  
  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-sm);
  }
  
  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-sm);
    padding: var(--spacing-sm);
  }
  
  /* 平板端分页优化 */
  .pagination-container {
    padding: var(--spacing-md) 0;
  }
  
  .pagination-component :deep(.el-pagination__total) {
    font-size: var(--font-size-sm);
  }
  
  .pagination-component :deep(.btn-prev),
  .pagination-component :deep(.btn-next),
  .pagination-component :deep(.el-pager li) {
    min-width: 36px;
    min-height: 36px;
    font-size: var(--font-size-sm);
  }
  
  /* 平板端对话框优化 */
  .el-dialog {
    width: 85% !important;
    max-width: 700px;
  }
  
  .el-dialog :deep(.el-dialog__body) {
    padding: var(--spacing-lg);
  }
}

/* ====== 小屏手机优化 (< 480px) ====== */
@media (max-width: 480px) {
  .ad-data-container {
    padding: var(--spacing-sm);
  }
  
  .page-header {
    padding: var(--spacing-sm);
    margin-bottom: var(--spacing-sm);
  }
  
  .action-buttons .el-button {
    font-size: var(--font-size-sm);
    padding: var(--spacing-sm) var(--spacing-md);
  }
  
  .filter-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
  }
  
  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-xs);
  }
  
  /* 小屏手机表格进一步优化 */
  .el-table {
    font-size: var(--font-size-xs);
    min-width: 700px; /* 小屏手机表格最小宽度稍小 */
  }
  
  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-xs);
  }
  
  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
    line-height: 1.3;
  }
  
  .el-table :deep(.el-table-column--selection) {
    width: 40px !important;
  }
  
  /* 小屏手机操作按钮进一步优化 */
  .el-table :deep(.el-table-column--action) {
    width: 100px !important;
  }
  
  .el-table :deep(.el-table-column--action .el-button) {
    padding: 2px 6px;
    font-size: var(--font-size-xs);
    min-width: 45px;
    min-height: 28px;
  }
  
  .pagination-container {
    padding: var(--spacing-sm) 0;
  }
  
  .pagination-component {
    font-size: var(--font-size-xs);
  }
  
  .pagination-component :deep(.el-pagination__total) {
    font-size: var(--font-size-xs);
    margin-right: var(--spacing-xs);
  }
  
  .pagination-component :deep(.btn-prev),
  .pagination-component :deep(.btn-next),
  .pagination-component :deep(.el-pager li) {
    min-width: 32px;
    min-height: 32px;
    font-size: var(--font-size-xs);
    padding: 0 4px;
  }
  
  /* 小屏手机对话框优化 */
  .el-dialog {
    width: 98% !important;
    margin: var(--spacing-sm) auto !important;
  }
  
  .el-dialog :deep(.el-dialog__body) {
    padding: var(--spacing-sm);
  }
  
  .edit-form :deep(.el-form-item__label) {
    width: 80px !important;
    font-size: var(--font-size-xs);
  }
  
  .edit-form :deep(.el-form-item__content) {
    font-size: var(--font-size-sm);
  }
  
  .dialog-footer .el-button {
    min-width: 80px;
    padding: 6px 16px;
    font-size: var(--font-size-sm);
  }
}

/* ====== 横屏模式优化 (移动设备横屏) ====== */
@media (max-width: 1024px) and (orientation: landscape) {
  .ad-data-container {
    padding: var(--spacing-md);
  }
  
  .page-header {
    flex-direction: row;
    align-items: center;
  }
  
  .action-buttons {
    flex-direction: row;
    width: auto;
  }
  
  .action-buttons .el-button {
    width: auto;
    min-width: 120px;
  }
  
  /* 横屏时表格可以显示更多列 */
  .el-table {
    min-width: 900px;
  }
}
/* 产品名称单元格样式 */
.product-name-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  cursor: pointer;
  padding: var(--spacing-xs) 0;
  transition: all 0.2s ease;
}

.product-name-cell:hover {
  color: var(--primary-color);
}

.product-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-icon {
  font-size: var(--font-size-sm);
  opacity: 0.6;
  transition: opacity 0.2s ease;
}

.product-name-cell:hover .product-icon {
  opacity: 1;
}
</style>