<template>
  <div class="third-party-report-management-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1>第三方上报日志</h1>
        <div class="stats-info" v-if="stats">
          <span class="stat-item">
            <span class="stat-label">总上报数：</span>
            <span class="stat-value">{{ stats.total || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">成功：</span>
            <span class="stat-value success">{{ stats.success || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">失败：</span>
            <span class="stat-value danger">{{ stats.failed || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">处理中：</span>
            <span class="stat-value warning">{{ stats.pending || 0 }}</span>
          </span>
        </div>
      </div>
    </div>

    <!-- 筛选控件 -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="来源">
          <el-select v-model="searchForm.source" placeholder="全部" clearable style="width: 150px;" name="source"
            popper-class="select-dropdown" :teleported="true">
            <el-option label="全部" value=""></el-option>
            <el-option label="短链接" value="short_link"></el-option>
            <el-option label="Postback" value="postback"></el-option>
            <el-option label="其他" value="unknown"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="广告ID">
          <el-input v-model="searchForm.adsid" placeholder="输入广告ID搜索" clearable @keyup.enter="fetchLogs"
            style="width: 250px;" name="adsid">
            <template #prefix>
              <el-icon :size="16">
                <Search />
              </el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="事件类型">
          <el-select v-model="searchForm.event" placeholder="全部" clearable style="width: 150px;" name="event"
            popper-class="select-dropdown" :teleported="true">
            <el-option label="全部" value=""></el-option>
            <el-option label="Purchase" value="Purchase"></el-option>
            <el-option label="Lead" value="Lead"></el-option>
            <el-option label="CompleteRegistration" value="CompleteRegistration"></el-option>
            <el-option label="ViewContent" value="ViewContent"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部" clearable style="width: 120px;" name="status"
            popper-class="select-dropdown" :teleported="true">
            <el-option label="全部" value=""></el-option>
            <el-option label="成功" value="success"></el-option>
            <el-option label="失败" value="failed"></el-option>
            <el-option label="处理中" value="pending"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围" class="date-range-item">
          <el-date-picker v-model="dateRange" name="dateRange" type="datetimerange" range-separator="至"
            start-placeholder="开始时间" end-placeholder="结束时间" format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss" style="width: 400px;" class="date-picker-full" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchLogs" :loading="loading" :icon="Search">
            查询
          </el-button>
          <el-button @click="resetFilter" :icon="Refresh">
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 日志数据表格 -->
    <el-card class="data-table-card" shadow="never">
      <template #header>
        <div class="table-header">
          <span>上报日志列表</span>
          <el-button type="text" :icon="Setting" @click="columnSettingVisible = true" style="float: right;">
            列设置
          </el-button>
        </div>
      </template>
      <el-table v-loading="loading" :data="logs" border stripe style="width: 100%">
        <el-table-column v-if="columnVisibility.id" prop="id" label="ID" width="80" align="center" />
        <el-table-column v-if="columnVisibility.source" prop="source" label="来源" width="120" align="center">
          <template #default="scope">
            <el-tag :type="getSourceTag(scope.row.source)" size="small">
              {{ getSourceLabel(scope.row.source) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.adsid" prop="adsid" label="广告ID" min-width="180"
          show-overflow-tooltip />
        <el-table-column v-if="columnVisibility.event" prop="event" label="事件类型" width="120" align="center">
          <template #default="scope">
            <el-tag size="small">{{ scope.row.event }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.status" prop="status" label="状态" width="90" align="center">
          <template #default="scope">
            <el-tag :type="getStatusTag(scope.row.status)" size="small">
              {{ getStatusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.attempt_count" prop="attempt_count" label="尝试次数" width="100"
          align="center" />
        <el-table-column v-if="columnVisibility.response_status" prop="response_status" label="响应状态码" width="120"
          align="center">
          <template #default="scope">
            <el-tag v-if="scope.row.response_status" :type="getResponseStatusTag(scope.row.response_status)"
              size="small">
              {{ scope.row.response_status }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.log_id" prop="log_id" label="日志ID" min-width="150"
          show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.log_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.use_hash" prop="use_hash" label="哈希处理" width="120" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.use_hash ? 'success' : 'info'" size="small">
              {{ scope.row.use_hash ? '已启用' : '已关闭' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.created_at" prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDateTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.report_success_time" prop="report_success_time" label="成功时间"
          width="180">
          <template #default="scope">
            {{ scope.row.report_success_time ? formatDateTime(scope.row.report_success_time) : '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.report_params" prop="report_params" label="完整上报参数" min-width="200" show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.report_params" class="report-params-preview">
              {{ (scope.row.report_params.length > 50) ? scope.row.report_params.substring(0, 50) + '...' : scope.row.report_params }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="scope">
            <el-button type="primary" link size="small" @click="handleViewDetail(scope.row)">
              详情
            </el-button>
            <el-button type="warning" link size="small" @click="handleEdit(scope.row)">
              编辑
            </el-button>
            <el-button v-if="scope.row.status === 'failed'" type="danger" link size="small"
              @click="handleRetry(scope.row)">
              重新上报
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]" :total="pagination.total"
          :layout="isMobile ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next, jumper'" />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog v-model="detailDialogVisible" title="上报日志详情" :width="isMobile ? '95%' : '1000px'"
      class="report-detail-dialog" :close-on-click-modal="false" :append-to-body="true">
      <div v-if="currentLog" class="report-detail-content">
        <el-descriptions :column="isMobile ? 1 : 2" border>
          <el-descriptions-item label="日志ID">{{ currentLog.id }}</el-descriptions-item>
          <el-descriptions-item label="来源">
            <el-tag :type="getSourceTag(currentLog.source)">
              {{ getSourceLabel(currentLog.source) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="广告ID">{{ currentLog.adsid }}</el-descriptions-item>
          <el-descriptions-item label="事件类型">
            <el-tag size="small">{{ currentLog.event }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusTag(currentLog.status)">
              {{ getStatusLabel(currentLog.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="尝试次数">{{ currentLog.attempt_count }} / {{ currentLog.max_attempts
            }}</el-descriptions-item>
          <el-descriptions-item :label="currentLog.use_hash ? '邮箱（已哈希）' : '邮箱'">
            {{ currentLog.email || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="currentLog.use_hash ? 'IP地址（已哈希）' : 'IP地址'">
            {{ currentLog.ip || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="currentLog.use_hash ? '手机号（已哈希）' : '手机号'">
            {{ currentLog.phone || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="哈希处理">
            <el-tag :type="currentLog.use_hash ? 'success' : 'info'">
              {{ currentLog.use_hash ? '已启用' : '已关闭' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="响应状态码">
            <el-tag v-if="currentLog.response_status" :type="getResponseStatusTag(currentLog.response_status)"
              size="small">
              {{ currentLog.response_status }}
            </el-tag>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="日志ID">{{ currentLog.log_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(currentLog.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="上报开始时间">
            {{ currentLog.report_start_time ? formatDateTime(currentLog.report_start_time) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="上报成功时间">
            {{ currentLog.report_success_time ? formatDateTime(currentLog.report_success_time) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="完成时间">
            {{ currentLog.completed_at ? formatDateTime(currentLog.completed_at) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="用户代理" :span="2">
            {{ currentLog.ua || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="完整上报参数" :span="2" v-if="currentLog.report_params">
            <pre class="json-content">{{ formatJson(currentLog.report_params) }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="响应内容" :span="2" v-if="currentLog.response_body">
            <pre class="json-content">{{ formatJson(currentLog.response_body) }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="错误信息" :span="2" v-if="currentLog.error_message">
            <el-alert type="error" :closable="false">
              {{ currentLog.error_message }}
            </el-alert>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <div v-else class="loading-placeholder">
        <el-icon class="is-loading">
          <Loading />
        </el-icon>
        <span>加载中...</span>
      </div>
      <template #footer>
        <el-button type="primary" @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑上报参数" :width="isMobile ? '95%' : '600px'" class="edit-dialog"
      :close-on-click-modal="false" :append-to-body="true">
      <el-form :model="editForm" label-width="120px">
        <el-form-item label="广告ID">
          <el-input v-model="editForm.adsid" placeholder="请输入广告ID" />
        </el-form-item>
        <el-form-item label="事件类型">
          <el-select v-model="editForm.event" placeholder="请选择事件类型" style="width: 100%;">
            <el-option label="Purchase" value="Purchase" />
            <el-option label="Lead" value="Lead" />
            <el-option label="CompleteRegistration" value="CompleteRegistration" />
            <el-option label="ViewContent" value="ViewContent" />
          </el-select>
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="editForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="IP地址">
          <el-input v-model="editForm.ip" placeholder="请输入IP地址" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="editForm.phone" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item label="用户代理">
          <el-input v-model="editForm.ua" type="textarea" :rows="3" placeholder="请输入用户代理" />
        </el-form-item>
        <el-form-item label="完整上报参数">
          <el-input v-model="editForm.report_params" type="textarea" :rows="4" placeholder="请输入完整上报参数（JSON格式）" />
        </el-form-item>
        <el-form-item label="哈希处理">
          <el-switch v-model="editForm.use_hash" />
          <span style="margin-left: 10px; color: var(--text-secondary);">
            开启后会对 email、ip、phone 进行 SHA256 哈希处理
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 列设置对话框 -->
    <el-dialog v-model="columnSettingVisible" title="列显示设置" width="500px" @close="saveColumnVisibility">
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="id" :disabled="true">ID（固定显示）</el-checkbox>
        <el-checkbox label="source">来源</el-checkbox>
        <el-checkbox label="adsid">广告ID</el-checkbox>
        <el-checkbox label="event">事件类型</el-checkbox>
        <el-checkbox label="status">状态</el-checkbox>
        <el-checkbox label="attempt_count">尝试次数</el-checkbox>
        <el-checkbox label="response_status">响应状态码</el-checkbox>
        <el-checkbox label="log_id">日志ID</el-checkbox>
        <el-checkbox label="use_hash">哈希处理</el-checkbox>
        <el-checkbox label="report_params">完整上报参数</el-checkbox>
        <el-checkbox label="created_at" :disabled="true">创建时间（固定显示）</el-checkbox>
        <el-checkbox label="report_success_time">成功时间</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import {
  ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem,
  ElInput, ElSelect, ElOption, ElTag, ElDialog, ElIcon, ElMessage, ElMessageBox,
  ElDescriptions, ElDescriptionsItem, ElDatePicker, ElAlert, ElCheckboxGroup, ElCheckbox,
  ElSwitch
} from 'element-plus';
import { Search, Refresh, Loading, Setting } from '@element-plus/icons-vue';
import { useAuthStore } from '../../store';
import { getThirdPartyReports, getThirdPartyReport, getThirdPartyReportStats, updateThirdPartyReport, retryThirdPartyReport } from '../../api/thirdPartyReport';
import { formatDateTime } from '../../utils/dateFormat';
import { useDevice } from '../../composables/useDevice';
import { logger } from '../../utils/logger';

// 设备检测
const { isMobile } = useDevice();

// 状态管理
const logs = ref([]);
const loading = ref(false);
const stats = ref(null);
const columnSettingVisible = ref(false);
const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
});

// 列显示状态（默认全部显示）
const getDefaultColumnVisibility = () => ({
  id: true,
  source: true,
  adsid: true,
  event: true,
  status: true,
  attempt_count: true,
  response_status: true,
  log_id: true,
  use_hash: true,
  created_at: true,
  report_success_time: true,
  report_params: false
})

const columnVisibility = reactive(getDefaultColumnVisibility())

// 计算属性：将对象转换为数组，用于 el-checkbox-group
const columnVisibilityArray = computed({
  get: () => {
    return Object.keys(columnVisibility).filter(key => columnVisibility[key])
  },
  set: (value) => {
    Object.keys(columnVisibility).forEach(key => {
      columnVisibility[key] = value.includes(key)
    })
  }
})

// 从localStorage加载列显示设置
const loadColumnVisibility = () => {
  try {
    const saved = localStorage.getItem('thirdPartyReportManagement_columnVisibility')
    if (saved) {
      const savedVisibility = JSON.parse(saved)
      Object.assign(columnVisibility, getDefaultColumnVisibility(), savedVisibility)
      columnVisibility.id = true
      columnVisibility.created_at = true
    }
  } catch (error) {
    logger.error('加载列显示设置失败:', error)
  }
}

// 保存列显示设置到localStorage
const saveColumnVisibility = () => {
  try {
    const toSave = {
      source: columnVisibility.source,
      adsid: columnVisibility.adsid,
      event: columnVisibility.event,
      status: columnVisibility.status,
      attempt_count: columnVisibility.attempt_count,
      response_status: columnVisibility.response_status,
      log_id: columnVisibility.log_id,
      use_hash: columnVisibility.use_hash,
      report_params: columnVisibility.report_params,
      report_success_time: columnVisibility.report_success_time
    }
    localStorage.setItem('thirdPartyReportManagement_columnVisibility', JSON.stringify(toSave))
    columnSettingVisible.value = false
    ElMessage.success('列显示设置已保存')
  } catch (error) {
    logger.error('保存列显示设置失败:', error)
    ElMessage.error('保存设置失败')
  }
}

// 筛选表单
const searchForm = reactive({
  source: '',
  adsid: '',
  event: '',
  status: ''
});

// 时间范围 - 默认显示本月数据
const getCurrentMonthRange = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();

  const startDate = new Date(year, month, 1, 0, 0, 0);
  const lastDay = new Date(year, month + 1, 0, 23, 59, 59);

  const formatDateTime = (date) => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    const h = String(date.getHours()).padStart(2, '0');
    const min = String(date.getMinutes()).padStart(2, '0');
    const s = String(date.getSeconds()).padStart(2, '0');
    return `${y}-${m}-${d}T${h}:${min}:${s}`;
  };

  return [
    formatDateTime(startDate),
    formatDateTime(lastDay)
  ];
};

const dateRange = ref(getCurrentMonthRange());

// 详情对话框
const detailDialogVisible = ref(false);
const currentLog = ref(null);

// 编辑对话框
const editDialogVisible = ref(false);
const editLogId = ref(null);
const editForm = reactive({
  adsid: '',
  event: '',
  email: '',
  ip: '',
  phone: '',
  ua: '',
  report_params: '',
  use_hash: true
});

// 获取来源标签类型
const getSourceTag = (source) => {
  const tagMap = {
    'short_link': 'primary',
    'postback': 'success',
    'unknown': 'info'
  };
  return tagMap[source] || '';
};

// 获取来源显示标签
const getSourceLabel = (source) => {
  const labelMap = {
    'short_link': '短链接',
    'postback': 'Postback',
    'unknown': '其他'
  };
  return labelMap[source] || source;
};

// 获取状态标签类型
const getStatusTag = (status) => {
  const tagMap = {
    'success': 'success',
    'failed': 'danger',
    'pending': 'warning'
  };
  return tagMap[status] || '';
};

// 获取状态显示标签
const getStatusLabel = (status) => {
  const labelMap = {
    'success': '成功',
    'failed': '失败',
    'pending': '处理中'
  };
  return labelMap[status] || status;
};

// 获取响应状态码标签类型
const getResponseStatusTag = (statusCode) => {
  if (statusCode >= 200 && statusCode < 300) return 'success';
  if (statusCode >= 300 && statusCode < 400) return 'info';
  if (statusCode >= 400 && statusCode < 500) return 'warning';
  if (statusCode >= 500) return 'danger';
  return '';
};

// 格式化JSON
const formatJson = (jsonString) => {
  try {
    let obj = typeof jsonString === 'string' ? JSON.parse(jsonString) : jsonString;
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(jsonString);
  }
};

// 获取日志列表
const fetchLogs = async () => {
  try {
    loading.value = true;

    if (!authStore.isAuthenticated) {
      ElMessage.warning('登录已过期，请重新登录');
      router.push('/login').catch(() => {
        window.location.href = '/login';
      });
      return;
    }

    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(searchForm.source && { source: searchForm.source }),
      ...(searchForm.adsid && { adsid: searchForm.adsid }),
      ...(searchForm.event && { event: searchForm.event }),
      ...(searchForm.status && { status: searchForm.status }),
      ...(dateRange.value && dateRange.value.length === 2 && {
        start_date: dateRange.value[0],
        end_date: dateRange.value[1]
      })
    };

    const response = await getThirdPartyReports(params);
    logs.value = response.data || [];
    pagination.total = response.total || 0;

    await fetchStats();
  } catch (error) {
  } finally {
    loading.value = false;
  }
};

// 获取统计信息
const fetchStats = async () => {
  try {
    const params = {};
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0];
      params.end_date = dateRange.value[1];
    }
    const data = await getThirdPartyReportStats(params);
    stats.value = data;
  } catch (error) {
  }
};

// 重置筛选条件
const resetFilter = () => {
  searchForm.source = '';
  searchForm.adsid = '';
  searchForm.event = '';
  searchForm.status = '';
  dateRange.value = getCurrentMonthRange();
  pagination.page = 1;
  fetchLogs();
};

// 监听分页变化
let isInitializing = true;

watch(
  () => [pagination.page, pagination.pageSize],
  ([newPage, newSize], [oldPage, oldSize]) => {
    if (isInitializing) {
      return;
    }

    if (newPage !== oldPage && newSize === oldSize) {
      fetchLogs();
    } else if (newSize !== oldSize) {
      if (pagination.page !== 1) {
        pagination.page = 1;
      } else {
        fetchLogs();
      }
    }
  },
  { flush: 'post' }
);

// 查看详情
const handleViewDetail = async (log) => {
  try {
    const data = await getThirdPartyReport(log.id);
    currentLog.value = data;
    detailDialogVisible.value = true;
  } catch (error) {
  }
};

// 编辑日志
const handleEdit = (log) => {
  editLogId.value = log.id;
  editForm.adsid = log.adsid || '';
  editForm.event = log.event || '';
  editForm.email = log.email || '';
  editForm.ip = log.ip || '';
  editForm.phone = log.phone || '';
  editForm.ua = log.ua || '';
  editForm.report_params = log.report_params || '';
  editForm.use_hash = log.use_hash !== false;
  editDialogVisible.value = true;
};

// 保存编辑
const handleSaveEdit = async () => {
  try {
    const params = {};
    if (editForm.adsid) params.adsid = editForm.adsid;
    if (editForm.event) params.event = editForm.event;
    if (editForm.email) params.email = editForm.email;
    if (editForm.ip) params.ip = editForm.ip;
    if (editForm.phone) params.phone = editForm.phone;
    if (editForm.ua) params.ua = editForm.ua;
    if (editForm.report_params) params.report_params = editForm.report_params;
    params.use_hash = editForm.use_hash;

    await updateThirdPartyReport(editLogId.value, params);
    ElMessage.success('更新成功');
    editDialogVisible.value = false;
    fetchLogs();
  } catch (error) {
    ElMessage.error('更新失败');
  }
};

// 重新上报
const handleRetry = async (log) => {
  try {
    await ElMessageBox.confirm(
      '确定要重新上报这条日志吗？',
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    await retryThirdPartyReport(log.id);
    ElMessage.success('已触发重新上报，请稍后刷新查看结果');
    fetchLogs();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('重新上报失败');
    }
  }
};

// 路由实例
const router = useRouter();
const authStore = useAuthStore();

// 初始化
onMounted(async () => {
  loadColumnVisibility()
  await nextTick();

  setTimeout(async () => {
    try {
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => {
          reject(new Error('页面加载超时，请检查网络连接或刷新页面'));
        }, 20000);
      });

      await Promise.race([
        fetchLogs(),
        timeoutPromise
      ]);
    } catch (error) {
      if (error.message && error.message.includes('超时')) {
        ElMessage.error(error.message);
        loading.value = false;
      } else {
        loading.value = false;
      }
    } finally {
      await nextTick();
      isInitializing = false;
    }
  }, 0);
});
</script>

<style scoped>
.third-party-report-management-container {
  width: 100%;
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-xl);
  padding: var(--spacing-xl);
  background-color: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.page-header h1 {
  margin: 0 0 var(--spacing-md) 0;
  font-size: var(--font-size-title);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.stats-info {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-lg);
  padding: var(--spacing-sm) 0;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-base);
}

.stat-label {
  color: var(--text-secondary);
}

.stat-value {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.stat-value.success {
  color: var(--success-color);
}

.stat-value.danger {
  color: var(--danger-color);
}

.stat-value.warning {
  color: var(--warning-color);
}

.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.data-table-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
  overflow: hidden;
}

.data-table-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-lg);
  color: var(--text-primary);
}

.pagination-container {
  margin-top: var(--spacing-lg);
  padding: var(--spacing-lg) 0;
  text-align: right;
  border-top: 1px solid var(--border-lighter);
}

@media (max-width: 767px) {
  .third-party-report-management-container {
    padding: var(--spacing-md);
  }

  .page-header {
    padding: var(--spacing-md);
    margin-bottom: var(--spacing-md);
  }

  .page-header h1 {
    font-size: var(--font-size-xl);
    margin-bottom: var(--spacing-sm);
  }

  .stats-info {
    flex-direction: column;
    gap: var(--spacing-sm);
    margin-top: var(--spacing-sm);
  }

  .stat-item {
    font-size: var(--font-size-sm);
  }

  .filter-card {
    margin-bottom: var(--spacing-md);
    overflow: visible;
  }

  .filter-card :deep(.el-card__body) {
    padding: var(--spacing-md);
    overflow: visible;
    max-height: none;
  }

  .data-table-card {
    margin-bottom: var(--spacing-md);
  }

  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .el-table {
    font-size: var(--font-size-sm);
    min-width: 1000px;
  }

  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-xs) var(--spacing-sm);
    word-break: break-word;
  }

  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
  }

  .pagination-container {
    margin-top: var(--spacing-md);
    justify-content: center;
  }
}

.filter-form {
  margin: 0;
}

.report-detail-dialog :deep(.el-dialog__body) {
  padding: var(--spacing-xl);
  max-height: calc(100vh - 200px);
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.report-detail-content {
  width: 100%;
}

.report-detail-content :deep(.el-descriptions) {
  width: 100%;
}

.report-detail-content :deep(.el-descriptions__table) {
  width: 100%;
  table-layout: auto;
}

.report-detail-content :deep(.el-descriptions__label),
.report-detail-content :deep(.el-descriptions-item__label) {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  min-width: 120px;
}

.report-detail-content :deep(.el-descriptions__content),
.report-detail-content :deep(.el-descriptions-item__content) {
  color: var(--text-regular);
  word-break: break-word;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.loading-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xxxxl);
  gap: var(--spacing-md);
  color: var(--text-secondary);
}

.loading-placeholder .is-loading {
  animation: rotating 2s linear infinite;
  font-size: var(--font-size-xl);
}

@keyframes rotating {
  0% {
    transform: rotate(0deg);
  }

  100% {
    transform: rotate(360deg);
  }
}

.json-content {
  background: var(--bg-secondary);
  padding: var(--spacing-md);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  max-height: 400px;
  overflow: auto;
  margin: 0;
  word-break: break-word;
  word-wrap: break-word;
  overflow-wrap: break-word;
  white-space: pre-wrap;
  color: var(--text-primary);
  line-height: var(--line-height-loose);
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}

@media (max-width: 767px) {
  .filter-form {
    display: flex !important;
    flex-direction: column !important;
  }

  .filter-form :deep(.el-form--inline) {
    display: flex !important;
    flex-direction: column !important;
  }

  .filter-form :deep(.el-form-item) {
    width: 100% !important;
    margin-right: 0 !important;
    margin-bottom: var(--spacing-md) !important;
    display: flex !important;
    flex-direction: column !important;
  }

  .filter-form :deep(.el-form-item__label) {
    width: 100% !important;
    text-align: left !important;
    margin-bottom: var(--spacing-xs) !important;
    padding: 0 !important;
    margin-right: 0 !important;
    float: none !important;
    justify-content: flex-start !important;
    align-items: flex-start !important;
    display: block !important;
  }

  .filter-form :deep(.el-form-item__content) {
    width: 100% !important;
    margin-left: 0 !important;
    flex: 1 !important;
  }

  .filter-form :deep(.el-input),
  .filter-form :deep(.el-select),
  .filter-form :deep(.el-date-editor),
  .filter-form :deep(.el-date-picker) {
    width: 100% !important;
    max-width: 100% !important;
  }

  .filter-form :deep(.el-input__wrapper) {
    min-height: var(--touch-target-size);
    width: 100% !important;
  }

  .filter-form :deep(.el-select .el-input__wrapper) {
    min-height: var(--touch-target-size);
    width: 100% !important;
  }

  .filter-form :deep(.el-date-editor.el-input__wrapper) {
    width: 100% !important;
    min-height: var(--touch-target-size);
  }

  .date-range-item :deep(.el-form-item__content) {
    width: 100% !important;
  }

  .date-picker-full {
    width: 100% !important;
    max-width: 100% !important;
  }

  .date-picker-full :deep(.el-input__wrapper) {
    width: 100% !important;
  }

  .date-picker-full :deep(.el-range-separator) {
    width: auto !important;
    padding: 0 var(--spacing-xs);
  }

  .date-picker-full :deep(.el-range-input) {
    width: calc(50% - 20px) !important;
    flex: 1 !important;
  }

  .filter-form :deep(.el-form-item:last-child) {
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm);
    margin-top: var(--spacing-sm);
    margin-bottom: 0 !important;
    width: 100% !important;
  }

  .filter-form :deep(.el-form-item:last-child .el-form-item__label) {
    display: none !important;
  }

  .filter-form :deep(.el-form-item:last-child .el-form-item__content) {
    width: 100% !important;
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm);
    margin-left: 0 !important;
  }

  .filter-form :deep(.el-form-item:last-child .el-button) {
    flex: 1;
    min-height: var(--touch-target-size);
    width: auto;
    white-space: nowrap;
  }

  .filter-form :deep(.el-form-item:last-child .el-button .el-icon) {
    margin-right: var(--spacing-xs);
  }

  .el-table :deep(.el-button--link) {
    min-height: var(--touch-target-size);
    padding: var(--spacing-xs) var(--spacing-sm);
  }
}
</style>
