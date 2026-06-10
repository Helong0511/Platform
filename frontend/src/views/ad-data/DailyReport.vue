<!--
  广告数据 - 每日报表
  @file views/ad-data/DailyReport.vue
-->
<template>
  <!-- 页面主模板 -->
<div class="daily-report-container">
    <div class="page-header">
      <div class="action-buttons">
        <el-button type="primary" @click="handleExport" :icon="Download">
          导出数据
        </el-button>
      </div>
    </div>

    <!-- 筛选控件 -->
    <!-- 筛选区 -->
    <el-card class="filter-card">
      <!-- 表单区域 -->
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="日期范围">
          <el-date-picker
            v-model="searchForm.dateRange"
            name="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%;"
            @change="handleDateRangeChange"
          ></el-date-picker>
        </el-form-item>
        <el-form-item v-if="isAdmin" label="客户">
          <el-select 
            v-model="searchForm.clientId" 
            name="clientId"
            placeholder="全部客户" 
            style="width: 100%;"
            @change="handleFilterClientChange"
            clearable
          >
            <el-option v-for="user in users" :key="user.value" :label="user.label" :value="user.value"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="产品">
          <el-select 
            v-model="searchForm.productId" 
            name="productId"
            placeholder="全部产品" 
            style="width: 100%;"
            clearable
          >
            <el-option v-for="product in filterProducts" :key="product.value" :label="product.label" :value="product.value"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchDailyData" :loading="loading" :disabled="loading">查询</el-button>
          <el-button @click="resetFilter" :disabled="loading">重置</el-button>
        </el-form-item>
      </el-form>
      <div class="filter-hint">
        <el-icon :size="16"><InfoFilled /></el-icon>
        <span>每日报表显示按产品每日汇总的数据，国家统一显示"全部区域"。默认查询本月数据。</span>
      </div>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="data-table-card">
      <!-- 卡片标题栏 -->
    <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-weight: 600; font-size: 16px;">每日报表数据</span>
          <el-button 
            type="text" 
            :icon="Setting" 
            @click="columnSettingVisible = true"
          >
            列设置
          </el-button>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="dailyDataList"
        border
        stripe
        style="width: 100%"
        @sort-change="handleSortChange"
        :summary-method="getSummaries"
        show-summary
      >
        <el-table-column v-if="columnVisibility.date" prop="date" label="数据日期" sortable="custom"></el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.user_name" prop="user_name" label="所属客户"></el-table-column>
        <el-table-column v-if="columnVisibility.product_name" prop="product_name" label="产品名称" sortable="custom" sort-by="product" :min-width="150">
          <template #default="{ row }">
            <div class="product-name-cell" @click="handleProductClick(row)">
              <span class="product-name">{{ row.product_name }}</span>
              <el-icon class="product-icon"><Right /></el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.ad_unit" prop="ad_unit" label="广告单元" :min-width="120" show-overflow-tooltip></el-table-column>
        <el-table-column v-if="columnVisibility.country_name_zh" prop="country_name_zh" label="国家"></el-table-column>
        <el-table-column v-if="columnVisibility.request_count" prop="request_count" label="请求数" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.match_count" prop="match_count" label="匹配数" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.coverage_rate" prop="coverage_rate" label="覆盖率" :formatter="formatPercentage" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.display_count" prop="display_count" label="展示数" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.display_rate" prop="display_rate" label="展示率" :formatter="formatPercentage" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.click_count" prop="click_count" label="点击数" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.click_rate" prop="click_rate" label="点击率" :formatter="formatPercentage" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.viewability_rate" prop="viewability_rate" label="可见率" :formatter="formatPercentage" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.cpc" prop="cpc" label="CPC" :formatter="formatCurrency" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.pageviews" prop="pageviews" label="PageViews" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.ecpm_after_deduct" prop="ecpm_after_deduct" :label="isAdmin ? 'eCPM(扣)' : 'eCPM'" :formatter="formatCurrency" sortable="custom"></el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.ecpm_before_deduct" prop="ecpm_before_deduct" label="eCPM" :formatter="formatCurrency" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.revenue_after_deduct" prop="revenue_after_deduct" :label="isAdmin ? '收益(扣)' : '收益'" :formatter="formatCurrency" sortable="custom"></el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.revenue_before_deduct" prop="revenue_before_deduct" label="收益" :formatter="formatCurrency" sortable="custom"></el-table-column>
      </el-table>

      <!-- 分页控件 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.size"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          :layout="isMobile ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
          class="pagination-component"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        ></el-pagination>
      </div>
    </el-card>

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
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
import { useAuthStore } from '../../store';
import { ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem, ElSelect, ElOption, ElDatePicker, ElIcon, ElMessage, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus';
import { Download, InfoFilled, Setting, Right } from '@element-plus/icons-vue';
import { getDailySummary, exportAdData, getAdDataDateRange } from '../../api/ad-data';
import { useRouter } from 'vue-router';
import { extractErrorMessage, isErrorHandled } from '../../utils/api';
import { useDevice } from '../../composables/useDevice';
import { useAdDataTableFormat } from '../../composables/useAdDataTableFormat';
import {
  useAdDataColumnVisibility,
  createAdDataDefaultColumns,
  AD_DATA_SAVABLE_COLUMN_KEYS
} from '../../composables/useAdDataColumnVisibility';
import { useDataPageFilterCascade } from '../../composables/useDataPageFilterCascade';
import { useDebouncedPaginatedFetch } from '../../composables/useDebouncedPaginatedFetch';
import { useAdDataProductPanel } from '../../composables/useAdDataProductPanel';
import ProductManagementDialog from '../../components/admin/ProductManagementDialog.vue';

// 路由实例
const router = useRouter();

// 获取用户认证状态
const authStore = useAuthStore();
const isAdmin = computed(() => authStore.isAdmin);

// 设备检测
const { isMobile } = useDevice();

// 状态管理
const dailyDataList = ref([]);
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
  productId: ''
});

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility
} = useAdDataColumnVisibility(
  'dailyReport_columnVisibility',
  () => createAdDataDefaultColumns(() => isAdmin.value),
  AD_DATA_SAVABLE_COLUMN_KEYS
);

