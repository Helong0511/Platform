<!--
  转化总览报表页面（ConversionSummary.vue）

  功能区块：
  1. 筛选区：日期范围、平台、产品、客户等多维筛选
  2. 汇总表格：按维度聚合展示转化数与金额
  3. 列显隐：支持自定义表格列展示

  数据加载与格式化由 useConversionSummary.js 提供。
-->
<template>
  <!-- 页面主模板 -->
  <!-- 页面主模板 -->
<div class="conversion-summary">
    <el-card class="page-card">
      <!-- 卡片标题栏 -->
    <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><DataAnalysis /></el-icon>
            <span class="header-title">转化总览</span>
          </div>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          class="filter-date-picker"
          @change="handleDateChange"
        />
        <el-select
          v-if="isAdmin"
          v-model="filterAdvertiser"
          placeholder="请选择广告主（可选）"
          clearable
          filterable
          class="filter-select"
          @change="handleAdvertiserChange"
        >
          <el-option
            v-for="adv in advertiserList"
            :key="adv.id"
            :label="adv.advertiser_name"
            :value="adv.id"
          />
        </el-select>
        <el-select
          v-model="filterOffer"
          placeholder="请选择Offer（可选）"
          clearable
          filterable
          class="filter-select"
          @change="handleOfferChange"
        >
          <el-option
            v-for="offer in offerList"
            :key="offer.id"
            :label="`${offer.id} - ${offer.offer_name}`"
            :value="offer.id"
          />
        </el-select>
        <el-select
          v-if="isAdmin"
          v-model="filterPublisher"
          placeholder="请选择渠道（可选）"
          clearable
          filterable
          class="filter-select"
          @change="handlePublisherChange"
        >
          <el-option
            v-for="pub in publisherList"
            :key="pub.id"
            :label="pub.publisher_name"
            :value="pub.id"
          />
        </el-select>
        <el-button type="primary" :icon="Search" @click="handleSearch" class="filter-button">查询</el-button>
        <el-button :icon="Refresh" @click="handleReset" class="filter-button">重置</el-button>
      </div>

      <!-- 统计卡片 -->
      <div class="stats-cards" v-loading="loading">
        <el-card class="stat-card">
          <el-statistic title="总点击" :value="summaryData.total_clicks || 0">
            <template #prefix>
              <el-icon :size="20"><Mouse /></el-icon>
            </template>
          </el-statistic>
        </el-card>
        <el-card class="stat-card">
          <el-statistic :title="isAdmin ? '总转化' : '转化数'" :value="displayConversion(summaryData.total_conversions, summaryData.conversion_cap)">
            <template #prefix>
              <el-icon :size="20"><Check /></el-icon>
            </template>
          </el-statistic>
        </el-card>
        <el-card class="stat-card">
          <el-statistic title="转化率 (CR)" :value="summaryData.cr || 0" suffix="%">
            <template #prefix>
              <el-icon :size="20"><TrendCharts /></el-icon>
            </template>
          </el-statistic>
        </el-card>
        <el-card v-if="isAdmin" class="stat-card">
          <el-statistic title="Revenue" :value="summaryData.total_po || 0" :precision="2">
            <template #prefix>
              <el-icon :size="20"><Money /></el-icon>
            </template>
          </el-statistic>
        </el-card>
        <el-card class="stat-card">
          <el-statistic title="Pub Revenue" :value="summaryData.total_po_after_discount || 0" :precision="2">
            <template #prefix>
              <el-icon :size="20"><Money /></el-icon>
            </template>
          </el-statistic>
        </el-card>
        <el-card v-if="isAdmin" class="stat-card">
          <el-statistic title="Profit" :value="summaryData.total_profit || 0" :precision="2">
            <template #prefix>
              <el-icon :size="20"><Money /></el-icon>
            </template>
          </el-statistic>
        </el-card>
      </div>

      <!-- Offer统计表格 -->
      <el-card class="table-card" style="margin-top: 20px;">
        <template #header>
          <div class="table-header">
            <span>转化总览</span>
            <div style="float: right; display: flex; gap: 10px;">
              <el-button 
                type="text" 
                :icon="Download" 
                @click="exportToExcel"
              >
                导出Excel
              </el-button>
              <el-button 
                type="text" 
                :icon="Setting" 
                @click="columnSettingVisible = true"
              >
                列设置
              </el-button>
            </div>
          </div>
        </template>
        <div class="table-wrapper">
          <el-table
            :data="statsList"
            stripe
            style="width: 100%;"
            show-summary
            :summary-method="getSummaries"
          >
            <el-table-column 
              v-if="columnVisibility.offer_id" 
              prop="offer_id" 
              label="Offer ID" 
              width="100" 
              align="right" 
              fixed="left"
            >
              <template #default="scope">
                <el-link
                  v-if="scope.row.offer_id"
                  type="primary"
                  :underline="false"
                  @click="handleOfferClick(scope.row.offer_id)"
                  style="cursor: pointer;"
                >
                  {{ scope.row.offer_id }}
                </el-link>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="columnVisibility.offer_name" 
              prop="offer_name" 
              label="Offer Name" 
              min-width="250" 
              show-overflow-tooltip 
              fixed="left"
            >
              <template #default="scope">
                <el-link
                  v-if="scope.row.offer_name"
                  type="primary"
                  :underline="false"
                  @click="handleOfferClick(scope.row.offer_id)"
                  style="cursor: pointer;"
                >
                  {{ scope.row.offer_name }}
                </el-link>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="isAdmin && columnVisibility.advertiser_name"
              prop="advertiser_name" 
              label="Advertiser" 
              min-width="100"
              show-overflow-tooltip
            />
            <el-table-column 
              v-if="columnVisibility.publisher_name"
              prop="publisher_name" 
              label="Publisher" 
              min-width="100" 
              show-overflow-tooltip 
            />
            <el-table-column 
              v-if="columnVisibility.click_count" 
              prop="click_count" 
              label="Click" 
              width="120" 
              align="right" 
            />
            <el-table-column 
              v-if="columnVisibility.conversion_count" 
              prop="conversion_count" 
              label="Conversion" 
              width="120" 
              align="right" 
            >
              <template #default="scope">
                {{ scope.row.conversion_count }}
              </template>
            </el-table-column>
            <el-table-column 
              v-if="columnVisibility.cr" 
              prop="cr" 
              label="CR" 
              width="120" 
              align="right"
            >
              <template #default="scope">
                {{ scope.row.cr }}%
              </template>
            </el-table-column>
            <el-table-column 
              v-if="isAdmin && columnVisibility.po"
              prop="po" 
              label="Revenue" 
              width="150" 
              align="right"
            >
              <template #default="scope">
                <span v-if="scope.row.po !== undefined && scope.row.po !== null">{{ scope.row.po.toFixed(2) }}</span>
                <span v-else>0.00</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="columnVisibility.po_after_discount"
              prop="po_after_discount" 
              label="Pub Revenue" 
              width="150" 
              align="right"
            >
              <template #default="scope">
                <span v-if="scope.row.po_after_discount !== undefined && scope.row.po_after_discount !== null">
                  {{ scope.row.po_after_discount.toFixed(2) }}
                </span>
                <span v-else>0.00</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="isAdmin && columnVisibility.profit"
              prop="profit" 
              label="Profit" 
              width="150" 
              align="right"
            >
              <template #default="scope">
                <span v-if="scope.row.po !== undefined && scope.row.po !== null && scope.row.po_after_discount !== undefined && scope.row.po_after_discount !== null">
                  {{ (scope.row.po - scope.row.po_after_discount).toFixed(2) }}
                </span>
                <span v-else>0.00</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="isAdmin && columnVisibility.adv_po"
              prop="adv_po" 
              label="上游单价" 
              width="120" 
              align="right"
            >
              <template #default="scope">
                <span v-if="scope.row.adv_po !== undefined && scope.row.adv_po !== null">{{ scope.row.adv_po.toFixed(2) }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="columnVisibility.pub_po"
              prop="pub_po" 
              label="下游单价" 
              width="120" 
              align="right"
            >
              <template #default="scope">
                <span v-if="scope.row.pub_po !== undefined && scope.row.pub_po !== null">{{ scope.row.pub_po.toFixed(2) }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="columnVisibility.geo"
              prop="geo" 
              label="GEO" 
              width="120" 
              align="center"
            >
              <template #default="scope">
                <span v-if="scope.row.geo">{{ scope.row.geo }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>
    </el-card>

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="offer_id" :disabled="true">Offer ID（固定显示）</el-checkbox>
        <el-checkbox label="offer_name" :disabled="true">Offer Name（固定显示）</el-checkbox>
        <el-checkbox v-if="isAdmin" label="advertiser_name">Advertiser</el-checkbox>
        <el-checkbox label="publisher_name">Publisher</el-checkbox>
        <el-checkbox label="click_count">Click</el-checkbox>
        <el-checkbox label="conversion_count">Conversion</el-checkbox>
        <el-checkbox label="cr">CR</el-checkbox>
        <el-checkbox v-if="isAdmin" label="po">Revenue</el-checkbox>
        <el-checkbox label="po_after_discount">Pub Revenue</el-checkbox>
        <el-checkbox v-if="isAdmin" label="profit">Profit</el-checkbox>
        <el-checkbox v-if="isAdmin" label="adv_po">上游单价</el-checkbox>
        <el-checkbox label="pub_po">下游单价</el-checkbox>
        <el-checkbox label="geo">GEO</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, computed } from 'vue'
import { ElCheckboxGroup, ElCheckbox } from 'element-plus'
import { Search, Refresh, DataAnalysis, Mouse, Check, TrendCharts, Money, Setting, Download } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store'
import { useConversionSummary } from '@/composables/useConversionSummary'
import { useConversionSummaryColumnVisibility } from '@/composables/useConversionSummaryColumnVisibility'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin)

const {
  loading,
  dateRange,
  filterOffer,
  filterAdvertiser,
  filterPublisher,
  offerList,
  advertiserList,
  publisherList,
  summaryData,
  statsList,
  handleDateChange,
  handleAdvertiserChange,
  handleOfferChange,
  handlePublisherChange,
  handleSearch,
  handleReset,
  handleOfferClick,
  exportToExcel,
  getSummaries,
  displayConversion,
  initPage,
} = useConversionSummary(isAdmin)

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility,
} = useConversionSummaryColumnVisibility(isAdmin)

