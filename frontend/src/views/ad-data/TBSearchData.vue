<!--
  广告数据 - TB 搜索数据
  @file views/ad-data/TBSearchData.vue
-->
<template>
  <!-- 页面主模板 -->
<div class="ad-data-container">
    <div class="page-header">
      <div class="action-buttons">
        <el-upload
          v-if="isAdmin"
          class="upload-demo"
          :show-file-list="false"
          :http-request="handleImport"
          accept=".xlsx,.xls"
          :disabled="loading"
        >
          <el-button type="primary" :icon="Upload" :loading="importing" :disabled="loading">导入Excel</el-button>
        </el-upload>
        <el-button 
          v-if="isAdmin && selectedRows.length > 0" 
          type="danger" 
          @click="handleBatchDelete" 
          :icon="Delete"
          :disabled="loading"
        >
          批量删除 ({{ selectedRows.length }})
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
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            @change="handleDateRangeChange"
          ></el-date-picker>
        </el-form-item>
        <el-form-item v-if="isAdmin" label="客户">
          <el-select 
            v-model="searchForm.clientId" 
            placeholder="全部客户" 
            clearable
            @change="handleClientChange"
          >
            <el-option v-for="user in users" :key="user.value" :label="user.label" :value="user.value"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="产品">
          <ProductFilterSelect
            v-model="searchForm.productId"
            :options="products"
            placeholder="全部产品"
            @change="handleProductChange"
          />
        </el-form-item>
        <el-form-item label="国家">
          <el-select 
            v-model="searchForm.countryCode" 
            placeholder="全部区域" 
            clearable
            @change="fetchData"
            style="width: 100%;"
          >
            <el-option v-for="country in countries" :key="country.code" :label="country.label || country.name_zh" :value="country.code"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchData" :loading="loading">查询</el-button>
          <el-button @click="resetFilter" :disabled="loading">重置</el-button>
        </el-form-item>
      </el-form>
      <div v-if="showProductOwnershipLegend" class="filter-legend">
        <span class="filter-legend__label">产品标注：</span>
        <el-tag size="small" type="success">当前</el-tag>
        <span class="filter-legend__text">名下产品</span>
        <el-tag size="small" type="info">历史</el-tag>
        <span class="filter-legend__text">所选日期内曾归属、已转移</span>
        <el-tag size="small" type="warning">当前+历史</el-tag>
        <span class="filter-legend__text">两种口径均匹配</span>
      </div>
      <div v-if="showProductOwnershipLegend" class="filter-hint">
        {{ productOwnershipHint }}
      </div>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="data-table-card">
      <!-- 卡片标题栏 -->
    <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-weight: 600; font-size: 16px;">TB搜索数据</span>
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
        :data="tableData"
        border
        stripe
        style="width: 100%"
        @selection-change="handleSelectionChange"
        @sort-change="handleSortChange"
        :summary-method="getSummaries"
        show-summary
      >
        <el-table-column type="selection" width="55"></el-table-column>
        <el-table-column v-if="columnVisibility.date" prop="date" label="DATE" sortable="custom" width="120"></el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.user_name" prop="user_name" label="所属客户" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.product_name" prop="product_name" label="SUBID" sortable="custom">
          <template #default="{ row }">
            <div class="product-name-cell" @click="handleProductClick(row)">
              <span>{{ row.product_name }}</span>
              <el-icon class="arrow-icon"><Right /></el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.country_name_zh" prop="country_name_zh" label="GEO" width="120">
          <template #default="{ row }">
            {{ row.country_code }} ({{ row.country_name_zh }})
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.redirects" prop="redirects" label="REDIRECTS" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.searches" prop="searches" label="SEARCHES" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.monetized" prop="monetized" label="MONETIZED" sortable="custom"></el-table-column>
        <el-table-column v-if="columnVisibility.clicks" prop="clicks" label="CLICKS" sortable="custom"></el-table-column>
        
        <el-table-column v-if="columnVisibility.revenue" prop="revenue" :label="isAdmin ? 'REVENUE(扣)' : 'REVENUE'" sortable="custom">
          <template #default="{ row }">
            {{ formatCurrency(row.revenue) }}
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.revenue_before_deduct" prop="revenue_before_deduct" label="REVENUE" sortable="custom">
          <template #default="{ row }">
            {{ formatCurrency(row.revenue_before_deduct) }}
          </template>
        </el-table-column>

        <el-table-column v-if="columnVisibility.rpm" prop="rpm" :label="isAdmin ? 'RPM(扣)' : 'RPM'" sortable="custom">
          <template #default="{ row }">
            {{ formatCurrency(row.rpm) }}
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.rpm_before_deduct" prop="rpm_before_deduct" label="RPM" sortable="custom">
          <template #default="{ row }">
            {{ formatCurrency(row.rpm_before_deduct) }}
          </template>
        </el-table-column>

        <el-table-column v-if="isAdmin" label="操作" width="150" fixed="right">
          <template #default="scope">
            <el-button size="small" type="primary" @click="handleEdit(scope.row)">修改</el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.size"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        ></el-pagination>
      </div>
    </el-card>

    <!-- 编辑对话框 -->
    <el-dialog 
      v-model="editDialogVisible" 
      title="修改数据" 
      width="500px"
      :append-to-body="true"
    >
      <el-form :model="editForm" label-width="120px">
        <el-form-item label="REDIRECTS">
          <el-input v-model.number="editForm.redirects" type="number"></el-input>
        </el-form-item>
        <el-form-item label="SEARCHES">
          <el-input v-model.number="editForm.searches" type="number"></el-input>
        </el-form-item>
        <el-form-item label="MONETIZED">
          <el-input v-model.number="editForm.monetized" type="number"></el-input>
        </el-form-item>
        <el-form-item label="CLICKS">
          <el-input v-model.number="editForm.clicks" type="number"></el-input>
        </el-form-item>
        <el-form-item label="REVENUE(扣)">
          <el-input v-model.number="editForm.revenue" type="number" step="0.01"></el-input>
        </el-form-item>
        <el-form-item label="REVENUE">
          <el-input v-model.number="editForm.revenue_before_deduct" type="number" step="0.01"></el-input>
        </el-form-item>
        <el-form-item label="RPM(扣)">
          <el-input v-model.number="editForm.rpm" type="number" step="0.01"></el-input>
        </el-form-item>
        <el-form-item label="RPM">
          <el-input v-model.number="editForm.rpm_before_deduct" type="number" step="0.01"></el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="date" :disabled="true">DATE（固定显示）</el-checkbox>
        <el-checkbox v-if="isAdmin" label="user_name">所属客户</el-checkbox>
        <el-checkbox label="product_name" :disabled="true">SUBID（固定显示）</el-checkbox>
        <el-checkbox label="country_name_zh">GEO</el-checkbox>
        <el-checkbox label="redirects">REDIRECTS</el-checkbox>
        <el-checkbox label="searches">SEARCHES</el-checkbox>
        <el-checkbox label="monetized">MONETIZED</el-checkbox>
        <el-checkbox label="clicks">CLICKS</el-checkbox>
        <el-checkbox label="revenue">REVENUE(扣)</el-checkbox>
        <el-checkbox v-if="isAdmin" label="revenue_before_deduct">REVENUE</el-checkbox>
        <el-checkbox label="rpm">RPM(扣)</el-checkbox>
        <el-checkbox v-if="isAdmin" label="rpm_before_deduct">RPM</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>

    <!-- 产品管理对话框 -->
    <ProductManagementDialog
      v-model="productManagementDialogVisible"
      :client-id="selectedClientId"
      :client-name="selectedClientName"
      :products="selectedClientProducts"
      :loading="loadingProducts"
      @refresh="handleProductManagementRefresh"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import { useAuthStore } from '../../store';