const { formatPercentage, formatCurrency, getSummaries } = useAdDataTableFormat({
  getIsAdmin: () => isAdmin.value,
  cpcSummaryMode: 'sum'
});

const {
  users,
  filterProducts,
  fetchClientsWithData,
  fetchFilterProducts,
  handleFilterClientChange,
  reloadFiltersAfterDateChange
} = useDataPageFilterCascade({ searchForm, includeCountry: false, source: 'ad-data' });

const { runFetch: fetchDailyData, cancel: cancelDailyFetch } = useDebouncedPaginatedFetch({
  loading,
  pagination,
  buildParams: () => {
    const params = {
      page: pagination.value.current,
      page_size: pagination.value.size
    };
    if (isAdmin.value && searchForm.value.clientId) {
      params.client_id = searchForm.value.clientId;
    }
    if (searchForm.value.productId) {
      params.product_id = searchForm.value.productId;
    }
    if (searchForm.value.dateRange?.length === 2) {
      params.start_date = searchForm.value.dateRange[0];
      params.end_date = searchForm.value.dateRange[1];
    }
    if (sortInfo.value.prop) {
      params.sort_by = sortInfo.value.prop;
      params.sort_order = sortInfo.value.order === 'ascending' ? 'asc' : 'desc';
    }
    return params;
  },
  fetchPage: (params) => getDailySummary(params),
  applyResponse: (response) => {
    dailyDataList.value = response.data || [];
    pagination.value.total =
      typeof response.total === 'number'
        ? response.total
        : parseInt(response.total || 0, 10);
  },
  checkAuth: () => authStore.isAuthenticated,
  onUnauthenticated: () => {
    ElMessage.warning('登录已过期，请重新登录');
    router.push('/login').catch(() => {
      window.location.href = '/login';
    });
  },
  afterEmpty: async (response) => {
    if (
      (response.data?.length ?? 0) > 0 ||
      pagination.value.total > 0 ||
      (searchForm.value.dateRange?.length ?? 0) > 0
    ) {
      return;
    }
    try {
      const clientId =
        isAdmin.value && searchForm.value.clientId ? searchForm.value.clientId : null;
      const dateRange = await getAdDataDateRange(clientId);
      if (dateRange?.min_date && dateRange?.max_date) {
        ElMessage.info({
          message: `当前月暂无数据。数据日期范围：${dateRange.min_date} 至 ${dateRange.max_date}，请选择对应的日期范围进行查询。`,
          duration: 10000,
          showClose: true
        });
      } else {
        ElMessage.warning({
          message:
            '当前月暂无数据。可能原因：1) 数据在其他月份，请选择日期范围查询；2) 产品未激活；3) 没有权限查看数据。',
          duration: 8000,
          showClose: true
        });
      }
    } catch {
      ElMessage.warning({
        message: '当前月暂无数据。如果数据在其他月份，请选择对应的日期范围进行查询。',
        duration: 6000,
        showClose: true
      });
    }
  }
});

