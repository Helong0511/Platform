<template>
  <div class="deduction-logs">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Document /></el-icon>
            <span class="header-title">扣减日志</span>
          </div>
          <div class="header-right">
            <el-button 
              type="text" 
              :icon="Setting" 
              @click="columnSettingVisible = true"
              style="margin-right: 10px;"
            >
              列设置
            </el-button>
            <el-button type="primary" :icon="Download" @click="handleExport" :disabled="loading">导出日志</el-button>
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
            :label="`${item.id} - ${item.name}`"
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
        <el-table-column prop="id" label="ID" width="80" align="center" />
        
        <el-table-column prop="conversion_id" label="转化ID" width="120" align="center">
          <template #default="scope">
            <span v-if="scope.row.conversion_id">{{ scope.row.conversion_id }}</span>
            <el-tooltip v-else content="该转化被扣量，不会保存到主转化表，下游渠道无法看到" placement="top">
              <el-tag size="small" type="warning">已扣量</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        
        <el-table-column prop="click_id" label="点击ID" min-width="200" show-overflow-tooltip />
        
        <el-table-column prop="advertiser_name" label="广告主" min-width="150" show-overflow-tooltip />
        
        <el-table-column prop="offer_name" label="Offer" min-width="150" show-overflow-tooltip />
        
        <el-table-column prop="publisher_name" label="渠道" min-width="150" show-overflow-tooltip />
        
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
        
        <el-table-column label="操作" width="100" align="center" fixed="right">
          <template #default="scope">
            <el-button
              type="primary"
              link
              size="small"
              @click="handleViewDetail(scope.row)"
            >
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 日志详情对话框 -->
      <el-dialog
        v-model="detailDialogVisible"
        title="日志详情"
        width="800px"
      >
        <el-descriptions :column="2" border v-if="currentLog">
          <el-descriptions-item label="日志ID">{{ currentLog.id }}</el-descriptions-item>
          <el-descriptions-item label="转化ID">
            <span v-if="currentLog.conversion_id">{{ currentLog.conversion_id }}</span>
            <el-tag v-else size="small" type="warning">已扣量</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="点击ID" :span="2">{{ currentLog.click_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="广告主">{{ currentLog.advertiser_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Offer">{{ currentLog.offer_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="渠道">{{ currentLog.publisher_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="扣减策略">
            {{ getStrategyLabel(currentLog.deduction_strategy) || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="扣量信息" :span="2">
            <div v-if="currentLog.deducted_volume > 0">
              <div>原始数量: {{ currentLog.original_volume }}</div>
              <div>扣减数量: <span style="color: #E6A23C;">{{ currentLog.deducted_volume }}</span></div>
              <div>最终数量: <span style="color: #67C23A;">{{ currentLog.final_volume }}</span></div>
              <div>扣量比例: {{ ((currentLog.volume_deduction_ratio || 0) * 100).toFixed(2) }}%</div>
            </div>
            <span v-else>未扣量</span>
          </el-descriptions-item>
          <el-descriptions-item label="扣金额信息" :span="2">
            <div v-if="currentLog.deducted_amount > 0">
              <div>原始金额: {{ formatCurrency(currentLog.original_amount) }}</div>
              <div>扣减金额: <span style="color: #F56C6C;">{{ formatCurrency(currentLog.deducted_amount) }}</span></div>
              <div>最终金额: <span style="color: #67C23A;">{{ formatCurrency(currentLog.final_amount) }}</span></div>
              <div>扣金额比例: {{ ((currentLog.amount_deduction_ratio || 0) * 100).toFixed(2) }}%</div>
            </div>
            <span v-else>未扣金额</span>
          </el-descriptions-item>
          <el-descriptions-item label="扣减原因" :span="2">{{ currentLog.deduction_reason || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间" :span="2">{{ currentLog.created_at || '-' }}</el-descriptions-item>
        </el-descriptions>
        <template #footer>
          <el-button @click="detailDialogVisible = false">关闭</el-button>
        </template>
      </el-dialog>
      
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

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="id" :disabled="true">ID（固定显示）</el-checkbox>
        <el-checkbox label="conversion_id">转化ID</el-checkbox>
        <el-checkbox label="click_id" :disabled="true">点击ID（固定显示）</el-checkbox>
        <el-checkbox label="advertiser_name">广告主</el-checkbox>
        <el-checkbox label="offer_name">Offer</el-checkbox>
        <el-checkbox label="publisher_name">渠道</el-checkbox>
        <el-checkbox label="volume_deduction">扣量信息</el-checkbox>
        <el-checkbox label="amount_deduction">扣金额信息</el-checkbox>
        <el-checkbox label="deduction_strategy">扣减策略</el-checkbox>
        <el-checkbox label="created_at">创建时间</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElTooltip, ElDescriptions, ElDescriptionsItem } from 'element-plus'
import { Search, Refresh, Document, Download, Setting } from '@element-plus/icons-vue'
import { getDeductionLogs } from '@/api/deduction'
import { getAdvertisers } from '@/api/advertiser'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'
import { logger } from '@/utils/logger'

const loading = ref(false)
const tableData = ref([])
const dateRange = ref([])
const detailDialogVisible = ref(false)
const currentLog = ref(null)
const columnSettingVisible = ref(false)

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

// 列显示状态（默认全部显示）
const getDefaultColumnVisibility = () => ({
  id: true,  // 固定显示
  conversion_id: true,
  click_id: true,  // 固定显示
  advertiser_name: true,
  offer_name: true,
  publisher_name: true,
  volume_deduction: true,
  amount_deduction: true,
  deduction_strategy: true,
  created_at: true
})

const columnVisibility = reactive(getDefaultColumnVisibility())

// 计算属性：将对象转换为数组，用于 el-checkbox-group
const columnVisibilityArray = computed({
  get: () => {
    return Object.keys(columnVisibility).filter(key => columnVisibility[key])
  },
  set: (value) => {
    // 当 checkbox-group 的值变化时，更新对象
    Object.keys(columnVisibility).forEach(key => {
      columnVisibility[key] = value.includes(key)
    })
  }
})

// 从localStorage加载列显示设置
const loadColumnVisibility = () => {
  try {
    const saved = localStorage.getItem('deductionLogs_columnVisibility')
    if (saved) {
      const savedVisibility = JSON.parse(saved)
      // 合并保存的设置和默认设置
      Object.assign(columnVisibility, getDefaultColumnVisibility(), savedVisibility)
      // 确保固定列始终显示
      columnVisibility.id = true
      columnVisibility.click_id = true
    }
  } catch (error) {
    logger.error('加载列显示设置失败:', error)
  }
}

// 保存列显示设置到localStorage
const saveColumnVisibility = () => {
  try {
    // 只保存可调整的列，不保存固定列
    const toSave = {
      conversion_id: columnVisibility.conversion_id,
      advertiser_name: columnVisibility.advertiser_name,
      offer_name: columnVisibility.offer_name,
      publisher_name: columnVisibility.publisher_name,
      volume_deduction: columnVisibility.volume_deduction,
      amount_deduction: columnVisibility.amount_deduction,
      deduction_strategy: columnVisibility.deduction_strategy,
      created_at: columnVisibility.created_at
    }
    localStorage.setItem('deductionLogs_columnVisibility', JSON.stringify(toSave))
    columnSettingVisible.value = false
    ElMessage.success('列显示设置已保存')
  } catch (error) {
    logger.error('保存列显示设置失败:', error)
    ElMessage.error('保存设置失败')
  }
}

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

// 查看详情
const handleViewDetail = (row) => {
  currentLog.value = { ...row }
  detailDialogVisible.value = true
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
    // response已经是标准分页格式，直接使用data和total字段
    tableData.value = response.data || []
    pagination.total = response.total || 0
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

// 导出日志
const handleExport = () => {
  try {
    // 构建导出参数（使用当前筛选条件）
    const params = new URLSearchParams()
    if (searchForm.start_time) {
      params.append('start_date', searchForm.start_time.split(' ')[0])
    }
    if (searchForm.end_time) {
      params.append('end_date', searchForm.end_time.split(' ')[0])
    }
    if (searchForm.conversion_id) {
      params.append('conversion_id', searchForm.conversion_id.toString())
    }
    if (searchForm.click_id) {
      params.append('click_id', searchForm.click_id)
    }
    if (searchForm.advertiser_id) {
      params.append('advertiser_id', searchForm.advertiser_id.toString())
    }
    if (searchForm.offer_id) {
      params.append('offer_id', searchForm.offer_id.toString())
    }
    if (searchForm.publisher_id) {
      params.append('publisher_id', searchForm.publisher_id.toString())
    }
    
    // 使用window.open下载文件
    const url = `/api/v1/conversion-deductions/logs/export?${params.toString()}`
    window.open(url, '_blank')
    
    ElMessage.success('导出请求已发送，请稍候...')
  } catch (error) {
    ElMessage.error('导出失败：' + (error.message || '未知错误'))
  }
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
        // advertiserRes已经是标准分页格式，直接使用data和total字段
        const advertisers = advertiserRes.data || []
        allAdvertisers = allAdvertisers.concat(advertisers)
        
        const total = advertiserRes.total || 0
        hasMore = allAdvertisers.length < total && advertisers.length > 0
        page++
      } catch (err) {
        logger.error('加载广告主失败：', err)
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
        // offerRes已经是标准分页格式，直接使用data和total字段
        const offers = offerRes.data || []
        allOffers = allOffers.concat(offers)
        
        const total = offerRes.total || 0
        hasMore = allOffers.length < total && offers.length > 0
        page++
      } catch (err) {
        logger.error('加载Offer失败：', err)
        hasMore = false
      }
    }
    
    offerOptions.value = allOffers
      .slice()
      .sort((a, b) => a.id - b.id)
      .map(item => ({
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
        // publisherRes已经是标准分页格式，直接使用data和total字段
        const publishers = publisherRes.data || []
        allPublishers = allPublishers.concat(publishers)
        
        const total = publisherRes.total || 0
        hasMore = allPublishers.length < total && publishers.length > 0
        page++
      } catch (err) {
        logger.error('加载渠道失败：', err)
        hasMore = false
      }
    }
    
    publisherOptions.value = allPublishers.map(item => ({
      id: item.id,
      name: item.publisher_name
    }))
  } catch (error) {
    logger.error('加载选项数据失败：', error)
    ElMessage.error('加载选项数据失败：' + (error.message || '未知错误'))
  }
}

onMounted(() => {
  // 加载列显示设置
  loadColumnVisibility()
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