import { ElMessage, ElMessageBox, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus';
import { Upload, Delete, Setting, Right } from '@element-plus/icons-vue';
import {
  getTBSearchDataList,
  updateTBSearchData,
  deleteTBSearchData,
  batchDeleteTBSearchData,
  importTBSearchData,
  getProductsWithTBSearchData
} from '../../api/tb-search-data';
import { getProductById } from '../../api/ad-data';
import { extractErrorMessage, isErrorHandled } from '../../utils/api';
import { useDataPageFilterCascade } from '../../composables/useDataPageFilterCascade';
import { useDebouncedPaginatedFetch } from '../../composables/useDebouncedPaginatedFetch';
import { useAdDataProductPanel } from '../../composables/useAdDataProductPanel';
import {
  useTbSearchColumnVisibility
} from '../../composables/useTbSearchColumnVisibility';
import { useTbSearchTableFormat } from '../../composables/useTbSearchTableFormat';
import ProductManagementDialog from '../../components/admin/ProductManagementDialog.vue';
import ProductFilterSelect from '../../components/ad-data/ProductFilterSelect.vue';
import {
  hasProductOwnershipLabels,
  PRODUCT_OWNERSHIP_HINT,
} from '../../utils/productFilterOptions';

const authStore = useAuthStore();
const isAdmin = computed(() => authStore.isAdmin);

const loading = ref(false);
const importing = ref(false);
const tableData = ref([]);
const selectedRows = ref([]);

const pagination = ref({
  current: 1,
  size: 10,
  total: 0
});

const searchForm = ref({
  dateRange: [],
  clientId: '',
  productId: '',
  countryCode: ''
});

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility
} = useTbSearchColumnVisibility(() => isAdmin.value);