const handleDateRangeChange = async () => {
  await reloadFiltersAfterDateChange(isAdmin.value);
  if (searchForm.value.productId) {
    const productExists = filterProducts.value.some(
      (p) => p.value === searchForm.value.productId
    );
    if (!productExists) {
      searchForm.value.productId = '';
    }
  }
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
    fetchDailyData();
  }
};

// 重置筛选条件
const resetFilter = async () => {
  searchForm.value = {
    clientId: '',
    dateRange: [],
    productId: ''
  };
  pagination.value.current = 1;
  // 重置排序
  sortInfo.value = {
    prop: 'date',
    order: 'descending'
  };
  
  if (isAdmin.value) {
    await fetchClientsWithData();
  }
  
  const defaultClientId = isAdmin.value ? null : null;
  await fetchFilterProducts(defaultClientId);
  
  fetchDailyData();
};

// 分页处理
const handleSizeChange = (size) => {
  pagination.value.size = size;
  pagination.value.current = 1;  // 分页大小变化时重置到第一页
  fetchDailyData();
};

const handlePageChange = (page) => {
  pagination.value.current = page;
  fetchDailyData();
};

// 导出数据
const handleExport = async () => {
  try {
    if (pagination.value.total === 0) {
      ElMessage.warning('当前没有可导出的数据，请先查询数据');
      return;
    }
    
    const params = {};
    
    if (isAdmin.value && searchForm.value.clientId) {
      params.client_id = parseInt(searchForm.value.clientId);
    }
    
    if (searchForm.value.productId) {
      params.product_id = parseInt(searchForm.value.productId);
    }

    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      params.start_date = searchForm.value.dateRange[0];
      params.end_date = searchForm.value.dateRange[1];
    }
    
    // 注意：导出功能暂时使用详细报表的导出，因为每日汇总的导出需要单独实现
    await exportAdData(params);
    ElMessage.success('导出成功');
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
  }
};

// 监听分页变化
let isInitializing = true;

watch(
  () => [pagination.value.current, pagination.value.size],
  ([newCurrent, newSize], [oldCurrent, oldSize]) => {
    if (isInitializing) {
      return;
    }
    
    if (oldCurrent === undefined || oldSize === undefined) {
      return;
    }
    
    if (newCurrent !== oldCurrent && newSize === oldSize) {
      fetchDailyData();
    } else if (newSize !== oldSize) {
      if (newCurrent !== 1) {
        pagination.value.current = 1;
      } else {
        fetchDailyData();
      }
    }
  },
  { flush: 'post' }
);

// 加载页面数据
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
    
    await fetchDailyData();
    
    if (isAdmin.value) {
      await fetchClientsWithData();
    }
    
    const defaultClientId = isAdmin.value ? null : null;
    await fetchFilterProducts(defaultClientId);
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(`页面初始化失败: ${errorMsg}`);
    }
  }
};

// 页面挂载时加载数据
onMounted(async () => {
  // 加载列显示设置
  loadColumnVisibility();
  await nextTick();
  setTimeout(async () => {
    await loadPageData();
    await nextTick();
    isInitializing = false;
  }, 0);
});

onUnmounted(() => {
  cancelDailyFetch();
});

const handleProductClick = (row) => {
  openProductPanel(row, {
    defaultClientId: authStore.userInfo?.id,
    defaultClientName: authStore.userInfo?.full_name || '未知客户'
  });
};

const handleProductManagementRefresh = () => {
  fetchDailyData();
};
</script>

