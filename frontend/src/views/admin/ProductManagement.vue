<!--
  管理端 - 产品管理（独立菜单页）
  @file views/admin/ProductManagement.vue
-->
<template>
  <div class="product-management-page">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Box /></el-icon>
            <span class="header-title">产品管理</span>
            <el-tag type="info" effect="plain" size="small" class="total-tag">
              共 {{ pagination.total }} 个产品
            </el-tag>
          </div>
          <div class="header-right">
            <el-button type="primary" :icon="Plus" @click="handleAddClick">添加产品</el-button>
          </div>
        </div>
      </template>

      <div class="search-bar">
        <el-input
          v-model="searchForm.name"
          placeholder="产品名称（前缀）"
          clearable
          style="width: 220px"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select
          v-model="searchForm.clientId"
          placeholder="所属客户"
          clearable
          filterable
          style="width: 240px; margin-left: 10px"
          @change="handleSearch"
        >
          <el-option
            v-for="opt in clientOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-select
          v-model="searchForm.isActive"
          placeholder="激活状态"
          clearable
          style="width: 140px; margin-left: 10px"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option label="活跃" :value="true" />
          <el-option label="禁用" :value="false" />
        </el-select>
        <el-button type="primary" :icon="Search" style="margin-left: 10px" @click="handleSearch">
          搜索
        </el-button>
        <el-button :icon="Refresh" @click="handleReset">重置</el-button>
      </div>

      <ProductTable
        :products="products"
        :loading="loading"
        :is-mobile="isMobile"
        :table-max-height="tableMaxHeight"
        :show-client="true"
        :client-label-map="clientLabelMap"
        @history="handleViewHistory"
        @edit="handleEditClick"
        @delete="handleDeleteClick"
      />

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          :layout="isMobile ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <ProductAssignmentHistoryDialog
      v-model="assignmentHistoryVisible"
      :product-id="selectedProductForHistory?.id"
      :product-name="selectedProductForHistory?.name"
    />

    <ProductFormDialog
      ref="formDialogRef"
      v-model="formDialogVisible"
      :form-title="formTitle"
      :is-mobile="isMobile"
      :form-data="formData"
      :form-rules="formRules"
      :saving="saving"
      :product-names="productNames"
      :product-names-loading="productNamesLoading"
      :query-product-names="queryProductNames"
      @save="handleSave"
      @product-name-select="handleProductNameSelect"
      @product-name-blur="handleProductNameBlur"
      @load-product-names="loadProductNames"
    />

    <ProductTransferDateDialog
      v-model="transferDateDialogVisible"
      :transfer-date-form="transferDateForm"
      :product-assignments="productAssignments"
      :loading-assignments="loadingAssignments"
      :last-client-start-date="lastClientStartDate"
      :old-client-end-date="oldClientEndDate"
      :client-name="formScope.clientName"
      @start-date-change="handleStartDateChange"
      @end-date-change="handleEndDateChange"
      @confirm="confirmTransferDate"
    />

    <el-dialog
      v-model="clientPickerVisible"
      title="选择所属客户"
      width="420px"
      append-to-body
      @closed="pendingClientId = null"
    >
      <p class="picker-hint">添加产品前请先指定归属客户。也可先在筛选项中选定客户后再点「添加产品」。</p>
      <el-select
        v-model="pendingClientId"
        placeholder="请选择客户"
        filterable
        style="width: 100%"
      >
        <el-option
          v-for="opt in clientOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <template #footer>
        <el-button @click="clientPickerVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmClientPicker">下一步</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { onBeforeRouteUpdate } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Box, Plus, Refresh, Search } from '@element-plus/icons-vue';
import ProductAssignmentHistoryDialog from '../../components/admin/ProductAssignmentHistoryDialog.vue';
import ProductFormDialog from '../../components/admin/ProductFormDialog.vue';
import ProductTable from '../../components/admin/ProductTable.vue';
import ProductTransferDateDialog from '../../components/admin/ProductTransferDateDialog.vue';
import { useDevice } from '../../composables/useDevice';
import { useProductManagement } from '../../composables/useProductManagement';
import '../../styles/product-management-dialog.css';

const { isMobile } = useDevice();

const tableMaxHeight = computed(() => {
  const viewportHeight = window.innerHeight || 800;
  if (isMobile.value) {
    return Math.max(240, viewportHeight - 280);
  }
  return Math.max(400, viewportHeight - 280);
});

const {
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
} = useProductManagement();

const {
  formDialogRef,
  formDialogVisible,
  formTitle,
  saving,
  formData,
  formRules,
  productNames,
  productNamesLoading,
  queryProductNames,
  transferDateDialogVisible,
  transferDateForm,
  productAssignments,
  loadingAssignments,
  lastClientStartDate,
  oldClientEndDate,
  handleSave,
  handleProductNameSelect,
  handleProductNameBlur,
  loadProductNames,
  handleStartDateChange,
  handleEndDateChange,
  confirmTransferDate,
} = productForm;

const assignmentHistoryVisible = ref(false);
const selectedProductForHistory = ref(null);

const handleViewHistory = (product) => {
  if (!product?.id) {
    ElMessage.warning('无法查看历史记录：产品信息不完整');
    return;
  }
  selectedProductForHistory.value = product;
  assignmentHistoryVisible.value = true;
};

onMounted(async () => {
  applyRouteQuery();
  await loadClientOptions();
  await fetchProducts();
});

/** 同页再次带 query 跳入时（如从广告数据点产品）重新应用筛选 */
onBeforeRouteUpdate(async (to, from) => {
  if (to.fullPath === from.fullPath) return;
  // 本页 search 也会 replace query，用 fullPath 差异过滤即可
  applyRouteQuery(to.query);
  pagination.page = 1;
  await fetchProducts();
});
</script>

<style scoped>
.product-management-page {
  padding: 0;
}

.page-card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon {
  font-size: 20px;
  color: var(--el-color-primary);
}

.header-title {
  font-size: 16px;
  font-weight: 600;
}

.total-tag {
  margin-left: 4px;
}

.search-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 16px;
  gap: 0;
}

.pagination-container {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.picker-hint {
  margin: 0 0 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}

@media (max-width: 768px) {
  .search-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .search-bar :deep(.el-input),
  .search-bar :deep(.el-select),
  .search-bar :deep(.el-button) {
    margin-left: 0 !important;
    margin-bottom: 8px;
    width: 100% !important;
  }
}
</style>