const sortInfo = ref({
  prop: 'date',
  order: 'descending'
});

const editDialogVisible = ref(false);
const editForm = ref({});

const {
  productManagementVisible: productManagementDialogVisible,
  selectedClientId,
  selectedClientName,
  selectedClientProducts,
  loadingProducts,
  selectedProductId,
  selectedProductName,
  openProductPanel
} = useAdDataProductPanel({
  getProductById,
  fetchProductsForClient: (clientId) =>
    getProductsWithTBSearchData(clientId).then((r) => r?.data || [])
});

const {
  users,
  filterProducts: products,
  filterCountries: countries,
  handleFilterClientChange,
  handleFilterProductChange,
  reloadFiltersAfterDateChange,
  loadAllFilterOptions,
  pruneInvalidFilterSelections
} = useDataPageFilterCascade({
  searchForm,
  includeCountry: true,
  source: 'tb-search'
});

const showProductOwnershipLegend = computed(() =>
  hasProductOwnershipLabels(
    (products.value || []).filter((item) => item?.value !== '' && item?.value != null)
  )
);
const productOwnershipHint = PRODUCT_OWNERSHIP_HINT;

const { formatCurrency, getSummaries } = useTbSearchTableFormat();

const { runFetch: fetchData } = useDebouncedPaginatedFetch({
  loading,
  pagination,
  debounceMs: 0,
  buildParams: () => {
    const params = {
      page: pagination.value.current,
      page_size: pagination.value.size,
      sort_by: sortInfo.value.prop,
      sort_order: sortInfo.value.order === 'ascending' ? 'asc' : 'desc'
    };
    if (searchForm.value.dateRange?.length === 2) {
      params.start_date = searchForm.value.dateRange[0];
      params.end_date = searchForm.value.dateRange[1];
    }
    if (searchForm.value.clientId) params.client_id = searchForm.value.clientId;
    if (searchForm.value.productId) params.product_id = searchForm.value.productId;
    if (searchForm.value.countryCode) params.country_code = searchForm.value.countryCode;
    return params;
  },
  fetchPage: (params) => getTBSearchDataList(params),
  applyResponse: (response) => {
    tableData.value = response.data || [];
    pagination.value.total =
      typeof response.total === 'number'
        ? response.total
        : parseInt(response.total || 0, 10);
  }
});