<style scoped>
.daily-report-container {
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

.action-buttons {
  display: flex;
  gap: var(--spacing-md);
}

.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.filter-form {
  margin-bottom: 0;
}

.filter-form :deep(.el-form-item) {
  width: 300px;
  margin-bottom: var(--spacing-lg);
}

.filter-form :deep(.el-form-item:last-child) {
  width: auto;
}

.filter-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background-color: var(--primary-light);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  color: var(--primary-color);
  font-size: var(--font-size-sm);
}

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

/* 移动端优化 */
@media (max-width: 767px) {
  .daily-report-container {
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
  
  .filter-form {
    display: flex !important;
    flex-direction: column !important;
  }
  
  .filter-form :deep(.el-form--inline) {
    display: flex !important;
    flex-direction: column !important;
  }
  
  .filter-form :deep(.el-form-item) {
    width: 100% !important;
    margin-right: 0 !important;
    margin-bottom: var(--spacing-md) !important;
    display: flex !important;
    flex-direction: column !important;
  }
  
  .filter-form :deep(.el-form-item__label) {
    width: 100% !important;
    text-align: left !important;
    margin-bottom: var(--spacing-xs) !important;
    padding: 0 !important;
    margin-right: 0 !important;
    float: none !important;
    justify-content: flex-start !important;
    align-items: flex-start !important;
    display: block !important;
    font-weight: var(--font-weight-semibold);
    color: var(--text-primary);
  }
  
  .filter-form :deep(.el-form-item__content) {
    width: 100% !important;
    margin-left: 0 !important;
    flex: 1 !important;
  }
  
  .filter-form :deep(.el-input),
  .filter-form :deep(.el-select),
  .filter-form :deep(.el-date-editor),
  .filter-form :deep(.el-date-picker) {
    width: 100% !important;
    max-width: 100% !important;
  }
  
  .filter-form :deep(.el-input__wrapper) {
    min-height: var(--touch-target-size);
    width: 100% !important;
  }
  
  .filter-form :deep(.el-select .el-input__wrapper) {
    min-height: var(--touch-target-size);
    width: 100% !important;
  }
  
  .filter-form :deep(.el-date-editor.el-input__wrapper) {
    width: 100% !important;
    min-height: var(--touch-target-size);
  }
  
  /* 日期选择器特殊处理 */
  .filter-form :deep(.el-date-editor) {
    width: 100% !important;
  }
  
  .filter-form :deep(.el-date-editor .el-range-separator) {
    width: auto !important;
    padding: 0 var(--spacing-xs);
  }
  
  .filter-form :deep(.el-date-editor .el-range-input) {
    width: calc(50% - 20px) !important;
    flex: 1 !important;
  }
  
  /* 查询和重置按钮移动端优化 */
  .filter-form :deep(.el-form-item:last-child) {
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm);
    margin-top: var(--spacing-sm);
    margin-bottom: 0 !important;
    width: 100% !important;
  }
  
  .filter-form :deep(.el-form-item:last-child .el-form-item__label) {
    display: none !important;
  }
  
  .filter-form :deep(.el-form-item:last-child .el-form-item__content) {
    width: 100% !important;
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm);
    margin-left: 0 !important;
  }
  
  .filter-form :deep(.el-form-item:last-child .el-button) {
    flex: 1;
    min-height: var(--touch-target-size);
    width: auto;
    white-space: nowrap;
  }
  
  .filter-hint {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs) var(--spacing-sm);
    line-height: 1.5;
  }
  
  .pagination-container {
    text-align: center;
    padding: var(--spacing-md) 0;
  }
  
  /* 移动端表格卡片优化 - 支持横向滚动 */
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
  
  /* 确保表格列内容不换行，通过横向滚动查看完整内容 */
  .el-table :deep(.el-table__body td) {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  
  /* 文本列（产品名称、客户名称、国家）在移动端允许适当换行以节省空间 */
  .el-table :deep(.el-table__body tr td:nth-child(3)), /* 产品名称 */
  .el-table :deep(.el-table__body tr td:nth-child(4)) { /* 国家 */
    white-space: normal;
    word-break: break-word;
    max-width: 100px;
    min-width: 80px;
  }
  
  /* 管理员模式下，所属客户列也允许换行 */
  .el-table :deep(.el-table__body tr td:nth-child(2)) {
    white-space: normal;
    word-break: break-word;
    max-width: 100px;
    min-width: 80px;
  }
  
  .el-table :deep(.el-table__header-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .el-table :deep(.el-table__body-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
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

