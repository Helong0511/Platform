<template>
  <div class="daily-report-container">
    <div class="page-header">
      <div class="action-buttons">
        <el-button type="primary" @click="handleExport" :icon="Download">
          导出数据
        </el-button>
      </div>
    </div>

    <!-- 筛选控件 -->
    <el-card class="filter-card">
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="日期范围">
          <el-date-picker
            v-model="searchForm.dateRange"
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
            placeholder="全部产品" 
            style="width: 100%;"
            clearable
          >
            <el-option v-for="product in filterProducts" :key="product.value" :label="product.label" :value="product.value"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchDailyData">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
      <div class="filter-hint">
        <el-icon :size="16"><InfoFilled /></el-icon>
        <span>每日报表显示按产品每日汇总的数据，国家统一显示"全部区域"。默认查询本月数据。</span>
      </div>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="data-table-card">
      <el-table
        v-loading="loading"
        :data="dailyDataList"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="date" label="数据日期"></el-table-column>
        <el-table-column v-if="isAdmin" prop="user_name" label="所属客户"></el-table-column>
        <el-table-column prop="product_name" label="产品名称"></el-table-column>
        <el-table-column prop="country_name_zh" label="国家"></el-table-column>
        <el-table-column prop="request_count" label="请求数"></el-table-column>
        <el-table-column prop="match_count" label="匹配数"></el-table-column>
        <el-table-column prop="coverage_rate" label="覆盖率" :formatter="formatPercentage"></el-table-column>
        <el-table-column prop="display_count" label="展示数"></el-table-column>
        <el-table-column prop="display_rate" label="展示率" :formatter="formatPercentage"></el-table-column>
        <el-table-column prop="click_count" label="点击数"></el-table-column>
        <el-table-column prop="click_rate" label="点击率" :formatter="formatPercentage"></el-table-column>
        <el-table-column prop="ecpm_after_deduct" :label="isAdmin ? 'eCPM(扣)' : 'eCPM'" :formatter="formatCurrency"></el-table-column>
        <el-table-column v-if="isAdmin" prop="ecpm_before_deduct" label="eCPM" :formatter="formatCurrency"></el-table-column>
        <el-table-column prop="revenue_after_deduct" :label="isAdmin ? '收益(扣)' : '收益'" :formatter="formatCurrency"></el-table-column>
        <el-table-column v-if="isAdmin" prop="revenue_before_deduct" label="收益" :formatter="formatCurrency"></el-table-column>
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
        ></el-pagination>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch, nextTick } from 'vue';
import { useAuthStore } from '../../store';
import { ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem, ElSelect, ElOption, ElDatePicker, ElIcon, ElMessage } from 'element-plus';
import { Download, InfoFilled } from '@element-plus/icons-vue';
import { getDailySummary, exportAdData, getClientsWithData, getProductsWithData } from '../../api/adData';
import { useRouter } from 'vue-router';
import { extractErrorMessage, isErrorHandled } from '../../utils/api';
import { useDevice } from '../../composables/useDevice';

// 路由实例
const router = useRouter();

// 获取用户认证状态
const authStore = useAuthStore();
const isAdmin = computed(() => authStore.isAdmin);

// 设备检测
const { isMobile } = useDevice();

// 状态管理
const dailyDataList = ref([]);
const filterProducts = ref([{ label: '全部产品', value: '' }]);
const users = ref([]);
const loading = ref(false);
const pagination = ref({
  current: 1,
  size: 10,
  total: 0
});

// 筛选表单
const searchForm = ref({
  clientId: '',
  dateRange: [],
  productId: ''
});

// 格式化百分比
const formatPercentage = (row, column, value) => {
  const numValue = Number(value);
  if (isNaN(numValue)) {
    return '0.00%';
  }
  return `${numValue.toFixed(2)}%`;
};

// 格式化货币
const formatCurrency = (row, column, value) => {
  const numValue = Number(value);
  if (isNaN(numValue)) {
    return '$0.00';
  }
  return `$${numValue.toFixed(2)}`;
};

// 获取每日汇总数据
const fetchDailyData = async () => {
  try {
    loading.value = true;
    
    const token = sessionStorage.getItem('token');
    if (!token) {
      ElMessage.warning('登录已过期，请重新登录');
      router.push('/login').catch(() => {
        window.location.href = '/login';
      });
      return;
    }
    
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

    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      params.start_date = searchForm.value.dateRange[0];
      params.end_date = searchForm.value.dateRange[1];
    }

    const response = await getDailySummary(params);
    
    if (response.code !== 200) {
      const errorMsg = response.detail || response.message || '获取数据失败';
      ElMessage.error(errorMsg);
      dailyDataList.value = [];
      pagination.value.total = 0;
      return;
    }
    
    const listResponse = response.data || {};
    dailyDataList.value = listResponse.data || [];
    pagination.value.total = listResponse.total || 0;
  } catch (error) {
    if (error.response?.status === 401) {
      loading.value = false;
      return;
    }
    
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
  } finally {
    loading.value = false;
  }
};

// 获取有数据的客户列表
const fetchClientsWithData = async () => {
  try {
    let startDate = null;
    let endDate = null;
    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      startDate = searchForm.value.dateRange[0];
      endDate = searchForm.value.dateRange[1];
    }
    
    const result = await getClientsWithData(startDate, endDate);
    const data = result.data || [];
    users.value = [
      { label: '全部客户', value: '' },
      ...data
        .filter(item => item && item.id != null)
        .map(item => ({
          label: item.full_name || '未知客户',
          value: item.id
        }))
    ];
  } catch (error) {
    users.value = [{ label: '全部客户', value: '' }];
  }
};

// 获取筛选表单的产品列表
const fetchFilterProducts = async (clientId) => {
  try {
    let startDate = null;
    let endDate = null;
    if (searchForm.value.dateRange && searchForm.value.dateRange.length === 2) {
      startDate = searchForm.value.dateRange[0];
      endDate = searchForm.value.dateRange[1];
    }
    
    const result = await getProductsWithData(clientId || null, startDate, endDate);
    const data = result.data || [];
    
    const productOptions = data
      .filter(item => item && item.id != null)
      .map(item => ({
        label: item.name || '未知产品',
        value: String(item.id),
        id: item.id
      }))
      .sort((a, b) => Number(b.id) - Number(a.id));
    
    filterProducts.value = [
      { label: '全部产品', value: '' },
      ...productOptions
    ];
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
    filterProducts.value = [{ label: '全部产品', value: '' }];
  }
};

// 客户选择变化时的处理函数
const handleFilterClientChange = async (clientId) => {
  searchForm.value.productId = '';
  await fetchFilterProducts(clientId || null);
};

// 日期范围变化时的处理函数
const handleDateRangeChange = async () => {
  if (isAdmin.value) {
    await fetchClientsWithData();
  }
  
  const clientId = searchForm.value.clientId || null;
  await fetchFilterProducts(clientId);
  
  if (searchForm.value.productId) {
    const productExists = filterProducts.value.some(p => p.value === searchForm.value.productId);
    if (!productExists) {
      searchForm.value.productId = '';
    }
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
  
  if (isAdmin.value) {
    await fetchClientsWithData();
  }
  
  const defaultClientId = isAdmin.value ? null : null;
  await fetchFilterProducts(defaultClientId);
  
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
    const token = sessionStorage.getItem('token');
    if (!token || !authStore.isAuthenticated) {
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
  await nextTick();
  setTimeout(async () => {
    await loadPageData();
    await nextTick();
    isInitializing = false;
  }, 0);
});
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
</style>

