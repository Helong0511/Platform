<template>
  <div class="conversion-log">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Document /></el-icon>
            <span class="header-title">转化日志</span>
          </div>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-input
          v-model="filterClickId"
          placeholder="Click ID"
          clearable
          style="width: 200px;"
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
          style="width: 180px; margin-left: 10px; min-width: 180px;"
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
          style="width: 180px; margin-left: 10px; min-width: 180px;"
          @change="handleSearch"
        >
          <el-option
            v-for="pub in publisherList"
            :key="pub.id"
            :label="pub.publisher_name"
            :value="pub.id"
          />
        </el-select>
        <el-select
          v-model="filterStatus"
          placeholder="请选择状态"
          clearable
          style="width: 140px; margin-left: 10px; min-width: 140px;"
          @change="handleSearch"
        >
          <el-option label="全部" :value="null" />
          <el-option label="Approved" value="Approved" />
          <el-option label="Pending" value="Pending" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          style="width: 300px; margin-left: 10px;"
          @change="handleDateChange"
        />
        <el-button type="primary" :icon="Search" @click="handleSearch" style="margin-left: 10px;">搜索</el-button>
        <el-button :icon="Refresh" @click="handleReset">重置</el-button>
      </div>

      <!-- 表格 -->
      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        style="width: 100%; margin-top: 20px;"
      >
        <el-table-column prop="click_id" label="Click ID" min-width="200">
          <template #default="scope">
            <el-button v-if="scope.row.click_id" type="primary" link @click="copyToClipboard(scope.row.click_id)">
              {{ scope.row.click_id }}
            </el-button>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="click_time" label="点击时间" width="180">
          <template #default="scope">
            {{ scope.row.click_time ? formatDate(scope.row.click_time) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="conversion_time" label="转化时间" width="180">
          <template #default="scope">
            {{ scope.row.conversion_time ? formatDate(scope.row.conversion_time) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="conversion_status" label="状态" width="120" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.conversion_status === 'Approved' ? 'success' : 'warning'">
              {{ scope.row.conversion_status || 'Pending' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="offer_name" label="Offer" min-width="200">
          <template #default="scope">
            {{ scope.row.offer_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="publisher_name" label="渠道" width="150">
          <template #default="scope">
            {{ scope.row.publisher_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="advertiser_name" label="广告主" width="150">
          <template #default="scope">
            {{ scope.row.advertiser_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="country" label="国家" width="100">
          <template #default="scope">
            {{ scope.row.country || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="payout" label="支付金额" width="120" align="right">
          <template #default="scope">
            <span v-if="scope.row.payout">{{ scope.row.payout.toFixed(2) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="platform" label="平台" width="100" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="scope">
            <el-dropdown @command="(cmd) => handleStatusChange(scope.row, cmd)">
              <el-button type="primary" link>
                状态 <el-icon class="el-icon--right"><arrow-down /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="Approved" :disabled="scope.row.conversion_status === 'Approved'">
                    批准
                  </el-dropdown-item>
                  <el-dropdown-item command="Pending" :disabled="scope.row.conversion_status === 'Pending'">
                    待处理
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>

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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Document, ArrowDown } from '@element-plus/icons-vue'
import { getConversionLogs, updateConversionStatus } from '@/api/conversionLog'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'
import { logger } from '@/utils/logger'
import { formatDate } from '@/utils/date'

const loading = ref(false)
const filterClickId = ref('')
const filterOffer = ref(null)
const filterPublisher = ref(null)
const filterStatus = ref(null)
const dateRange = ref([])

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const tableData = ref([])
const offerList = ref([])
const publisherList = ref([])

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
      conversion_status: filterStatus.value || undefined,
      start_date: dateRange.value?.[0] || undefined,
      end_date: dateRange.value?.[1] || undefined
    }
    const response = await getConversionLogs(params)
    if (response.code === 200) {
      tableData.value = response.data || []
      pagination.total = response.total || 0
    } else {
      ElMessage.error(response.message || '获取数据失败')
    }
  } catch (error) {
    logger.error('获取转化日志列表失败:', error)
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
  filterStatus.value = null
  dateRange.value = []
  pagination.page = 1
  loadData()
}

// 状态改变
const handleStatusChange = async (row, status) => {
  try {
    await ElMessageBox.confirm(
      `确定要将转化状态改为 "${status}" 吗？`,
      '确认操作',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const response = await updateConversionStatus(row.id, status)
    if (response.code === 200) {
      ElMessage.success('状态更新成功')
      row.conversion_status = status
    } else {
      ElMessage.error(response.message || '更新失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('更新状态失败:', error)
      ElMessage.error('更新失败')
    }
  }
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

// 分页
const handleSizeChange = () => {
  loadData()
}

const handlePageChange = () => {
  loadData()
}

onMounted(() => {
  loadOffers()
  loadPublishers()
  // 默认查询最近30天（使用本地时区）
  const endDate = new Date()
  const startDate = new Date()
  startDate.setDate(startDate.getDate() - 30)
  // 使用本地时区格式化日期，避免时区问题
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
.conversion-log {
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

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>

