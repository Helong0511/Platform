<template>
  <div class="deduction-stats">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><DataAnalysis /></el-icon>
            <span class="header-title">扣减统计</span>
          </div>
          <el-button :icon="Refresh" @click="handleRefresh">刷新</el-button>
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
            <div style="font-weight: 600; margin-bottom: 8px;">统计说明：</div>
            <div style="margin-left: 20px;">
              <div style="margin-bottom: 6px;">
                <strong style="color: #E6A23C;">扣量统计</strong>：
                <ul style="margin: 4px 0 0 20px; padding: 0; line-height: 1.6;">
                  <li><strong>原始转化数量</strong>：统计时间范围内所有转化记录的总数（包括被扣量的和未扣量的）</li>
                  <li><strong>扣减转化数量</strong>：被扣量的转化数量（这些转化<strong style="color: #F56C6C;">不会保存到主转化表</strong>，下游<strong style="color: #F56C6C;">无法看到</strong>）</li>
                  <li><strong>最终转化数量</strong>：实际保存到数据库的转化数量（原始数量 - 扣减数量）</li>
                  <li><strong>扣量比例</strong>：扣减数量 ÷ 原始数量 × 100%</li>
                </ul>
              </div>
              <div>
                <strong style="color: #F56C6C;">扣金额统计</strong>：
                <ul style="margin: 4px 0 0 20px; padding: 0; line-height: 1.6;">
                  <li><strong>原始转化金额</strong>：所有转化的原始金额总和</li>
                  <li><strong>扣减转化金额</strong>：按比例扣减的金额总和（转化<strong style="color: #67C23A;">仍然保存</strong>，但金额减少）</li>
                  <li><strong>最终转化金额</strong>：实际支付给下游的金额总和（原始金额 - 扣减金额）</li>
                  <li><strong>扣金额比例</strong>：扣减金额 ÷ 原始金额 × 100%</li>
                </ul>
              </div>
            </div>
          </div>
        </template>
      </el-alert>

      <!-- 筛选条件 -->
      <div class="filter-bar">
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
        
        <el-select
          v-model="filterForm.advertiser_id"
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
          v-model="filterForm.offer_id"
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
          v-model="filterForm.publisher_id"
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
        
        <el-select
          v-model="filterForm.group_by"
          placeholder="分组方式"
          clearable
          style="width: 150px; margin-left: 10px;"
          @change="handleSearch"
        >
          <el-option label="不分组" value="" />
          <el-option label="按广告主" value="advertiser" />
          <el-option label="按Offer" value="offer" />
          <el-option label="按渠道" value="publisher" />
        </el-select>
        
        <el-button type="primary" :icon="Search" @click="handleSearch" style="margin-left: 10px;">
          查询
        </el-button>
        <el-button :icon="Refresh" @click="handleReset">重置</el-button>
      </div>

      <!-- 统计卡片 -->
      <div class="stats-cards" v-loading="loading">
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-label">原始转化数量</div>
            <div class="stat-value">{{ stats.original_volume || 0 }}</div>
          </div>
        </el-card>
        
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-label">扣减转化数量</div>
            <div class="stat-value warning">{{ stats.deducted_volume || 0 }}</div>
          </div>
        </el-card>
        
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-label">最终转化数量</div>
            <div class="stat-value success">{{ stats.final_volume || 0 }}</div>
          </div>
        </el-card>
        
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-label">扣量比例</div>
            <div class="stat-value warning">
              {{ ((stats.volume_deduction_ratio || 0) * 100).toFixed(2) }}%
            </div>
          </div>
        </el-card>
        
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-label">原始转化金额</div>
            <div class="stat-value">{{ formatCurrency(stats.original_amount || 0) }}</div>
          </div>
        </el-card>
        
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-label">扣减转化金额</div>
            <div class="stat-value danger">{{ formatCurrency(stats.deducted_amount || 0) }}</div>
          </div>
        </el-card>
        
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-label">最终转化金额</div>
            <div class="stat-value success">{{ formatCurrency(stats.final_amount || 0) }}</div>
          </div>
        </el-card>
        
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-label">扣金额比例</div>
            <div class="stat-value danger">
              {{ ((stats.amount_deduction_ratio || 0) * 100).toFixed(2) }}%
            </div>
          </div>
        </el-card>
      </div>

      <!-- 详细统计表格 -->
      <div class="table-section" v-if="detailStats.length > 0">
        <h3>详细统计</h3>
        <el-table
          v-loading="loading"
          :data="detailStats"
          stripe
          style="width: 100%; margin-top: 20px;"
        >
          <el-table-column prop="advertiser_name" label="广告主" min-width="150" />
          <el-table-column prop="offer_name" label="Offer" min-width="150" />
          <el-table-column prop="publisher_name" label="渠道" min-width="150" />
          <el-table-column label="扣量统计" align="center">
            <el-table-column prop="original_volume" label="原始数量" width="100" align="right">
              <template #default="scope">
                <span>{{ scope.row.original_volume || 0 }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="deducted_volume" label="扣减数量" width="100" align="right">
              <template #default="scope">
                <span class="text-warning">{{ scope.row.deducted_volume || 0 }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="final_volume" label="最终数量" width="100" align="right">
              <template #default="scope">
                <span class="text-success">{{ scope.row.final_volume || 0 }}</span>
              </template>
            </el-table-column>
            <el-table-column label="扣量比例" width="100" align="right">
              <template #default="scope">
                <el-tag size="small" type="warning">
                  {{ ((scope.row.volume_deduction_ratio || 0) * 100).toFixed(2) }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="扣金额统计" align="center">
            <el-table-column prop="original_amount" label="原始金额" width="120" align="right">
              <template #default="scope">
                {{ formatCurrency(scope.row.original_amount || 0) }}
              </template>
            </el-table-column>
            <el-table-column prop="deducted_amount" label="扣减金额" width="120" align="right">
              <template #default="scope">
                <span class="text-danger">{{ formatCurrency(scope.row.deducted_amount || 0) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="final_amount" label="最终金额" width="120" align="right">
              <template #default="scope">
                <span class="text-success">{{ formatCurrency(scope.row.final_amount || 0) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="扣金额比例" width="100" align="right">
              <template #default="scope">
                <el-tag size="small" type="danger">
                  {{ ((scope.row.amount_deduction_ratio || 0) * 100).toFixed(2) }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table-column>
        </el-table>
      </div>
      
      <!-- 无数据提示 -->
      <el-empty v-if="!loading && detailStats.length === 0" description="暂无详细统计数据" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh, DataAnalysis } from '@element-plus/icons-vue'
import { getDeductionStats } from '@/api/deduction'
import { getAdvertisers } from '@/api/advertiser'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'

const loading = ref(false)
const dateRange = ref([])
const stats = ref({})
const detailStats = ref([])

const filterForm = reactive({
  start_time: null,
  end_time: null,
  advertiser_id: null,
  offer_id: null,
  publisher_id: null,
  group_by: null
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

// 获取统计数据
const fetchStats = async () => {
  loading.value = true
  try {
    // 转换日期格式：从 YYYY-MM-DD HH:mm:ss 转换为 YYYY-MM-DD
    const params = {
      advertiser_id: filterForm.advertiser_id,
      offer_id: filterForm.offer_id,
      publisher_id: filterForm.publisher_id
    }
    
    // 转换日期格式
    if (filterForm.start_time) {
      params.start_date = filterForm.start_time.split(' ')[0] // 只取日期部分
    }
    if (filterForm.end_time) {
      params.end_date = filterForm.end_time.split(' ')[0] // 只取日期部分
    }
    
    // 添加分组参数
    if (filterForm.group_by) {
      params.group_by = filterForm.group_by
    }
    
    const response = await getDeductionStats(params)
    if (response.code === 200) {
      // 后端返回的数据结构：response.data 就是 DeductionStatsResponse
      const data = response.data || {}
      stats.value = {
        original_volume: data.original_volume || 0,
        deducted_volume: data.deducted_volume || 0,
        final_volume: data.final_volume || 0,
        volume_deduction_ratio: data.volume_deduction_ratio || 0,
        original_amount: data.original_amount || 0,
        deducted_amount: data.deducted_amount || 0,
        final_amount: data.final_amount || 0,
        amount_deduction_ratio: data.amount_deduction_ratio || 0
      }
      // items 是分组统计的详细数据
      detailStats.value = data.items || []
      
      // 如果分组了，需要加载名称信息
      if (filterForm.group_by && detailStats.value.length > 0) {
        await loadGroupNames()
      }
    }
  } catch (error) {
    ElMessage.error('获取统计数据失败：' + (error.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// 加载分组名称
const loadGroupNames = async () => {
  try {
    if (filterForm.group_by === 'advertiser') {
      // 分页加载所有广告主
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
      
      const advertiserMap = new Map(allAdvertisers.map(a => [a.id, a.advertiser_name]))
      detailStats.value = detailStats.value.map(item => ({
        ...item,
        advertiser_name: advertiserMap.get(item.advertiser_id) || `广告主${item.advertiser_id}`
      }))
    } else if (filterForm.group_by === 'offer') {
      // 分页加载所有Offer
      let allOffers = []
      let page = 1
      const pageSize = 100 // 后端最大限制
      let hasMore = true
      
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
      
      const offerMap = new Map(allOffers.map(o => [o.id, o.offer_name]))
      detailStats.value = detailStats.value.map(item => ({
        ...item,
        offer_name: offerMap.get(item.offer_id) || `Offer${item.offer_id}`
      }))
    } else if (filterForm.group_by === 'publisher') {
      // 分页加载所有渠道
      let allPublishers = []
      let page = 1
      const pageSize = 100 // 后端最大限制
      let hasMore = true
      
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
      
      const publisherMap = new Map(allPublishers.map(p => [p.id, p.publisher_name]))
      detailStats.value = detailStats.value.map(item => ({
        ...item,
        publisher_name: publisherMap.get(item.publisher_id) || `渠道${item.publisher_id}`
      }))
    }
  } catch (error) {
    console.error('加载分组名称失败：', error)
  }
}

// 日期范围变化
const handleDateChange = (dates) => {
  if (dates && dates.length === 2) {
    filterForm.start_time = dates[0]
    filterForm.end_time = dates[1]
  } else {
    filterForm.start_time = null
    filterForm.end_time = null
  }
  handleSearch()
}

// 搜索
const handleSearch = () => {
  fetchStats()
}

// 重置
const handleReset = () => {
  dateRange.value = []
  filterForm.start_time = null
  filterForm.end_time = null
  filterForm.advertiser_id = null
  filterForm.offer_id = null
  filterForm.publisher_id = null
  filterForm.group_by = null
  handleSearch()
}

// 刷新
const handleRefresh = () => {
  fetchStats()
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
  // 设置默认时间范围（最近30天）
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 30)
  
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
  filterForm.start_time = dateRange.value[0]
  filterForm.end_time = dateRange.value[1]
  
  loadOptions()
  fetchStats()
})
</script>

<style scoped>
.deduction-stats {
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

.filter-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 20px;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 30px;
}

.stat-card {
  text-align: center;
}

.stat-content {
  padding: 10px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 10px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.stat-value.warning {
  color: #E6A23C;
}

.stat-value.danger {
  color: #F56C6C;
}

.stat-value.success {
  color: #67C23A;
}

.table-section {
  margin-top: 30px;
}

.table-section {
  margin-top: 30px;
}

.table-section h3 {
  font-size: 16px;
  font-weight: 500;
  margin-bottom: 10px;
  color: #303133;
}

.text-warning {
  color: #E6A23C;
  font-weight: 600;
}

.text-danger {
  color: #F56C6C;
  font-weight: 600;
}

.text-success {
  color: #67C23A;
  font-weight: 600;
}
</style>

