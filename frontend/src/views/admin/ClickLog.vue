<template>
  <div class="click-log">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Mouse /></el-icon>
            <span class="header-title">短链接访问记录</span>
          </div>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div class="filter-container">
        <el-collapse v-model="filterCollapse" class="filter-collapse">
          <el-collapse-item name="filter" :title="filterCollapse.includes('filter') ? '收起筛选条件' : '展开筛选条件'">
            <div class="filter-bar">
              <div class="filter-row">
                <el-input
                  v-model="filterClickId"
                  placeholder="Click ID"
                  clearable
                  class="filter-item"
                  @clear="handleSearch"
                  @keyup.enter="handleSearch"
                >
                  <template #prefix>
                    <el-icon><Search /></el-icon>
                  </template>
                </el-input>
                <el-select
                  v-model="filterOffer"
                  placeholder="请选择Offer"
                  clearable
                  filterable
                  class="filter-item"
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
                  placeholder="请选择渠道"
                  clearable
                  filterable
                  class="filter-item"
                  @change="handleSearch"
                >
                  <el-option
                    v-for="pub in publisherList"
                    :key="pub.id"
                    :label="pub.publisher_name"
                    :value="pub.id"
                  />
                </el-select>
                <el-input
                  v-model="filterIp"
                  placeholder="IP地址"
                  clearable
                  class="filter-item"
                  @clear="handleSearch"
                  @keyup.enter="handleSearch"
                />
                <el-input
                  v-model="filterCountry"
                  placeholder="国家"
                  clearable
                  class="filter-item filter-item-small"
                  @clear="handleSearch"
                  @keyup.enter="handleSearch"
                />
              </div>
              <div class="filter-row">
                <el-date-picker
                  v-model="dateRange"
                  type="daterange"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                  class="filter-item filter-item-date"
                  @change="handleDateChange"
                />
                <div class="filter-actions">
                  <el-button type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
                  <el-button :icon="Refresh" @click="handleReset">重置</el-button>
                </div>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
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
          <el-table-column prop="click_id" label="Click ID" min-width="200" show-overflow-tooltip>
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
          <el-table-column prop="click_time" label="访问时间" width="180" sortable>
            <template #default="scope">
              {{ scope.row.click_time ? formatDate(scope.row.click_time) : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="offer_name" label="Offer" min-width="150" show-overflow-tooltip>
            <template #default="scope">
              <span class="text-primary">{{ scope.row.offer_name || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="publisher_name" label="渠道" width="120" show-overflow-tooltip>
            <template #default="scope">
              {{ scope.row.publisher_name || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="advertiser_name" label="广告主" width="120" show-overflow-tooltip>
            <template #default="scope">
              {{ scope.row.advertiser_name || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="short_code" label="短链接代码" width="120" show-overflow-tooltip>
            <template #default="scope">
              <el-button 
                v-if="scope.row.short_code" 
                type="primary" 
                link 
                size="small"
                @click="copyToClipboard(scope.row.short_code)"
              >
                {{ scope.row.short_code }}
              </el-button>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="ip" label="IP地址" width="140" show-overflow-tooltip>
            <template #default="scope">
              {{ scope.row.ip || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="country" label="国家" width="100" align="center">
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
          <el-table-column prop="os" label="操作系统" width="140" show-overflow-tooltip>
            <template #default="scope">
              <span v-if="scope.row.os">
                {{ scope.row.os }}{{ scope.row.os_version ? ' ' + scope.row.os_version : '' }}
              </span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="browser" label="浏览器" width="140" show-overflow-tooltip>
            <template #default="scope">
              <span v-if="scope.row.browser">
                {{ scope.row.browser }}{{ scope.row.browser_version ? ' ' + scope.row.browser_version : '' }}
              </span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="device_brand" label="设备品牌" width="120" show-overflow-tooltip>
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
          <el-table-column prop="referer" label="来源页面" min-width="200" show-overflow-tooltip>
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
          <el-table-column prop="conversion_id" label="转化ID" width="100" align="center">
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
    <el-dialog
      v-model="detailDialogVisible"
      title="点击记录详情"
      width="80%"
      :close-on-click-modal="false"
    >
      <div v-if="currentDetail" class="detail-content">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="Click ID" :span="2">
            <el-button 
              type="primary" 
              link 
              size="small"
              @click="copyToClipboard(currentDetail.click_id)"
            >
              {{ currentDetail.click_id }}
            </el-button>
          </el-descriptions-item>
          <el-descriptions-item label="访问时间">
            {{ currentDetail.click_time ? formatDate(currentDetail.click_time) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="IP地址">
            {{ currentDetail.ip || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="国家">
            <el-tag v-if="currentDetail.country" size="small" type="info">
              {{ currentDetail.country }}
            </el-tag>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="设备类型">
            <el-tag 
              v-if="currentDetail.device_type" 
              :type="currentDetail.device_type === 'mobile' ? 'success' : currentDetail.device_type === 'tablet' ? 'warning' : 'info'"
              size="small"
            >
              {{ currentDetail.device_type === 'mobile' ? '手机' : currentDetail.device_type === 'tablet' ? '平板' : '桌面' }}
            </el-tag>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="设备品牌">
            {{ currentDetail.device_brand || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="设备型号">
            {{ currentDetail.device_model || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="操作系统">
            {{ currentDetail.os ? (currentDetail.os + (currentDetail.os_version ? ' ' + currentDetail.os_version : '')) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="浏览器">
            {{ currentDetail.browser ? (currentDetail.browser + (currentDetail.browser_version ? ' ' + currentDetail.browser_version : '')) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="接受语言">
            {{ currentDetail.accept_language || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="接受编码">
            {{ currentDetail.accept_encoding || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="是否为机器人">
            <el-tag v-if="currentDetail.is_bot" type="danger" size="small">是</el-tag>
            <el-tag v-else type="success" size="small">否</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="Offer ID">
            <span v-if="currentDetail.offer_id" class="text-primary">
              {{ currentDetail.offer_id }}
            </span>
            <span v-else class="text-muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item label="Offer名称">
            {{ currentDetail.offer_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="渠道ID">
            <span v-if="currentDetail.publisher_id" class="text-primary">
              {{ currentDetail.publisher_id }}
            </span>
            <span v-else class="text-muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item label="渠道名称">
            {{ currentDetail.publisher_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="广告主ID">
            <span v-if="currentDetail.advertiser_id" class="text-primary">
              {{ currentDetail.advertiser_id }}
            </span>
            <span v-else class="text-muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item label="广告主名称">
            {{ currentDetail.advertiser_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="短链接ID">
            <span v-if="currentDetail.short_link_id" class="text-primary">
              {{ currentDetail.short_link_id }}
            </span>
            <span v-else class="text-muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item label="短链接代码">
            <el-button 
              v-if="currentDetail.short_code" 
              type="primary" 
              link 
              size="small"
              @click="copyToClipboard(currentDetail.short_code)"
            >
              {{ currentDetail.short_code }}
            </el-button>
            <span v-else class="text-muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item label="短链接标题">
            {{ currentDetail.short_link_title || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="短链接URL" :span="2">
            <el-link 
              v-if="currentDetail.short_link_url" 
              :href="currentDetail.short_link_url" 
              target="_blank" 
              type="primary"
            >
              {{ currentDetail.short_link_url }}
            </el-link>
            <span v-else class="text-muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item label="来源页面" :span="2">
            <el-link 
              v-if="currentDetail.referer" 
              :href="currentDetail.referer" 
              target="_blank" 
              type="primary"
            >
              {{ currentDetail.referer }}
            </el-link>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="原始点击URL" :span="2">
            <el-link 
              v-if="currentDetail.original_request_url" 
              :href="currentDetail.original_request_url" 
              target="_blank" 
              type="primary"
            >
              {{ currentDetail.original_request_url }}
            </el-link>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="最终跳转URL" :span="2">
            <el-link 
              v-if="currentDetail.final_redirect_url" 
              :href="currentDetail.final_redirect_url" 
              target="_blank" 
              type="success"
            >
              {{ currentDetail.final_redirect_url }}
            </el-link>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="User Agent" :span="2">
            <div class="text-wrap">{{ currentDetail.user_agent || '-' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="URL参数" :span="2" v-if="currentDetail.url_params">
            <pre class="json-content">{{ formatJSON(currentDetail.url_params) }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="请求头" :span="2" v-if="currentDetail.all_headers">
            <pre class="json-content">{{ formatJSON(currentDetail.all_headers) }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="转化ID">
            <el-tag v-if="currentDetail.conversion_id" type="success" size="small">
              已转化 (ID: {{ currentDetail.conversion_id }})
            </el-tag>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ currentDetail.created_at ? formatDate(currentDetail.created_at) : '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Mouse } from '@element-plus/icons-vue'
import { getClicks } from '@/api/clicks'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'
import { logger } from '@/utils/logger'
import { formatDate } from '@/utils/date'

const route = useRoute()
const loading = ref(false)
const filterClickId = ref('')
const filterOffer = ref(null)
const filterPublisher = ref(null)
const filterIp = ref('')
const filterCountry = ref('')
const dateRange = ref([])
const filterCollapse = ref(['filter']) // 默认展开筛选条件

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

// 加载基础数据
const loadOffers = async () => {
  try {
    const response = await getOffers({ 
      page: 1, 
      page_size: 100,
      is_active: true
    })
    if (response.code === 200) {
      offerList.value = response.data || []
    } else {
      ElMessage.warning('加载Offer列表失败，筛选功能可能受限')
    }
  } catch (error) {
    logger.error('加载Offer列表失败:', error)
    ElMessage.warning('加载Offer列表失败，筛选功能可能受限')
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

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: Math.min(pagination.pageSize, 100),
      click_id: filterClickId.value || undefined,
      offer_id: filterOffer.value || undefined,
      publisher_id: filterPublisher.value || undefined,
      ip: filterIp.value || undefined,
      country: filterCountry.value || undefined,
      start_date: dateRange.value?.[0] || undefined,
      end_date: dateRange.value?.[1] || undefined
    }
    const response = await getClicks(params)
    if (response.code === 200) {
      tableData.value = response.data || []
      pagination.total = response.total || 0
    } else {
      ElMessage.error(response.message || '获取数据失败')
    }
  } catch (error) {
    logger.error('获取短链接访问记录失败:', error)
    ElMessage.error('获取数据失败')
  } finally {
    loading.value = false
  }
}

// 日期改变
const handleDateChange = () => {
  handleSearch()
}

// 搜索
const handleSearch = () => {
  pagination.page = 1
  loadData()
}

// 重置
const handleReset = () => {
  filterClickId.value = ''
  filterOffer.value = null
  filterPublisher.value = null
  filterIp.value = ''
  filterCountry.value = ''
  dateRange.value = []
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

// 显示详情
const showDetail = (row) => {
  currentDetail.value = row
  detailDialogVisible.value = true
}

// 格式化JSON
const formatJSON = (jsonString) => {
  if (!jsonString) return '-'
  try {
    const obj = JSON.parse(jsonString)
    return JSON.stringify(obj, null, 2)
  } catch (e) {
    return jsonString
  }
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
  loadOffers()
  loadPublishers()
  
  // 检查URL参数中是否有click_id，如果有则设置过滤条件
  const clickIdFromUrl = route.query.click_id
  if (clickIdFromUrl) {
    filterClickId.value = clickIdFromUrl
  }
  
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
  dateRange.value = [
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