const handleProductClick = (row) => {
  if (!row) return;
  openProductPanel(row, {
    defaultClientId: authStore.userInfo?.id,
    defaultClientName: authStore.userInfo?.full_name || '未知客户'
  });
};

const handleProductManagementRefresh = () => {
  fetchData();
};

onMounted(async () => {
  loadColumnVisibility();
  await loadAllFilterOptions(isAdmin.value);
  fetchData();
});

const syncFilterSelections = () => {
  pruneInvalidFilterSelections(isAdmin.value);
};

const handleDateRangeChange = async () => {
  await reloadFiltersAfterDateChange(isAdmin.value);
  pagination.value.current = 1;
  fetchData();
};

const handleClientChange = async () => {
  await handleFilterClientChange();
  syncFilterSelections();
  pagination.value.current = 1;
  fetchData();
};

const handleProductChange = async () => {
  await handleFilterProductChange();
  syncFilterSelections();
  pagination.value.current = 1;
  fetchData();
};

const handleSizeChange = (size) => {
  pagination.value.size = size;
  pagination.value.current = 1;
  fetchData();
};

const handlePageChange = (page) => {
  pagination.value.current = page;
  fetchData();
};

const handleSortChange = ({ prop, order }) => {
  sortInfo.value = { prop, order };
  fetchData();
};

const handleSelectionChange = (val) => {
  selectedRows.value = val;
};

const resetFilter = async () => {
  searchForm.value = {
    dateRange: [],
    clientId: '',
    productId: '',
    countryCode: ''
  };
  pagination.value.current = 1;
  await loadAllFilterOptions(isAdmin.value);
  fetchData();
};

const handleImport = async (options) => {
  const { file } = options;
  const formData = new FormData();
  formData.append('file', file);
  
  importing.value = true;
  try {
    const res = await importTBSearchData(formData);
    // 优先显示 data.message（后端业务消息），其次显示外层 message，最后是默认消息
    const msg = res.data?.message || res.message || '导入成功';
    ElMessage.success(msg);
    
    // 如果有部分错误，也显示出来
    if (res.data?.errors && res.data.errors.length > 0) {
      setTimeout(() => {
        const errorMsg = `部分数据导入失败（${res.data.errors.length}条）：\n` + res.data.errors.join('\n');
        ElMessage.warning({
          message: errorMsg,
          duration: 10000,
          showClose: true,
          dangerouslyUseHTMLString: true,
          formatter: (msg) => msg.replace(/\n/g, '<br/>')
        });
      }, 500);
    }
    
    // 导入成功后，重新加载筛选条件并刷新数据，确保能看到新导入的数据
    // 重置到第一页
    pagination.value.current = 1;
    
    // 如果用户没有选择日期范围，后端默认只显示当前月的数据
    // 为了确保能看到新导入的数据，如果当前没有选择日期范围，清除客户筛选
    // 这样至少能看到"默认客户（导入数据）"的数据
    if (!searchForm.value.dateRange || searchForm.value.dateRange.length === 0) {
      // 没有选择日期范围时，清除客户筛选，确保能看到所有客户的数据（包括默认客户）
      if (isAdmin.value) {
        searchForm.value.clientId = '';
      }
    }
    
    // 重新加载筛选条件（基于当前日期范围）
    await loadAllFilterOptions(isAdmin.value);
    
    // 刷新数据
    await fetchData();
    
    // 如果导入成功但数据没有显示，提示用户调整筛选条件
    if (res.data?.message && res.data.message.includes('成功导入')) {
      setTimeout(() => {
        if (tableData.value.length === 0 && pagination.value.total === 0) {
          ElMessage.info({
            message: '导入成功！如果看不到数据，请检查日期范围筛选条件是否包含导入数据的日期。',
            duration: 5000,
            showClose: true
          });
        }
      }, 1000);
    }
  } catch (error) {
    if (!isErrorHandled(error)) {
      ElMessage.error(extractErrorMessage(error));
    }
  } finally {
    importing.value = false;
  }
};

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该条数据?', '警告', { type: 'warning' });
    await deleteTBSearchData(row.id);
    ElMessage.success('删除成功');
    fetchData();
  } catch (e) {
    if (e !== 'cancel') {
      // 错误已处理
    }
  }
};

