<template>
  <div class="postback-management-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1>Postback 转化管理</h1>
        <div class="stats-info" v-if="stats && stats.length > 0">
          <span class="stat-item" v-for="stat in stats" :key="stat.platform">
            <span class="stat-label">{{ stat.platform }}：</span>
            <span class="stat-value">{{ stat.total_conversions || 0 }}</span>
            <span class="stat-unit">条转化</span>
            <span class="stat-separator">|</span>
            <span class="stat-label">总金额：</span>
            <span class="stat-value">{{ formatCurrency(stat.total_payout || 0) }}</span>
          </span>
        </div>
      </div>
    </div>

    <!-- 筛选控件 -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="平台">
          <el-select v-model="searchForm.platform" placeholder="全部" clearable style="width: 150px;" name="platform" popper-class="select-dropdown" :teleported="true">
            <el-option label="全部" value=""></el-option>
            <el-option label="Macan" value="macan"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="事件名称">
          <el-input 
            v-model="searchForm.event_name" 
            placeholder="输入事件名称" 
            clearable
            @keyup.enter="fetchConversions"
            style="width: 200px;"
            name="event_name"
          >
            <template #prefix>
              <el-icon :size="16"><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="产品ID">
          <el-input-number 
            v-model="searchForm.product_id" 
            placeholder="产品ID" 
            clearable
            :min="1"
            style="width: 150px;"
            name="product_id"
          />
        </el-form-item>
        <el-form-item label="客户ID">
          <el-input-number 
            v-model="searchForm.client_id" 
            placeholder="客户ID" 
            clearable
            :min="1"
            style="width: 150px;"
            name="client_id"
          />
        </el-form-item>
        <el-form-item label="时间范围" class="date-range-item">
          <el-date-picker
            v-model="dateRange"
            name="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 300px;"
            class="date-picker-full"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchConversions" :loading="loading" :icon="Search">
            查询
          </el-button>
          <el-button @click="resetFilter" :icon="Refresh">
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 统计数据卡片 -->
    <el-card class="stats-card" shadow="never" v-if="stats && stats.length > 0">
      <template #header>
        <div class="stats-header">
          <span>平台统计</span>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :xs="24" :sm="12" :md="8" :lg="6" v-for="stat in stats" :key="stat.platform">
          <div class="stat-card">
            <div class="stat-card-header">
              <span class="platform-name">{{ stat.platform.toUpperCase() }}</span>
            </div>
            <div class="stat-card-body">
              <div class="stat-row">
                <span class="stat-label">总转化数：</span>
                <span class="stat-value">{{ stat.total_conversions || 0 }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">总支付金额：</span>
                <span class="stat-value highlight">{{ formatCurrency(stat.total_payout || 0) }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">总事件价值：</span>
                <span class="stat-value">{{ formatCurrency(stat.total_event_value || 0) }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">唯一事件数：</span>
                <span class="stat-value">{{ stat.unique_events || 0 }}</span>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 转化数据表格 -->
    <el-card class="data-table-card" shadow="never">
      <template #header>
        <div class="table-header">
          <span>转化记录列表</span>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="conversions"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="platform" label="平台" width="100">
          <template #default="scope">
            <el-tag type="primary" size="small">
              {{ scope.row.platform.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="conversion_id" label="转化ID" min-width="150" show-overflow-tooltip />
        <el-table-column prop="event_name" label="事件名称" width="120">
          <template #default="scope">
            <el-tag v-if="scope.row.event_name" type="success" size="small">
              {{ scope.row.event_name }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="event_value" label="事件价值" width="120" align="right">
          <template #default="scope">
            {{ scope.row.event_value ? formatCurrency(scope.row.event_value) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="payout" label="支付金额" width="120" align="right">
          <template #default="scope">
            <span class="highlight" v-if="scope.row.payout">
              {{ formatCurrency(scope.row.payout) }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="devad_id" label="设备ID" min-width="150" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.devad_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="os" label="操作系统" width="100">
          <template #default="scope">
            <el-tag v-if="scope.row.os" size="small">
              {{ scope.row.os }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="carrier" label="运营商" width="120">
          <template #default="scope">
            {{ scope.row.carrier || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="product_id" label="产品ID" width="100" align="center">
          <template #default="scope">
            {{ scope.row.product_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="client_id" label="客户ID" width="100" align="center">
          <template #default="scope">
            {{ scope.row.client_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDateTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
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

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          :layout="isMobile ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
        />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="转化记录详情"
      :width="isMobile ? '95%' : '900px'"
      class="conversion-detail-dialog"
      :close-on-click-modal="false"
      :append-to-body="true"
    >
      <div v-if="currentConversion" class="conversion-detail-content">
        <el-descriptions :column="isMobile ? 1 : 2" border>
          <el-descriptions-item label="记录ID">{{ currentConversion.id }}</el-descriptions-item>
          <el-descriptions-item label="平台">
            <el-tag type="primary">{{ currentConversion.platform.toUpperCase() }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="转化ID">{{ currentConversion.conversion_id }}</el-descriptions-item>
          <el-descriptions-item label="事件名称">
            <el-tag v-if="currentConversion.event_name" type="success">
              {{ currentConversion.event_name }}
            </el-tag>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="事件价值">
            {{ currentConversion.event_value ? formatCurrency(currentConversion.event_value) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="支付金额">
            <span class="highlight" v-if="currentConversion.payout">
              {{ formatCurrency(currentConversion.payout) }}
            </span>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="设备ID">{{ currentConversion.devad_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="操作系统">
            <el-tag v-if="currentConversion.os" size="small">
              {{ currentConversion.os }}
            </el-tag>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="运营商">{{ currentConversion.carrier || '-' }}</el-descriptions-item>
          <el-descriptions-item label="IP地址">{{ currentConversion.ip || '-' }}</el-descriptions-item>
          <el-descriptions-item label="渠道ID">{{ currentConversion.gid || '-' }}</el-descriptions-item>
          <el-descriptions-item label="产品ID">{{ currentConversion.product_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户ID">{{ currentConversion.client_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(currentConversion.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="原始数据" :span="2" v-if="currentConversion.raw_data">
            <pre class="json-content">{{ formatJson(currentConversion.raw_data) }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <div v-else class="loading-placeholder">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
      <template #footer>
        <el-button type="primary" @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue';
import { 
  ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem, 
  ElInput, ElSelect, ElOption, ElTag, ElDialog, ElIcon, ElMessage, 
  ElDescriptions, ElDescriptionsItem, ElDatePicker, ElInputNumber, ElRow, ElCol
} from 'element-plus';
import { Search, Refresh, Loading } from '@element-plus/icons-vue';
import { getPostbackConversions, getPostbackStats } from '../../api/postback';
import { formatDateTime } from '../../utils/dateFormat';
import { useDevice } from '../../composables/useDevice';

// 设备检测
const { isMobile } = useDevice();

// 状态管理
const conversions = ref([]);
const loading = ref(false);
const stats = ref([]);
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
});

// 搜索表单
const searchForm = reactive({
  platform: '',
  event_name: '',
  product_id: null,
  client_id: null,
  start_date: '',
  end_date: ''
});

// 日期范围
const dateRange = ref(null);

// 详情对话框
const detailDialogVisible = ref(false);
const currentConversion = ref(null);

// 监听日期范围变化
watch(dateRange, (newVal) => {
  if (newVal && newVal.length === 2) {
    searchForm.start_date = newVal[0];
    searchForm.end_date = newVal[1];
  } else {
    searchForm.start_date = '';
    searchForm.end_date = '';
  }
});

// 监听分页变化
watch(() => pagination.page, () => {
  fetchConversions();
});

watch(() => pagination.pageSize, () => {
  pagination.page = 1;
  fetchConversions();
});

// 获取转化记录
const fetchConversions = async () => {
  loading.value = true;
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...searchForm
    };
    
    // 移除空值
    Object.keys(params).forEach(key => {
      if (params[key] === '' || params[key] === null || params[key] === undefined) {
        delete params[key];
      }
    });

    const response = await getPostbackConversions(params);
    conversions.value = response.data || [];
    pagination.total = response.total || 0;
  } catch (error) {
    // 错误已通过 isErrorHandled 处理
  } finally {
    loading.value = false;
  }
};

// 获取统计信息
const fetchStats = async () => {
  try {
    const params = {};
    if (searchForm.platform) {
      params.platform = searchForm.platform;
    }
    if (searchForm.start_date) {
      params.start_date = searchForm.start_date;
    }
    if (searchForm.end_date) {
      params.end_date = searchForm.end_date;
    }

    const response = await getPostbackStats(params);
    stats.value = response || [];
  } catch (error) {
    // 错误已通过 isErrorHandled 处理
  }
};

// 重置筛选
const resetFilter = () => {
  searchForm.platform = '';
  searchForm.event_name = '';
  searchForm.product_id = null;
  searchForm.client_id = null;
  searchForm.start_date = '';
  searchForm.end_date = '';
  dateRange.value = null;
  pagination.page = 1;
  fetchConversions();
  fetchStats();
};

// 查看详情
const handleViewDetail = (row) => {
  currentConversion.value = row;
  detailDialogVisible.value = true;
};

// 格式化货币
const formatCurrency = (value) => {
  if (!value && value !== 0) return '-';
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
};

// 格式化JSON
const formatJson = (jsonString) => {
  try {
    const obj = typeof jsonString === 'string' ? JSON.parse(jsonString) : jsonString;
    return JSON.stringify(obj, null, 2);
  } catch (e) {
    return jsonString;
  }
};

// 初始化
onMounted(() => {
  fetchConversions();
  fetchStats();
});
</script>

<style scoped>
.postback-management-container {
  padding: var(--spacing-lg);
}

.page-header {
  margin-bottom: var(--spacing-lg);
}

.page-header h1 {
  margin: 0 0 var(--spacing-md) 0;
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
}

.stats-info {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  margin-top: var(--spacing-sm);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.stat-label {
  color: var(--text-secondary);
}

.stat-value {
  font-weight: var(--font-weight-semibold);
  color: var(--primary-color);
}

.stat-unit {
  color: var(--text-secondary);
}

.stat-separator {
  margin: 0 var(--spacing-xs);
  color: var(--text-tertiary);
}

.filter-card {
  margin-bottom: var(--spacing-lg);
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.stats-card {
  margin-bottom: var(--spacing-lg);
}

.stats-header {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-lg);
}

.stat-card {
  background: var(--bg-light);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.stat-card-header {
  margin-bottom: var(--spacing-sm);
  padding-bottom: var(--spacing-xs);
  border-bottom: 1px solid var(--border-color);
}

.platform-name {
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-lg);
  color: var(--primary-color);
}

.stat-card-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-row .stat-label {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.stat-row .stat-value {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.stat-row .stat-value.highlight {
  color: var(--success-color);
  font-size: var(--font-size-lg);
}

.data-table-card {
  margin-bottom: var(--spacing-lg);
}

.data-table-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.data-table-card :deep(.el-table) {
  min-width: 1400px;
}

.table-header {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-lg);
}

.pagination-container {
  margin-top: var(--spacing-lg);
  display: flex;
  justify-content: flex-end;
}

.conversion-detail-content {
  max-height: 70vh;
  overflow-y: auto;
}

.json-content {
  background: var(--bg-light);
  padding: var(--spacing-md);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
}

.loading-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl);
  gap: var(--spacing-md);
}

.highlight {
  color: var(--success-color);
  font-weight: var(--font-weight-semibold);
}

/* 移动端优化 */
@media (max-width: 767px) {
  .postback-management-container {
    padding: var(--spacing-md);
  }

  .filter-form {
    flex-direction: column;
  }

  .date-range-item {
    width: 100%;
  }

  .date-picker-full {
    width: 100% !important;
  }

  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .data-table-card :deep(.el-table) {
    min-width: 1300px;
    font-size: 12px;
  }

  .data-table-card :deep(.el-table__cell) {
    padding: 8px 4px;
  }
}
</style>

