<!--
  广告数据详细报表 - 表格与分页
  @file components/ad-data/AdDataDetailTable.vue
-->
<template>
  <el-card class="data-table-card">
    <template #header>
      <div class="table-card-header">
        <span class="table-title">详细报表数据</span>
        <el-button type="text" :icon="Setting" @click="emit('open-column-settings')">
          列设置
        </el-button>
      </div>
    </template>
    <el-table
      v-loading="loading"
      :data="adDataList"
      border
      stripe
      style="width: 100%"
      :summary-method="getSummaries"
      show-summary
      @selection-change="(rows) => emit('selection-change', rows)"
      @sort-change="(payload) => emit('sort-change', payload)"
    >
      <el-table-column type="selection" width="55" />
      <el-table-column v-if="columnVisibility.date" prop="date" label="数据日期" sortable="custom" />
      <el-table-column
        v-if="isAdmin && columnVisibility.user_name"
        prop="user_name"
        label="所属客户"
      />
      <el-table-column
        v-if="columnVisibility.product_name"
        prop="product_name"
        label="产品名称"
        sortable="custom"
        sort-by="product"
        :min-width="150"
      >
        <template #default="{ row }">
          <div class="product-name-cell" @click="emit('product-click', row)">
            <span class="product-name">{{ row.product_name }}</span>
            <el-icon class="product-icon"><Right /></el-icon>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        v-if="columnVisibility.ad_unit"
        prop="ad_unit"
        label="广告单元"
        :min-width="120"
        show-overflow-tooltip
      />
      <el-table-column v-if="columnVisibility.country_name_zh" prop="country_name_zh" label="国家" />
      <el-table-column v-if="columnVisibility.request_count" prop="request_count" label="请求数" sortable="custom" />
      <el-table-column v-if="columnVisibility.match_count" prop="match_count" label="匹配数" sortable="custom" />
      <el-table-column
        v-if="columnVisibility.coverage_rate"
        prop="coverage_rate"
        label="覆盖率"
        :formatter="formatPercentage"
        sortable="custom"
      />
      <el-table-column v-if="columnVisibility.display_count" prop="display_count" label="展示数" sortable="custom" />
      <el-table-column
        v-if="columnVisibility.display_rate"
        prop="display_rate"
        label="展示率"
        :formatter="formatPercentage"
        sortable="custom"
      />
      <el-table-column v-if="columnVisibility.click_count" prop="click_count" label="点击数" sortable="custom" />
      <el-table-column
        v-if="columnVisibility.click_rate"
        prop="click_rate"
        label="点击率"
        :formatter="formatPercentage"
        sortable="custom"
      />
      <el-table-column
        v-if="columnVisibility.viewability_rate"
        prop="viewability_rate"
        label="可见率"
        :formatter="formatPercentage"
        sortable="custom"
      />
      <el-table-column
        v-if="columnVisibility.cpc"
        prop="cpc"
        label="CPC"
        :formatter="formatCurrency"
        sortable="custom"
      />
      <el-table-column v-if="columnVisibility.pageviews" prop="pageviews" label="PageViews" sortable="custom" />
      <el-table-column
        v-if="columnVisibility.ecpm_after_deduct"
        prop="ecpm_after_deduct"
        :label="isAdmin ? 'eCPM(扣)' : 'eCPM'"
        :formatter="formatCurrency"
        sortable="custom"
      />
      <el-table-column
        v-if="isAdmin && columnVisibility.ecpm_before_deduct"
        prop="ecpm_before_deduct"
        label="eCPM"
        :formatter="formatCurrency"
        sortable="custom"
      />
      <el-table-column
        v-if="columnVisibility.revenue_after_deduct"
        prop="revenue_after_deduct"
        :label="isAdmin ? '收益(扣)' : '收益'"
        :formatter="formatCurrency"
        sortable="custom"
      />
      <el-table-column
        v-if="isAdmin && columnVisibility.revenue_before_deduct"
        prop="revenue_before_deduct"
        label="收益"
        :formatter="formatCurrency"
        sortable="custom"
      />
      <el-table-column v-if="isAdmin" label="操作" width="180">
        <template #default="scope">
          <el-button size="small" type="primary" @click="emit('edit', scope.row)">修改</el-button>
          <el-button size="small" type="danger" @click="emit('delete', scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="pagination-container">
      <el-pagination
        v-model:current-page="paginationModel.current"
        v-model:page-size="paginationModel.size"
        :page-sizes="[10, 20, 50, 100]"
        :total="pagination.total"
        :layout="isMobile ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
        class="pagination-component"
      />
    </div>
  </el-card>
</template>

<script setup>
import { Setting, Right } from '@element-plus/icons-vue';

const paginationModel = defineModel('pagination', { type: Object, required: true });

defineProps({
  loading: { type: Boolean, default: false },
  adDataList: { type: Array, default: () => [] },
  columnVisibility: { type: Object, required: true },
  isAdmin: { type: Boolean, default: false },
  isMobile: { type: Boolean, default: false },
  formatPercentage: { type: Function, required: true },
  formatCurrency: { type: Function, required: true },
  getSummaries: { type: Function, required: true },
});

const emit = defineEmits([
  'selection-change',
  'sort-change',
  'edit',
  'delete',
  'product-click',
  'open-column-settings',
]);
</script>

<style scoped>
.table-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-title {
  font-weight: 600;
  font-size: 16px;
}

.pagination-container {
  margin-top: 16px;
  text-align: right;
}

.product-name-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.product-name-cell:hover {
  color: var(--el-color-primary);
}

.product-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