const handleBatchDelete = async () => {
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedRows.value.length} 条数据?`, '警告', { type: 'warning' });
    await batchDeleteTBSearchData(selectedRows.value.map(r => r.id));
    ElMessage.success('批量删除成功');
    selectedRows.value = [];
    fetchData();
  } catch (e) {
    if (e !== 'cancel') {
      // 错误已处理
    }
  }
};

const handleEdit = (row) => {
  editForm.value = { ...row };
  editDialogVisible.value = true;
};

const saveEdit = async () => {
  try {
    await updateTBSearchData(editForm.value);
    ElMessage.success('修改成功');
    editDialogVisible.value = false;
    fetchData();
  } catch (error) {
    // 错误已处理
  }
};
</script>

<style scoped>
.ad-data-container {
  padding: 20px;
}
.page-header {
  margin-bottom: 20px;
}
.filter-card {
  margin-bottom: 20px;
}

.filter-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  margin-top: 4px;
  font-size: 13px;
  color: #606266;
}

.filter-legend__label {
  color: #909399;
}

.filter-legend__text {
  margin-right: 4px;
}

.filter-hint {
  margin-top: 8px;
  font-size: 13px;
  color: #909399;
  line-height: 1.5;
}

/* 筛选表单样式优化 */
.filter-form {
  margin-bottom: 0;
}

.filter-form :deep(.el-form-item) {
  width: 300px;
  margin-bottom: 16px;
  margin-right: 16px;
  vertical-align: top;
  display: inline-flex;
  align-items: center;
}

/* 确保标签宽度一致 */
.filter-form :deep(.el-form-item__label) {
  width: auto;
  min-width: 60px;
  text-align: right;
  padding-right: 12px;
  line-height: 32px;
}

/* 确保内容区域对齐 */
.filter-form :deep(.el-form-item__content) {
  flex: 1;
  line-height: 32px;
}

/* 确保所有输入框和选择框宽度一致 */
.filter-form :deep(.el-input),
.filter-form :deep(.el-select),
.filter-form :deep(.el-date-editor) {
  width: 100%;
}

/* 确保输入框和选择框的高度一致 */
.filter-form :deep(.el-input__wrapper),
.filter-form :deep(.el-select .el-input__wrapper) {
  height: 32px;
  min-height: 32px;
}

/* 下拉框宽度优化 */
.filter-form :deep(.el-select) {
  min-width: 100%;
}

/* 日期选择器宽度优化 */
.filter-form :deep(.el-date-editor) {
  width: 100%;
}

/* 确保输入框内部元素对齐 */
.filter-form :deep(.el-input__inner) {
  height: 100%;
  line-height: 1;
}

/* 按钮组不限制宽度 */
.filter-form :deep(.el-form-item:last-child) {
  width: auto;
  margin-right: 0;
}

/* 响应式优化 */
@media (min-width: 1200px) {
  .filter-form :deep(.el-form-item) {
    width: 280px;
  }
}

@media (min-width: 1400px) {
  .filter-form :deep(.el-form-item) {
    width: 300px;
  }
}

/* 移动端优化 */
@media (max-width: 767px) {
  .filter-form :deep(.el-form-item) {
    width: 100% !important;
    margin-right: 0 !important;
  }
  
  .filter-form :deep(.el-input),
  .filter-form :deep(.el-select),
  .filter-form :deep(.el-date-editor) {
    width: 100% !important;
  }
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

/* 产品名称单元格样式 */
.product-name-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  padding: 4px 0;
  color: #409EFF;
  transition: color 0.3s;
}

.product-name-cell:hover {
  color: #66b1ff;
}

.product-name-cell:hover .arrow-icon {
  transform: translateX(4px);
}

.arrow-icon {
  font-size: 12px;
  transition: transform 0.3s;
}
</style>
