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
          style="width: 300px;"
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
            :label="offer.offer_name"
            :value="offer.id"
          />
        </el-select>
        <el-select
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
          <el-statistic title="总支付 (PO)" :value="summaryData.total_po || 0" :precision="2">
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
        <el-table
          :data="statsList"
          stripe
          style="width: 100%;"
        >
          <el-table-column prop="offer_id" label="Offer ID" width="100" align="right" />
          <el-table-column prop="offer_name" label="Offer Name" min-width="200" />
          <el-table-column 
            v-if="isAdmin"
            prop="advertiser_name" 
            label="Advertiser" 
            min-width="150" 
          />
          <el-table-column prop="publisher_name" label="Publisher" min-width="150" />
          <el-table-column prop="click_count" label="Click" width="120" align="right" />
          <el-table-column prop="conversion_count" label="Conversion" width="120" align="right" />
          <el-table-column prop="cr" label="CR（点击率）" width="120" align="right">
            <template #default="scope">
              {{ scope.row.cr }}%
            </template>
          </el-table-column>
          <el-table-column 
            v-if="isAdmin"
            prop="po" 
            label="PO（仅管理员可）" 
            width="150" 
            align="right"
          >
            <template #default="scope">
              <span v-if="scope.row.po !== undefined && scope.row.po !== null">{{ scope.row.po.toFixed(2) }}</span>
              <span v-else>0.00</span>
            </template>
          </el-table-column>
          <el-table-column prop="po_after_discount" label="PO（扣价后）" width="150" align="right">
            <template #default="scope">
              <span v-if="scope.row.po_after_discount !== undefined && scope.row.po_after_discount !== null">
                {{ scope.row.po_after_discount.toFixed(2) }}
              </span>
              <span v-else>0.00</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh, DataAnalysis, Mouse, Check, TrendCharts, Money } from '@element-plus/icons-vue'
import { getConversionSummary } from '@/api/conversionSummary'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'
import { logger } from '@/utils/logger'
import { useAuthStore } from '@/store'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin)

const loading = ref(false)
const dateRange = ref([])
const filterOffer = ref(null)
const filterPublisher = ref(null)

const offerList = ref([])
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
    if (response.code === 200) {
      offerList.value = response.data || []
    }
  } catch (error) {
    logger.error('加载Offer列表失败:', error)
  }
}

const loadPublishers = async () => {
  try {
    const response = await getPublishers({ page: 1, page_size: 100 })
    if (response.code === 200) {
      publisherList.value = response.data || []
    }
  } catch (error) {
    logger.error('加载渠道列表失败:', error)
  }
}

// 加载统计数据
const loadData = async () => {
  loading.value = true
  try {
    const params = {
      start_date: dateRange.value?.[0] || undefined,
      end_date: dateRange.value?.[1] || undefined,
      offer_id: filterOffer.value || undefined,
      publisher_id: filterPublisher.value || undefined
    }
    const response = await getConversionSummary(params)
    if (response.code === 200) {
      Object.assign(summaryData, response.data)
      statsList.value = response.data.stats_list || []
    } else {
      ElMessage.error(response.message || '获取数据失败')
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
  dateRange.value = []
  filterOffer.value = null
  filterPublisher.value = null
  loadData()
}

onMounted(() => {
  loadOffers()
  loadPublishers()
  // 默认查询最近30天
  const endDate = new Date()
  const startDate = new Date()
  startDate.setDate(startDate.getDate() - 30)
  dateRange.value = [
    startDate.toISOString().split('T')[0],
    endDate.toISOString().split('T')[0]
  ]
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

.stats-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
}

.table-header {
  font-weight: 600;
  font-size: 16px;
}
</style>