onMounted(() => {
  loadColumnVisibility()
  initPage()
})
</script>

<style scoped>
.conversion-summary {
  padding: 20px;
}

.page-card {
  min-height: calc(100vh - 100px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-icon {
  font-size: 20px;
  color: #409eff;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}

.filter-bar {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 10px;
}

/* 日期选择器宽度 */
.filter-date-picker {
  width: 100px !important;
}

/* 筛选下拉框统一宽度 */
.filter-select {
  width: 250px !important;
}

/* 按钮样式 */
.filter-button {
  margin-left: 0 !important;
}

/* 确保输入框和下拉框文字不被遮盖 */
.filter-bar :deep(.el-input__wrapper) {
  padding-right: 30px; /* 为清除按钮留出空间 */
}

.filter-bar :deep(.el-select .el-input__wrapper) {
  padding-right: 30px; /* 为清除按钮和下拉箭头留出空间 */
}

.filter-bar :deep(.el-input__inner),
.filter-bar :deep(.el-select__input) {
  padding-right: 8px; /* 文字与清除按钮之间的间距 */
  text-overflow: ellipsis;
  overflow: hidden;
  white-space: nowrap;
}

/* 确保清除按钮不遮挡文字 */
.filter-bar :deep(.el-input__suffix) {
  right: 8px;
}

.filter-bar :deep(.el-select .el-input__suffix) {
  right: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 日期选择器特殊处理 */
.filter-date-picker :deep(.el-input__wrapper) {
  padding-right: 30px;
}

.filter-date-picker :deep(.el-input__inner) {
  padding-right: 8px;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
}

.conversion-cap {
  font-size: 14px;
  color: #606266;
  margin-left: 4px;
}

.table-card {
  margin-top: 20px;
}

.table-card :deep(.el-card__body) {
  padding: 20px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.table-wrapper {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.table-wrapper :deep(.el-table) {
  min-width: 1000px;
}

.table-wrapper :deep(.el-table__header-wrapper),
.table-wrapper :deep(.el-table__body-wrapper) {
  overflow-x: visible;
}

.table-header {
  font-weight: 600;
  font-size: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .conversion-summary {
    padding: 10px;
  }

  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-bar > * {
    width: 100% !important;
    margin-left: 0 !important;
  }

  .stats-cards {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .table-card :deep(.el-card__body) {
    padding: 10px;
  }

  .table-wrapper :deep(.el-table) {
    min-width: 900px;
    font-size: 12px;
  }

.table-wrapper :deep(.el-table__cell) {
  padding: 8px 4px;
}

/* 汇总行样式 */
.table-wrapper :deep(.el-table__footer-wrapper) {
  font-weight: 600;
}

.table-wrapper :deep(.el-table__footer) {
  background-color: #f5f7fa;
}

.table-wrapper :deep(.el-table__footer .el-table__cell) {
  background-color: #f5f7fa;
  font-weight: 600;
  color: #303133;
}
}
</style>
