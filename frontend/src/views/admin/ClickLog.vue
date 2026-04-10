<template>
  <div class="click-log">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Mouse /></el-icon>
            <span class="header-title">短链接访问记录</span>
          </div>
          <div class="header-right">
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

      <!-- 筛选栏 -->
      <div class="filter-container">
        <ClickLogFilter
          v-model:filters="filters"
          :offer-list="offerList"
          :publisher-list="publisherList"
          @search="handleSearch"
          @reset="handleReset"
        />
      </div>

      <!-- 表格 -->
      <div class="table-wrapper">
        <el-table
          v-loading="loading"
          :data="tableData"
          stripe
          style="width: 100%;"
          :default-sort="{ prop: 'click_time', order: 'descending' }"
        >
          <el-table-column prop="click_id" label="Click ID" min-width="180" show-overflow-tooltip>
            <template #default="scope">
              <el-button 
                v-if="scope.row.click_id" 
                type="primary" 
                link 
                size="small"
                @click="copyToClipboard(scope.row.click_id)"
              >
                {{ scope.row.click_id }}
              </el-button>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="click_time" label="访问时间" width="170" sortable>
            <template #default="scope">
              {{ scope.row.click_time ? formatDate(scope.row.click_time) : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="offer_name" label="Offer" min-width="180" show-overflow-tooltip>
            <template #default="scope">
            <span class="text-primary" v-if="scope.row.offer_id && scope.row.offer_name">
              {{ `${scope.row.offer_id} - ${scope.row.offer_name}` }}
            </span>
            <span class="text-primary" v-else-if="scope.row.offer_name">
              {{ scope.row.offer_name }}
            </span>
            <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="publisher_name" label="渠道" width="140" show-overflow-tooltip>
            <template #default="scope">
              <span v-if="scope.row.publisher_id && scope.row.publisher_name">
                {{ `${scope.row.publisher_id} - ${scope.row.publisher_name}` }}
              </span>
              <span v-else-if="scope.row.publisher_name">{{ scope.row.publisher_name }}</span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="advertiser_name" label="广告主" width="140" show-overflow-tooltip>
            <template #default="scope">
              <span v-if="scope.row.advertiser_id && scope.row.advertiser_name">
                {{ `${scope.row.advertiser_id} - ${scope.row.advertiser_name}` }}
              </span>
              <span v-else-if="scope.row.advertiser_name">{{ scope.row.advertiser_name }}</span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="short_code" label="短链接代码" width="130" show-overflow-tooltip>
            <template #default="scope">
              <el-link 
                v-if="scope.row.short_code" 
                type="primary" 
                :underline="false"
                @click="handleShortCodeClick(scope.row.short_code)"
                style="cursor: pointer;"
              >
                {{ scope.row.short_code }}
              </el-link>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="ip" label="IP地址" width="130" show-overflow-tooltip>
            <template #default="scope">
              {{ scope.row.ip || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="country" label="国家" width="90" align="center">
            <template #default="scope">
              <el-tag v-if="scope.row.country" size="small" type="info">
                {{ scope.row.country }}
              </el-tag>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="device_type" label="设备类型" width="100" align="center">
            <template #default="scope">
              <el-tag 
                v-if="scope.row.device_type" 
                :type="scope.row.device_type === 'mobile' ? 'success' : scope.row.device_type === 'tablet' ? 'warning' : 'info'"
                size="small"
              >
                {{ scope.row.device_type === 'mobile' ? '手机' : scope.row.device_type === 'tablet' ? '平板' : '桌面' }}
              </el-tag>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="os" label="操作系统" width="130" show-overflow-tooltip>
            <template #default="scope">
              <span v-if="scope.row.os">
                {{ scope.row.os }}{{ scope.row.os_version ? ' ' + scope.row.os_version : '' }}
              </span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="browser" label="浏览器" width="130" show-overflow-tooltip>
            <template #default="scope">
              <span v-if="scope.row.browser">
                {{ scope.row.browser }}{{ scope.row.browser_version ? ' ' + scope.row.browser_version : '' }}
              </span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="device_brand" label="设备品牌" width="130" show-overflow-tooltip>
            <template #default="scope">
              <span v-if="scope.row.device_brand || scope.row.device_model">
                {{ scope.row.device_brand || '' }}{{ scope.row.device_brand && scope.row.device_model ? ' ' : '' }}{{ scope.row.device_model || '' }}
              </span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="is_bot" label="机器人" width="80" align="center">
            <template #default="scope">
              <el-tag v-if="scope.row.is_bot" type="danger" size="small">是</el-tag>
              <el-tag v-else type="success" size="small">否</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="referer" label="来源页面" min-width="220" show-overflow-tooltip>
            <template #default="scope">
              <el-link 
                v-if="scope.row.referer" 
                :href="scope.row.referer" 
                target="_blank" 
                type="primary"
                :underline="false"
              >
                {{ scope.row.referer.length > 50 ? scope.row.referer.substring(0, 50) + '...' : scope.row.referer }}
              </el-link>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column v-if="columnVisibility.conversion_id" prop="conversion_id" label="转化ID" width="100" align="center">
            <template #default="scope">
              <el-tag v-if="scope.row.conversion_id" type="success" size="small">
                已转化
              </el-tag>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center" fixed="right">
            <template #default="scope">
              <el-button 
                type="primary" 
                link 
                size="small"
                @click="showDetail(scope.row)"
              >
                详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <ClickLogDetailDialog
      v-model="detailDialogVisible"
      :detail="currentDetail"
    />

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="500px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="click_id" :disabled="true">Click ID（固定显示）</el-checkbox>
        <el-checkbox label="click_time" :disabled="true">访问时间（固定显示）</el-checkbox>
        <el-checkbox label="offer_name">Offer</el-checkbox>
        <el-checkbox label="publisher_name">渠道</el-checkbox>
        <el-checkbox label="advertiser_name">广告主</el-checkbox>
        <el-checkbox label="short_code">短链接代码</el-checkbox>
        <el-checkbox label="ip">IP地址</el-checkbox>
        <el-checkbox label="country">国家</el-checkbox>
        <el-checkbox label="device_type">设备类型</el-checkbox>
        <el-checkbox label="os">操作系统</el-checkbox>
        <el-checkbox label="browser">浏览器</el-checkbox>
        <el-checkbox label="device_brand">设备品牌</el-checkbox>
        <el-checkbox label="is_bot">机器人</el-checkbox>
        <el-checkbox label="referer">来源页面</el-checkbox>
        <el-checkbox label="conversion_id">转化ID</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus'
import { Mouse, Setting } from '@element-plus/icons-vue'
import { getClicks } from '@/api/clicks'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'
import { logger } from '@/utils/logger'
import { formatDate } from '@/utils/date'
import ClickLogFilter from '@/components/admin/ClickLogFilter.vue'
import ClickLogDetailDialog from '@/components/admin/ClickLogDetailDialog.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)

// 使用统一的filters对象
const filters = reactive({
  clickId: '',
  conversionId: '',
  offer: null,
  publisher: null,
  ip: '',
  country: '',
  dateRange: []
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const tableData = ref([])
const offerList = ref([])
const publisherList = ref([])
const detailDialogVisible = ref(false)
const currentDetail = ref(null)
const columnSettingVisible = ref(false)

// 列显示状态（默认全部显示）
const getDefaultColumnVisibility = () => ({
  click_id: true,  // 固定显示
  click_time: true,  // 固定显示
  offer_name: true,
  publisher_name: true,
  advertiser_name: true,
  short_code: true,
  ip: true,
  country: true,
  device_type: true,
  os: true,
  browser: true,
  device_brand: true,
  is_bot: true,
  referer: true,
  conversion_id: true
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
    const saved = localStorage.getItem('clickLog_columnVisibility')
    if (saved) {
      const savedVisibility = JSON.parse(saved)
      // 合并保存的设置和默认设置
      Object.assign(columnVisibility, getDefaultColumnVisibility(), savedVisibility)
      // 确保固定列始终显示
      columnVisibility.click_id = true
      columnVisibility.click_time = true
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
      offer_name: columnVisibility.offer_name,
      publisher_name: columnVisibility.publisher_name,
      advertiser_name: columnVisibility.advertiser_name,
      short_code: columnVisibility.short_code,
      ip: columnVisibility.ip,
      country: columnVisibility.country,
      device_type: columnVisibility.device_type,
      os: columnVisibility.os,
      browser: columnVisibility.browser,
      device_brand: columnVisibility.device_brand,
      is_bot: columnVisibility.is_bot,
      referer: columnVisibility.referer,
      conversion_id: columnVisibility.conversion_id
    }
    localStorage.setItem('clickLog_columnVisibility', JSON.stringify(toSave))
    columnSettingVisible.value = false
    ElMessage.success('列显示设置已保存')
  } catch (error) {
    logger.error('保存列显示设置失败:', error)
    ElMessage.error('保存设置失败')
  }
}

// 防抖定时器
let searchDebounceTimer = null

// 防抖搜索函数
const debouncedSearch = (delay = 500) => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  searchDebounceTimer = setTimeout(() => {
    handleSearch()
  }, delay)
}

// 加载基础数据
const loadOffers = async () => {
  try {
    const response = await getOffers({ 
      page: 1, 
      page_size: 100,
      is_active: true
    })
    // response已经是标准分页格式，直接使用data字段
    offerList.value = (response.data || []).slice().sort((a, b) => a.id - b.id)
  } catch (error) {
    logger.error('加载Offer列表失败:', error)
    ElMessage.warning('加载Offer列表失败，筛选功能可能受限')
  }
}

const loadPublishers = async () => {
  try {
    const response = await getPublishers({ page: 1, page_size: 100 })
    // response已经是标准分页格式，直接使用data字段
    publisherList.value = response.data || []
  } catch (error) {
    logger.error('加载渠道列表失败:', error)
  }
}

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: Math.min(pagination.pageSize, 100),
      click_id: filters.clickId || undefined,
      conversion_id: filters.conversionId || undefined,
      offer_id: filters.offer || undefined,
      publisher_id: filters.publisher || undefined,
      ip: filters.ip || undefined,
      country: filters.country || undefined,
      start_date: filters.dateRange?.[0] || undefined,
      end_date: filters.dateRange?.[1] || undefined
    }
    const response = await getClicks(params)
    // response已经是标准分页格式，直接使用data和total字段
    tableData.value = response.data || []
    pagination.total = response.total || 0
    
    // 如果有conversion_id参数，并且只找到一条记录，自动显示详情
    if (conversionIdFromUrl && tableData.value.length === 1) {
      currentDetail.value = tableData.value[0]
      detailDialogVisible.value = true
    }
  } catch (error) {
    logger.error('获取短链接访问记录失败:', error)
    ElMessage.error('获取数据失败')
  } finally {
    loading.value = false
  }
}

// 搜索
const handleSearch = () => {
  pagination.page = 1
  loadData()
}

// 重置
const handleReset = () => {
  filters.clickId = ''
  filters.conversionId = ''
  filters.offer = null
  filters.publisher = null
  filters.ip = ''
  filters.country = ''
  filters.dateRange = []
  pagination.page = 1
  loadData()
}

// 复制到剪贴板
const copyToClipboard = async (text) => {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    logger.error('复制失败:', error)
    ElMessage.error('复制失败')
  }
}

// 点击短链接代码，跳转到短链接管理页面并搜索
const handleShortCodeClick = async (shortCode) => {
  if (!shortCode) return
  try {
    await router.push({
      name: 'ShortLinkManagement',
      query: {
        search: shortCode
      }
    })
  } catch (error) {
    logger.error('跳转到短链接管理页面失败:', error)
    ElMessage.error('跳转失败，请重试')
  }
}

// 显示详情
const showDetail = (row) => {
  currentDetail.value = row
  detailDialogVisible.value = true
}

// 分页
const handleSizeChange = (size) => {
  pagination.pageSize = size;
  pagination.page = 1;  // 分页大小变化时重置到第一页
  loadData()
}

const handlePageChange = (page) => {
  pagination.page = page;
  loadData()
}

onMounted(() => {
  // 加载列显示设置
  loadColumnVisibility()
  loadOffers()
  loadPublishers()
  
  // 检查URL参数中是否有click_id或conversion_id，如果有则设置过滤条件
  const clickIdFromUrl = route.query.click_id
  const conversionIdFromUrl = route.query.conversion_id
  
  if (clickIdFromUrl) {
    filters.clickId = clickIdFromUrl
  }
  
  if (conversionIdFromUrl) {
    filters.conversionId = conversionIdFromUrl
  }
  
  // 加载数据（如果有参数，会自动搜索）
  
  // 默认查询最近7天（优化性能，减少数据量）
  const endDate = new Date()
  const startDate = new Date()
  startDate.setDate(startDate.getDate() - 7)
  const formatLocalDate = (date) => {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }
  filters.dateRange = [
    formatLocalDate(startDate),
    formatLocalDate(endDate)
  ]
  loadData()
})
</script>

<style scoped>
.click-log {
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
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}

.filter-container {
  margin-bottom: 20px;
}

.filter-collapse {
  border: none;
}

.filter-bar {
  padding: 10px 0;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}

.filter-row:last-child {
  margin-bottom: 0;
}

.filter-item {
  width: 200px;
}

.filter-item-small {
  width: 150px;
}

.filter-item-date {
  width: 300px;
}

.filter-actions {
  display: flex;
  gap: 10px;
}

.table-wrapper {
  margin-bottom: 20px;
}

.pagination-container {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

.text-muted {
  color: #909399;
}

.text-primary {
  color: #409eff;
}

.detail-content {
  max-height: 70vh;
  overflow-y: auto;
}

.json-content {
  background-color: #f5f7fa;
  padding: 10px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.text-wrap {
  word-break: break-all;
  white-space: pre-wrap;
}
</style>

