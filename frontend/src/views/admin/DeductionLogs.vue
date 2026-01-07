<template>
  <div class="deduction-logs">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Document /></el-icon>
            <span class="header-title">扣减日志</span>
          </div>
        </div>
      </template>

      <!-- 功能说明卡片 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 20px;"
      >
        <template #title>
          <div style="line-height: 1.8;">
            <div style="font-weight: 600; margin-bottom: 8px;">日志说明：</div>
            <div style="margin-left: 20px;">
              <div style="margin-bottom: 6px;">
                <strong style="color: #E6A23C;">扣量日志</strong>：
                <ul style="margin: 4px 0 0 20px; padding: 0; line-height: 1.6;">
                  <li>记录所有扣量操作的详细信息</li>
                  <li>被扣量的转化<strong style="color: #F56C6C;">不会保存到主转化表</strong>，所以<strong style="color: #F56C6C;">转化ID为空</strong>（显示"已扣量"标签）</li>
                  <li>但会在扣减日志表中记录，用于统计和审计</li>
                  <li>下游渠道<strong style="color: #F56C6C;">完全看不到</strong>被扣量的转化</li>
                </ul>
              </div>
              <div>
                <strong style="color: #F56C6C;">扣金额日志</strong>：
                <ul style="margin: 4px 0 0 20px; padding: 0; line-height: 1.6;">
                  <li>记录所有扣金额操作的详细信息</li>
                  <li>被扣金额的转化<strong style="color: #67C23A;">仍然保存到主转化表</strong>，所以<strong style="color: #67C23A;">有转化ID</strong></li>
                  <li>下游渠道可以看到转化记录，但<strong style="color: #F56C6C;">金额已按比例减少</strong></li>
                  <li>例如：原始金额$100，扣金额比例5%，最终支付$95给下游</li>
                </ul>
              </div>
              <div style="margin-top: 8px; font-size: 12px; color: #909399;">
                <strong>注意</strong>：所有转化都会记录到扣减日志表，即使未扣减也会记录（用于统计准确性）
              </div>
            </div>
          </div>
        </template>
      </el-alert>

      <!-- 搜索筛选区 -->
      <div class="search-bar">
        <el-date-picker
          v-model="dateRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          format="YYYY-MM-DD HH:mm:ss"
          value-format="YYYY-MM-DD HH:mm:ss"
          style="width: 400px;"
          @change="handleDateChange"
        />
        
        <el-input
          v-model="searchForm.conversion_id"
          placeholder="转化ID"
          clearable
          style="width: 150px; margin-left: 10px;"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        />
        
        <el-input
          v-model="searchForm.click_id"
          placeholder="点击ID"
          clearable
          style="width: 200px; margin-left: 10px;"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        />
        
        <el-select
          v-model="searchForm.advertiser_id"
          placeholder="选择广告主"
          clearable
          filterable
          style="width: 200px; margin-left: 10px;"
          @change="handleSearch"
        >
          <el-option
            v-for="item in advertiserOptions"
            :key="item.id"
            :label="item.name"
            :value="item.id"
          />
        </el-select>
        
        <el-select
          v-model="searchForm.offer_id"
          placeholder="选择Offer"
          clearable
          filterable
          style="width: 200px; margin-left: 10px;"
          @change="handleSearch"
        >
          <el-option
            v-for="item in offerOptions"
            :key="item.id"
            :label="item.name"
            :value="item.id"
          />
        </el-select>
        
        <el-select
          v-model="searchForm.publisher_id"
          placeholder="选择渠道"
          clearable
          filterable
          style="width: 200px; margin-left: 10px;"
          @change="handleSearch"
        >
          <el-option
            v-for="item in publisherOptions"
            :key="item.id"
            :label="item.name"
            :value="item.id"
          />
        </el-select>
        
        <el-button type="primary" :icon="Search" @click="handleSearch" style="margin-left: 10px;">
          搜索
        </el-button>
        <el-button :icon="Refresh" @click="handleReset">重置</el-button>
      </div>

      <!-- 日志列表表格 -->
      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        style="width: 100%; margin-top: 20px;"
      >
        <el-table-column prop="id" label="ID" width="80" />
        
        <el-table-column prop="conversion_id" label="转化ID" width="120">
          <template #default="scope">
            <span v-if="scope.row.conversion_id">{{ scope.row.conversion_id }}</span>
            <el-tooltip v-else content="该转化被扣量，不会保存到主转化表，下游渠道无法看到" placement="top">
              <el-tag size="small" type="warning">已扣量</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        
        <el-table-column prop="click_id" label="点击ID" min-width="200" show-overflow-tooltip />
        
        <el-table-column prop="advertiser_name" label="广告主" min-width="150" />
        
        <el-table-column prop="offer_name" label="Offer" min-width="150" />
        
        <el-table-column prop="publisher_name" label="渠道" min-width="150" />
        
        <el-table-column label="扣量信息" align="center" width="220">
          <template #default="scope">
            <div v-if="scope.row.deducted_volume > 0" class="deduction-info volume-deduction">
              <div class="deduction-row">
                <span class="deduction-label">原始:</span>
                <span class="deduction-value">{{ scope.row.original_volume }}</span>
              </div>
              <div class="deduction-row">
                <span class="deduction-label">扣减:</span>
                <span class="deduction-value deducted">{{ scope.row.deducted_volume }}</span>
              </div>
              <div class="deduction-row">
                <span class="deduction-label">最终:</span>
                <span class="deduction-value final">{{ scope.row.final_volume }}</span>
              </div>
              <div v-if="scope.row.volume_deduction_ratio" class="deduction-ratio">
                比例: {{ (scope.row.volume_deduction_ratio * 100).toFixed(2) }}%
              </div>
            </div>
            <span v-else class="no-deduction">未扣量</span>
          </template>
        </el-table-column>
        
        <el-table-column label="扣金额信息" align="center" width="220">
          <template #default="scope">
            <div v-if="scope.row.deducted_amount > 0" class="deduction-info amount-deduction">
              <div class="deduction-row">
                <span class="deduction-label">原始:</span>
                <span class="deduction-value">{{ formatCurrency(scope.row.original_amount) }}</span>
              </div>
              <div class="deduction-row">
                <span class="deduction-label">扣减:</span>
                <span class="deduction-value deducted">{{ formatCurrency(scope.row.deducted_amount) }}</span>
              </div>
              <div class="deduction-row">
                <span class="deduction-label">最终:</span>
                <span class="deduction-value final">{{ formatCurrency(scope.row.final_amount) }}</span>
              </div>
              <div v-if="scope.row.amount_deduction_ratio" class="deduction-ratio">
                比例: {{ (scope.row.amount_deduction_ratio * 100).toFixed(2) }}%
              </div>
            </div>
            <span v-else class="no-deduction">未扣金额</span>
          </template>
        </el-table-column>
        
        <el-table-column prop="deduction_strategy" label="扣减策略" width="100" align="center">
          <template #default="scope">
            <el-tag size="small" type="info">
              {{ getStrategyLabel(scope.row.deduction_strategy) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="created_at" label="创建时间" width="180" />
      </el-table>
      
      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElTooltip } from 'element-plus'
import { Search, Refresh, Document } from '@element-plus/icons-vue'
import { getDeductionLogs } from '@/api/deduction'
import { getAdvertisers } from '@/api/advertiser'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'

const loading = ref(false)
const tableData = ref([])
const dateRange = ref([])

const searchForm = reactive({
  start_time: null,
  end_time: null,
  conversion_id: '',
  click_id: '',
  advertiser_id: null,
  offer_id: null,
  publisher_id: null
})

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

const advertiserOptions = ref([])
const offerOptions = ref([])
const publisherOptions = ref([])

// 格式化货币
const formatCurrency = (amount) => {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(amount)
}

// 获取策略标签
const getStrategyLabel = (strategy) => {
  const map = {
    'random': '随机',
    'proportional': '按比例',
    'round_robin': '轮询'
  }
  return map[strategy] || strategy
}

// 获取日志列表
const fetchData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.page_size,
      advertiser_id: searchForm.advertiser_id,
      offer_id: searchForm.offer_id,
      publisher_id: searchForm.publisher_id,
      conversion_id: searchForm.conversion_id ? parseInt(searchForm.conversion_id) : null,
      click_id: searchForm.click_id || null
    }
    
    // 转换日期格式：从 YYYY-MM-DD HH:mm:ss 转换为 YYYY-MM-DD
    if (searchForm.start_time) {
      params.start_date = searchForm.start_time.split(' ')[0] // 只取日期部分
    }
    if (searchForm.end_time) {
      params.end_date = searchForm.end_time.split(' ')[0] // 只取日期部分
    }
    
    // 移除空值
    Object.keys(params).forEach(key => {
      if (params[key] === null || params[key] === undefined || params[key] === '') {
        delete params[key]
      }
    })
    
    const response = await getDeductionLogs(params)
    if (response.code === 200) {
      const data = response.data || {}
      tableData.value = data.data || data.items || []
      pagination.total = data.total || response.total || 0
    }
  } catch (error) {
    ElMessage.error('获取日志列表失败：' + (error.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// 日期范围变化
const handleDateChange = (dates) => {
  if (dates && dates.length === 2) {
    searchForm.start_time = dates[0]
    searchForm.end_time = dates[1]
  } else {
    searchForm.start_time = null
    searchForm.end_time = null
  }
  handleSearch()
}

// 搜索
const handleSearch = () => {
  pagination.page = 1
  fetchData()
}

// 重置
const handleReset = () => {
  dateRange.value = []
  searchForm.start_time = null
  searchForm.end_time = null
  searchForm.conversion_id = ''
  searchForm.click_id = ''
  searchForm.advertiser_id = null
  searchForm.offer_id = null
  searchForm.publisher_id = null
  handleSearch()
}

// 分页
const handlePageChange = (page) => {
  pagination.page = page
  fetchData()
}

const handleSizeChange = (size) => {
  // 确保page_size不超过后端最大限制
  pagination.page_size = Math.min(size, 100)
  pagination.page = 1
  fetchData()
}

// 加载选项数据（分页加载所有数据）
const loadOptions = async () => {
  try {
    // 加载广告主（分页加载所有）
    let allAdvertisers = []
    let page = 1
    const pageSize = 100 // 后端最大限制
    let hasMore = true
    
    while (hasMore) {
      try {
        const advertiserRes = await getAdvertisers({ page, page_size: pageSize })
        if (advertiserRes && advertiserRes.code === 200) {
          const data = advertiserRes.data || {}
          const advertisers = data.data || data.items || []
          allAdvertisers = allAdvertisers.concat(advertisers)
          
          const total = data.total || advertiserRes.total || 0
          hasMore = allAdvertisers.length < total && advertisers.length > 0
          page++
        } else {
          hasMore = false
        }
      } catch (err) {
        console.error('加载广告主失败：', err)
        hasMore = false
      }
    }
    
    advertiserOptions.value = allAdvertisers.map(item => ({
      id: item.id,
      name: item.advertiser_name
    }))
    
    // 加载Offer（分页加载所有）
    let allOffers = []
    page = 1
    hasMore = true
    
    while (hasMore) {
      try {
        const offerRes = await getOffers({ page, page_size: pageSize })
        if (offerRes && offerRes.code === 200) {
          const data = offerRes.data || {}
          const offers = data.data || data.items || []
          allOffers = allOffers.concat(offers)
          
          const total = data.total || offerRes.total || 0
          hasMore = allOffers.length < total && offers.length > 0
          page++
        } else {
          hasMore = false
        }
      } catch (err) {
        console.error('加载Offer失败：', err)
        hasMore = false
      }
    }
    
    offerOptions.value = allOffers.map(item => ({
      id: item.id,
      name: item.offer_name
    }))
    
    // 加载渠道（分页加载所有）
    let allPublishers = []
    page = 1
    hasMore = true
    
    while (hasMore) {
      try {
        const publisherRes = await getPublishers({ page, page_size: pageSize })
        if (publisherRes && publisherRes.code === 200) {
          const data = publisherRes.data || {}
          const publishers = data.data || data.items || []
          allPublishers = allPublishers.concat(publishers)
          
          const total = data.total || publisherRes.total || 0
          hasMore = allPublishers.length < total && publishers.length > 0
          page++
        } else {
          hasMore = false
        }
      } catch (err) {
        console.error('加载渠道失败：', err)
        hasMore = false
      }
    }
    
    publisherOptions.value = allPublishers.map(item => ({
      id: item.id,
      name: item.publisher_name
    }))
  } catch (error) {
    console.error('加载选项数据失败：', error)
    ElMessage.error('加载选项数据失败：' + (error.message || '未知错误'))
  }
}

onMounted(() => {
  // 设置默认时间范围（最近7天）
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 7)
  
  // 格式化为 YYYY-MM-DD HH:mm:ss
  const formatDateTime = (date) => {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    const seconds = String(date.getSeconds()).padStart(2, '0')
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
  }
  
  dateRange.value = [
    formatDateTime(start),
    formatDateTime(end)
  ]
  searchForm.start_time = dateRange.value[0]
  searchForm.end_time = dateRange.value[1]
  
  loadOptions()
  fetchData()
})
</script>

<style scoped>
.deduction-logs {
  padding: 20px;
}

.page-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
}

.header-icon {
  font-size: 20px;
  margin-right: 8px;
  color: #409EFF;
}

.header-title {
  font-size: 18px;
  font-weight: 500;
}

.search-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.deduction-info {
  font-size: 12px;
  line-height: 1.8;
  padding: 8px;
  border-radius: 4px;
}

.deduction-info.volume-deduction {
  background-color: #FDF6EC;
  border: 1px solid #F5DAB1;
}

.deduction-info.amount-deduction {
  background-color: #FEF0F0;
  border: 1px solid #FBC4C4;
}

.deduction-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.deduction-row:last-child {
  margin-bottom: 0;
}

.deduction-label {
  color: #606266;
  font-weight: 500;
}

.deduction-value {
  font-weight: 600;
  color: #303133;
}

.deduction-value.deducted {
  color: #F56C6C;
}

.deduction-value.final {
  color: #67C23A;
}

.deduction-ratio {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #DCDFE6;
  font-size: 11px;
  color: #909399;
  text-align: center;
}

.no-deduction {
  color: #909399;
  font-size: 12px;
}
</style>

