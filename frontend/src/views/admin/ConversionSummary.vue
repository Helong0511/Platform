<template>
  <div class="conversion-summary">
    <el-card class="page-card">
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
          style="width: 250px;"
          @change="handleDateChange"
        />
        <el-select
          v-model="filterOffer"
          placeholder="Offer"
          clearable
          filterable
          style="width: 200px; margin-left: 10px;"
          @change="handleSearch"
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
          v-model="filterAdvertiser"
          placeholder="广告主"
          clearable
          filterable
          style="width: 200px; margin-left: 10px;"
          @change="handleSearch"
        >
          <el-option
            v-for="adv in advertiserList"
            :key="adv.id"
            :label="adv.advertiser_name"
            :value="adv.id"
          />
        </el-select>
        <el-select
          v-if="isAdmin"
          v-model="filterPublisher"
          placeholder="渠道"
          clearable
          filterable
          style="width: 200px; margin-left: 10px;"
          @change="handleSearch"
        >
          <el-option
            v-for="pub in publisherList"
            :key="pub.id"
            :label="pub.publisher_name"
            :value="pub.id"
          />
        </el-select>
        <el-button type="primary" :icon="Search" @click="handleSearch" style="margin-left: 10px;">查询</el-button>
        <el-button :icon="Refresh" @click="handleReset">重置</el-button>
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
          <el-statistic title="总转化" :value="summaryData.total_conversions || 0">
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
        <el-card class="stat-card">
          <el-statistic :title="isAdmin ? 'Revenue' : 'Pub Revenue'" :value="summaryData.total_po || 0" :precision="2">
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
          </div>
        </template>
        <div class="table-wrapper">
          <el-table
            :data="statsList"
            stripe
            style="width: 100%;"
          >
            <el-table-column prop="offer_id" label="Offer ID" width="100" align="right" fixed="left">
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
            <el-table-column prop="offer_name" label="Offer Name" min-width="200" show-overflow-tooltip fixed="left">
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
              v-if="isAdmin"
              prop="advertiser_name" 
              label="Advertiser" 
              min-width="150"
              show-overflow-tooltip
            />
            <el-table-column 
              v-if="isAdmin"
              prop="publisher_name" 
              label="Publisher" 
              min-width="150" 
              show-overflow-tooltip 
            />
            <el-table-column prop="click_count" label="Click" width="120" align="right" />
            <el-table-column prop="conversion_count" label="Conversion" width="120" align="right" />
            <el-table-column prop="cr" label="CR" width="120" align="right">
              <template #default="scope">
                {{ scope.row.cr }}%
              </template>
            </el-table-column>
            <el-table-column 
              v-if="!isAdmin"
              prop="revenue" 
              label="收益" 
              width="150" 
              align="right"
            >
              <template #default="scope">
                <span v-if="scope.row.revenue !== undefined && scope.row.revenue !== null">
                  {{ scope.row.revenue.toFixed(2) }}
                </span>
                <span v-else>0.00</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="isAdmin"
              prop="po" 
              label="PO" 
              width="150" 
              align="right"
            >
              <template #default="scope">
                <span v-if="scope.row.po !== undefined && scope.row.po !== null">{{ scope.row.po.toFixed(2) }}</span>
                <span v-else>0.00</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="isAdmin"
              prop="po_after_discount" 
              label="PO(扣)" 
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
          </el-table>
        </div>
      </el-card>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh, DataAnalysis, Mouse, Check, TrendCharts, Money } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { getConversionSummary } from '@/api/conversionSummary'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'
import { getAdvertisers } from '@/api/advertiser'
import { logger } from '@/utils/logger'
import { useAuthStore } from '@/store'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin)
const router = useRouter()

const loading = ref(false)
const dateRange = ref([])
const filterOffer = ref(null)
const filterAdvertiser = ref(null)
const filterPublisher = ref(null)

const offerList = ref([])
const advertiserList = ref([])
const publisherList = ref([])

const summaryData = reactive({
  total_clicks: 0,
  total_conversions: 0,
  cr: 0,
  total_po: 0,
  stats_list: []
})

const statsList = ref([])

// 加载基础数据
const loadOffers = async () => {
  try {
    const response = await getOffers({ page: 1, page_size: 100 })
    // response已经是标准格式，直接使用data字段
    if (response && response.data) {
      offerList.value = (response.data || []).slice().sort((a, b) => a.id - b.id)
    }
  } catch (error) {
    logger.error('加载Offer列表失败:', error)
  }
}

const loadAdvertisers = async () => {
  try {
    const response = await getAdvertisers({ page: 1, page_size: 100 })
    // response已经是标准格式，直接使用data字段
    if (response && response.data) {
      advertiserList.value = response.data || []
    }
  } catch (error) {
    logger.error('加载广告主列表失败:', error)
  }
}

const loadPublishers = async () => {
  try {
    const response = await getPublishers({ page: 1, page_size: 100 })
    // response已经是标准格式，直接使用data字段
    if (response && response.data) {
      publisherList.value = response.data || []
    }
  } catch (error) {
    logger.error('加载渠道列表失败:', error)
  }
}

const setDefaultMonthRange = () => {
  const today = new Date()
  const start = new Date(today.getFullYear(), today.getMonth(), 1)
  const end = new Date(today.getFullYear(), today.getMonth() + 1, 0)
  dateRange.value = [
    start.toISOString().split('T')[0],
    end.toISOString().split('T')[0]
  ]
}

// 加载统计数据
const loadData = async () => {
  loading.value = true
  try {
    const params = {
      start_date: dateRange.value?.[0] || undefined,
      end_date: dateRange.value?.[1] || undefined,
      offer_id: filterOffer.value || undefined,
      advertiser_id: filterAdvertiser.value || undefined,
      publisher_id: filterPublisher.value || undefined
    }
    const response = await getConversionSummary(params)
    // response已经是标准格式，直接使用data字段
    if (response && response.data) {
      Object.assign(summaryData, response.data)
      statsList.value = response.data.stats_list || []
    }
  } catch (error) {
    logger.error('获取统计数据失败:', error)
    ElMessage.error('获取数据失败')
  } finally {
    loading.value = false
  }
}

// 日期改变
const handleDateChange = () => {
  loadData()
}

// 搜索
const handleSearch = () => {
  loadData()
}

// 重置
const handleReset = () => {
  setDefaultMonthRange()
  filterOffer.value = null
  filterAdvertiser.value = null
  filterPublisher.value = null
  loadData()
}

// 点击Offer ID或Offer Name跳转到Offer管理详情
const handleOfferClick = (offerId) => {
  if (offerId) {
    const route = router.resolve({
      name: 'OfferManagement',
      query: { offer_id: offerId }
    })
    window.open(route.href, '_blank')
  }
}

onMounted(() => {
  loadOffers()
  if (isAdmin.value) {
    loadAdvertisers()
  }
  loadPublishers()
  // 默认查询当月
  setDefaultMonthRange()
  loadData()
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
.filter-bar :deep(.el-date-editor .el-input__wrapper) {
  padding-right: 30px;
}

.filter-bar :deep(.el-date-editor .el-input__inner) {
  padding-right: 8px;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
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
}
</style>

