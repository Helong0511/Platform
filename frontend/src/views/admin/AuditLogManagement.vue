<template>
  <div class="audit-log-management-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1>操作日志</h1>
        <div class="stats-info" v-if="stats">
          <span class="stat-item">
            <span class="stat-label">总日志数：</span>
            <span class="stat-value">{{ stats.total_count || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">成功：</span>
            <span class="stat-value success">{{ stats.success_count || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">失败：</span>
            <span class="stat-value danger">{{ stats.failure_count || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">活跃用户：</span>
            <span class="stat-value">{{ stats.active_users_count || 0 }}</span>
          </span>
        </div>
      </div>
    </div>

    <!-- 筛选控件 -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="用户名">
          <el-input 
            v-model="searchForm.username" 
            placeholder="输入用户名搜索" 
            clearable
            @keyup.enter="fetchLogs"
            style="width: 200px;"
            name="username"
          >
            <template #prefix>
              <el-icon :size="16"><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="操作类型">
          <el-select v-model="searchForm.action_type" placeholder="全部" clearable style="width: 150px;" name="action_type">
            <el-option label="全部" value=""></el-option>
            <el-option label="登录" value="LOGIN"></el-option>
            <el-option label="登出" value="LOGOUT"></el-option>
            <el-option label="增加" value="CREATE"></el-option>
            <el-option label="删除" value="DELETE"></el-option>
            <el-option label="修改" value="UPDATE"></el-option>
            <el-option label="导入" value="IMPORT"></el-option>
            <el-option label="导出" value="EXPORT"></el-option>
            <el-option label="激活" value="ACTIVATE"></el-option>
            <el-option label="禁用" value="DEACTIVATE"></el-option>
            <el-option label="定时任务运行" value="TASK_RUN"></el-option>
            <el-option label="API访问" value="API_ACCESS"></el-option>
            <el-option label="程序运行错误" value="RUNTIME_ERROR"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="资源类型">
          <el-select v-model="searchForm.resource_type" placeholder="全部" clearable style="width: 150px;" name="resource_type">
            <el-option label="全部" value=""></el-option>
            <el-option label="用户" value="USER"></el-option>
            <el-option label="客户" value="CLIENT"></el-option>
            <el-option label="产品" value="PRODUCT"></el-option>
            <el-option label="广告数据" value="AD_DATA"></el-option>
            <el-option label="定时任务" value="SCHEDULED_TASK"></el-option>
            <el-option label="系统" value="SYSTEM"></el-option>
            <el-option label="前端" value="FRONTEND"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="IP地址">
          <el-input 
            v-model="searchForm.ip_address" 
            placeholder="输入IP地址" 
            clearable
            style="width: 150px;"
            name="ip_address"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.success" placeholder="全部" clearable style="width: 120px;" name="success">
            <el-option label="全部" value=""></el-option>
            <el-option label="成功" :value="true"></el-option>
            <el-option label="失败" :value="false"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围" class="date-range-item">
          <el-date-picker
            v-model="dateRange"
            name="dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 400px;"
            class="date-picker-full"
          />
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
          <span>日志列表</span>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="logs"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" width="120">
          <template #default="scope">
            {{ scope.row.username || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="action_type" label="操作类型" width="120">
          <template #default="scope">
            <el-tag :type="getActionTypeTag(scope.row.action_type)">
              {{ getActionTypeLabel(scope.row.action_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="resource_type" label="资源类型" width="120">
          <template #default="scope">
            {{ scope.row.resource_type || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="resource_name" label="资源名称" min-width="150" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.resource_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP地址" width="130" />
        <el-table-column prop="request_method" label="请求方法" width="100">
          <template #default="scope">
            <el-tag v-if="scope.row.request_method" size="small">
              {{ scope.row.request_method }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="request_path" label="请求路径" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status_code" label="状态码" width="100">
          <template #default="scope">
            <el-tag 
              v-if="scope.row.status_code" 
              :type="getStatusCodeTag(scope.row.status_code)"
              size="small"
            >
              {{ scope.row.status_code }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="success" label="状态" width="80">
          <template #default="scope">
            <el-tag :type="scope.row.success ? 'success' : 'danger'" size="small">
              {{ scope.row.success ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180">
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
      title="日志详情"
      :width="isMobile ? '95%' : '900px'"
      class="log-detail-dialog"
      :close-on-click-modal="false"
    >
      <div v-if="currentLog" class="log-detail-content">
        <el-descriptions :column="isMobile ? 1 : 2" border>
        <el-descriptions-item label="日志ID">{{ currentLog.id }}</el-descriptions-item>
        <el-descriptions-item label="用户名">{{ currentLog.username || '-' }}</el-descriptions-item>
        <el-descriptions-item label="操作类型">
          <el-tag :type="getActionTypeTag(currentLog.action_type)">
            {{ getActionTypeLabel(currentLog.action_type) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="资源类型">{{ currentLog.resource_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="资源ID">{{ currentLog.resource_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="资源名称">{{ currentLog.resource_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="IP地址">{{ currentLog.ip_address || '-' }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="currentLog.success ? 'success' : 'danger'">
            {{ currentLog.success ? '成功' : '失败' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="请求方法">{{ currentLog.request_method || '-' }}</el-descriptions-item>
        <el-descriptions-item label="请求路径">{{ currentLog.request_path || '-' }}</el-descriptions-item>
        <el-descriptions-item label="状态码">
          <el-tag v-if="currentLog.status_code" :type="getStatusCodeTag(currentLog.status_code)">
            {{ currentLog.status_code }}
          </el-tag>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatDateTime(currentLog.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="用户代理" :span="2">
          {{ currentLog.user_agent || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="请求参数" :span="2">
          <pre v-if="currentLog.request_params" class="json-content">{{ formatJson(currentLog.request_params) }}</pre>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="错误信息" :span="2" v-if="currentLog.error_message">
          <el-alert type="error" :closable="false">
            {{ currentLog.error_message }}
          </el-alert>
        </el-descriptions-item>
        <el-descriptions-item label="详细信息" :span="2" v-if="currentLog.details">
          <pre class="json-content">{{ formatJson(currentLog.details) }}</pre>
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
import { ref, reactive, onMounted, computed, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { 
  ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem, 
  ElInput, ElSelect, ElOption, ElTag, ElDialog, ElIcon, ElMessage, 
  ElDescriptions, ElDescriptionsItem, ElDatePicker, ElAlert
} from 'element-plus';
import { Search, Refresh, Loading } from '@element-plus/icons-vue';
import { useAuthStore } from '../../store';
import { getAuditLogs, getAuditLog, getAuditLogStats } from '../../api/auditLog';
import { formatDateTime } from '../../utils/dateFormat';
import { useDevice } from '../../composables/useDevice';

// 设备检测
const { isMobile } = useDevice();

// 状态管理
const logs = ref([]);
const loading = ref(false);
const stats = ref(null);
const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
});

// 筛选表单
const searchForm = reactive({
  username: '',
  action_type: '',
  resource_type: '',
  ip_address: '',
  success: null
});

// 时间范围 - 默认显示本月数据
const getCurrentMonthRange = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  
  // 本月第一天 00:00:00
  const startDate = new Date(year, month, 1, 0, 0, 0);
  // 本月最后一天 23:59:59
  const lastDay = new Date(year, month + 1, 0, 23, 59, 59);
  
  // 格式化为 YYYY-MM-DDTHH:mm:ss 格式（Element Plus 日期选择器期望的格式）
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

// 获取操作类型标签类型
const getActionTypeTag = (actionType) => {
  const tagMap = {
    'LOGIN': 'success',
    'LOGOUT': 'info',
    'CREATE': 'success',
    'UPDATE': 'warning',
    'DELETE': 'danger',
    'IMPORT': 'success',
    'EXPORT': 'info',
    'ACTIVATE': 'success',
    'DEACTIVATE': 'warning',
    'TASK_RUN': 'primary',
    'API_ACCESS': '',
    'RUNTIME_ERROR': 'danger'
  };
  return tagMap[actionType] || '';
};

// 获取操作类型显示标签
const getActionTypeLabel = (actionType) => {
  const labelMap = {
    'LOGIN': '登录',
    'LOGOUT': '登出',
    'CREATE': '增加',
    'UPDATE': '修改',
    'DELETE': '删除',
    'IMPORT': '导入',
    'EXPORT': '导出',
    'ACTIVATE': '激活',
    'DEACTIVATE': '禁用',
    'TASK_RUN': '定时任务运行',
    'API_ACCESS': 'API访问',
    'RUNTIME_ERROR': '程序运行错误'
  };
  return labelMap[actionType] || actionType;
};

// 获取状态码标签类型
const getStatusCodeTag = (statusCode) => {
  if (statusCode >= 200 && statusCode < 300) return 'success';
  if (statusCode >= 300 && statusCode < 400) return 'info';
  if (statusCode >= 400 && statusCode < 500) return 'warning';
  if (statusCode >= 500) return 'danger';
  return '';
};

// 格式化JSON
const formatJson = (jsonString) => {
  try {
    // 首先尝试解析为JSON
    let obj = typeof jsonString === 'string' ? JSON.parse(jsonString) : jsonString;
    
    // 递归格式化对象，美化日期显示
    const formatValue = (value) => {
      if (value === null || value === undefined) {
        return value;
      }
      if (typeof value === 'string') {
        // 检查是否是日期格式字符串（YYYY-MM-DD 或 ISO 格式）
        const dateMatch = value.match(/^(\d{4}-\d{2}-\d{2})(T\d{2}:\d{2}:\d{2})?/);
        if (dateMatch) {
          return dateMatch[1]; // 只返回日期部分
        }
        // 检查是否是 Python datetime.date 格式：datetime.date(2025, 9, 30)
        const pythonDateMatch = value.match(/datetime\.date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)/);
        if (pythonDateMatch) {
          const year = pythonDateMatch[1];
          const month = String(pythonDateMatch[2]).padStart(2, '0');
          const day = String(pythonDateMatch[3]).padStart(2, '0');
          return `${year}-${month}-${day}`;
        }
      }
      if (Array.isArray(value)) {
        return value.map(formatValue);
      }
      if (typeof value === 'object') {
        const formatted = {};
        for (const [key, val] of Object.entries(value)) {
          formatted[key] = formatValue(val);
        }
        return formatted;
      }
      return value;
    };
    
    const formattedObj = formatValue(obj);
    return JSON.stringify(formattedObj, null, 2);
  } catch {
    // 如果JSON解析失败，可能是Python字典字符串格式
    // 尝试提取并格式化其中的日期
    if (typeof jsonString === 'string') {
      // 替换 Python datetime.date 格式为 ISO 日期格式
      let formatted = jsonString.replace(
        /datetime\.date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)/g,
        (match, year, month, day) => {
          const monthStr = String(month).padStart(2, '0');
          const dayStr = String(day).padStart(2, '0');
          return `"${year}-${monthStr}-${dayStr}"`;
        }
      );
      
      // 尝试将单引号替换为双引号（Python字典格式）
      formatted = formatted.replace(/'/g, '"');
      
      // 尝试再次解析为JSON
      try {
        const obj = JSON.parse(formatted);
        return JSON.stringify(obj, null, 2);
      } catch {
        // 如果还是失败，返回原始字符串（但已替换日期格式）
        return formatted;
      }
    }
    return String(jsonString);
  }
};

// 获取日志列表
const fetchLogs = async () => {
  try {
    loading.value = true;
    
    // 检查认证状态
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
      ...(searchForm.username && { username: searchForm.username }),
      ...(searchForm.action_type && { action_type: searchForm.action_type }),
      ...(searchForm.resource_type && { resource_type: searchForm.resource_type }),
      ...(searchForm.ip_address && { ip_address: searchForm.ip_address }),
      ...(searchForm.success !== null && searchForm.success !== '' && { success: searchForm.success }),
      ...(dateRange.value && dateRange.value.length === 2 && {
        start_date: dateRange.value[0],
        end_date: dateRange.value[1]
      })
    };

    const response = await getAuditLogs(params);
    logs.value = response.data || [];
    pagination.total = response.total || 0;
    
    // 同时更新统计信息（使用相同的日期范围）
    await fetchStats();
  } catch (error) {
    // 错误已在API中处理
  } finally {
    loading.value = false;
  }
};

// 获取统计信息
const fetchStats = async () => {
  try {
    // 使用当前选择的日期范围（默认本月）
    const params = {};
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0];
      params.end_date = dateRange.value[1];
    }
    const data = await getAuditLogStats(params);
    stats.value = data;
  } catch (error) {
    // 静默失败
  }
};

// 重置筛选条件
const resetFilter = () => {
  searchForm.username = '';
  searchForm.action_type = '';
  searchForm.resource_type = '';
  searchForm.ip_address = '';
  searchForm.success = null;
  dateRange.value = getCurrentMonthRange();  // 重置为本月
  pagination.page = 1;
  fetchLogs();
};

// 监听分页变化
let isInitializing = true;

watch(
  () => [pagination.page, pagination.pageSize],
  ([newPage, newSize], [oldPage, oldSize]) => {
    // 跳过初始化时的触发
    if (isInitializing) {
      return;
    }
    
    // 如果只是页码变化，直接刷新
    if (newPage !== oldPage && newSize === oldSize) {
      fetchLogs();
    }
    // 如果每页条数变化，重置到第一页并刷新
    else if (newSize !== oldSize) {
      if (pagination.page !== 1) {
        pagination.page = 1;
      } else {
        // 如果已经在第一页，直接刷新
        fetchLogs();
      }
    }
  },
  { flush: 'post' }
);

// 查看详情
const handleViewDetail = async (log) => {
  try {
    const data = await getAuditLog(log.id);
    currentLog.value = data;
    detailDialogVisible.value = true;
  } catch (error) {
    // 错误已在API中处理
  }
};

// 路由实例
const router = useRouter();
const authStore = useAuthStore();

// 初始化
onMounted(async () => {
  // 路由守卫已经处理了认证检查，这里不需要重复检查
  // 延迟加载数据，让页面先渲染出来
  await nextTick();
  
  setTimeout(async () => {
    try {
      // 设置超时保护（20秒）
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => {
          reject(new Error('页面加载超时，请检查网络连接或刷新页面'));
        }, 20000);
      });
      
      // fetchLogs 内部会调用 fetchStats，所以只需要调用 fetchLogs
      await Promise.race([
        fetchLogs(),
        timeoutPromise
      ]);
    } catch (error) {
      // 超时或其他错误
      if (error.message && error.message.includes('超时')) {
        ElMessage.error(error.message);
        loading.value = false;
      } else if (error.response?.status === 401) {
        // 401错误已在拦截器中处理
        loading.value = false;
      } else {
        // 其他错误已在API中处理
        loading.value = false;
      }
    } finally {
      // 初始化完成后，允许 watch 触发
      await nextTick();
      isInitializing = false;
    }
  }, 0);
});
</script>

<style scoped>
.audit-log-management-container {
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

.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
  overflow: visible;
}

.filter-card :deep(.el-card__body) {
  overflow: visible;
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

/* 移动端优化 */
@media (max-width: 767px) {
  .audit-log-management-container {
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
    overflow: visible; /* 确保内容不被裁剪 */
  }
  
  .filter-card :deep(.el-card__body) {
    padding: var(--spacing-md);
    overflow: visible; /* 移除滚动条 */
    max-height: none; /* 移除高度限制 */
  }
  
  .data-table-card {
    margin-bottom: var(--spacing-md);
  }
  
  /* 移动端表格卡片优化 - 支持横向滚动 */
  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  /* 移动端表格优化 */
  .el-table {
    font-size: var(--font-size-sm);
    min-width: 800px; /* 确保表格有最小宽度，可以横向滚动 */
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
  
  .el-table :deep(.el-table__header-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .el-table :deep(.el-table__body-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .pagination-container {
    margin-top: var(--spacing-md);
    justify-content: center;
  }
  
  /* 移动端分页组件优化 */
  .pagination-component {
    flex-wrap: wrap;
    justify-content: center;
    font-size: var(--font-size-sm);
  }
  
  .pagination-component :deep(.el-pagination__total) {
    margin-right: var(--spacing-sm);
    font-size: var(--font-size-sm);
  }
  
  .pagination-component :deep(.btn-prev),
  .pagination-component :deep(.btn-next),
  .pagination-component :deep(.el-pager li) {
    min-width: var(--touch-target-size);
    min-height: var(--touch-target-size);
    font-size: var(--font-size-sm);
  }
  
  /* 移动端对话框优化 */
  .log-detail-dialog :deep(.el-dialog) {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    height: 100vh !important;
    max-height: 100vh !important;
    border-radius: 0 !important;
    display: flex !important;
    flex-direction: column !important;
  }
  
  .log-detail-dialog :deep(.el-dialog__header) {
    padding: var(--spacing-md) var(--spacing-lg);
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-lighter);
    background-color: var(--bg-primary);
    position: sticky;
    top: 0;
    z-index: 10;
  }
  
  .log-detail-dialog :deep(.el-dialog__title) {
    font-size: var(--font-size-lg);
    font-weight: var(--font-weight-semibold);
    color: var(--text-primary);
  }
  
  .log-detail-dialog :deep(.el-dialog__headerbtn) {
    top: var(--spacing-md);
    right: var(--spacing-lg);
    width: var(--touch-target-size);
    height: var(--touch-target-size);
  }
  
  .log-detail-dialog :deep(.el-dialog__close) {
    font-size: var(--font-size-lg);
  }
  
  .log-detail-dialog :deep(.el-dialog__body) {
    padding: var(--spacing-md);
    max-height: none !important;
    flex: 1;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior: contain;
  }
  
  .log-detail-dialog :deep(.el-dialog__footer) {
    padding: var(--spacing-md) var(--spacing-lg);
    flex-shrink: 0;
    border-top: 1px solid var(--border-lighter);
    background-color: var(--bg-primary);
    position: sticky;
    bottom: 0;
    z-index: 10;
  }
  
  .log-detail-dialog :deep(.el-dialog__footer .el-button) {
    width: 100%;
    min-height: var(--touch-target-size);
    font-size: var(--font-size-base);
    padding: var(--spacing-md) var(--spacing-lg);
  }
  
  /* 移动端描述列表优化 - 单列显示 */
  .log-detail-content :deep(.el-descriptions) {
    font-size: var(--font-size-sm);
    width: 100%;
  }
  
  .log-detail-content :deep(.el-descriptions__table) {
    width: 100%;
    border-collapse: collapse;
  }
  
  .log-detail-content :deep(.el-descriptions__row) {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    border-bottom: 1px solid var(--border-lighter);
    padding: var(--spacing-md) 0;
  }
  
  .log-detail-content :deep(.el-descriptions__row:last-child) {
    border-bottom: none;
  }
  
  .log-detail-content :deep(.el-descriptions-item) {
    width: 100% !important;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    padding: 0;
    margin: 0;
    border: none !important;
  }
  
  .log-detail-content :deep(.el-descriptions-item__label) {
    width: 100% !important;
    min-width: auto !important;
    max-width: none !important;
    flex-shrink: 0 !important;
    text-align: left !important;
    font-weight: var(--font-weight-semibold) !important;
    font-size: var(--font-size-sm) !important;
    color: var(--text-primary) !important;
    margin-bottom: var(--spacing-xs) !important;
    margin-right: 0 !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    line-height: 1.5 !important;
  }
  
  .log-detail-content :deep(.el-descriptions-item__content) {
    width: 100% !important;
    flex: 1 !important;
    min-width: 0 !important;
    text-align: left !important;
    word-break: break-word !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    font-size: var(--font-size-sm) !important;
    line-height: 1.6 !important;
    color: var(--text-regular) !important;
  }
  
  /* 移动端标签优化 */
  .log-detail-content :deep(.el-tag) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs) var(--spacing-sm);
    min-height: auto;
    line-height: 1.4;
  }
  
  /* JSON 内容移动端优化 */
  .json-content {
    max-height: 300px !important;
    font-size: var(--font-size-xs) !important;
    padding: var(--spacing-sm) !important;
    line-height: 1.6 !important;
    white-space: pre-wrap !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    overflow-x: auto !important;
    overflow-y: auto !important;
    -webkit-overflow-scrolling: touch !important;
    overscroll-behavior: contain;
    background: var(--bg-secondary) !important;
    border-radius: var(--radius-sm) !important;
    margin: var(--spacing-xs) 0 !important;
  }
  
  /* 警告框移动端优化 */
  .log-detail-content :deep(.el-alert) {
    margin: var(--spacing-xs) 0 !important;
    font-size: var(--font-size-sm) !important;
    padding: var(--spacing-sm) var(--spacing-md) !important;
    border-radius: var(--radius-sm) !important;
  }
  
  .log-detail-content :deep(.el-alert__content) {
    font-size: var(--font-size-sm) !important;
    line-height: 1.6 !important;
    word-break: break-word !important;
  }
  
  /* 加载占位符移动端优化 */
  .loading-placeholder {
    padding: var(--spacing-xxl) var(--spacing-md);
    font-size: var(--font-size-base);
  }
  
  .loading-placeholder .is-loading {
    font-size: var(--font-size-xxl);
  }
}

.filter-form {
  margin: 0;
}

.log-detail-dialog :deep(.el-dialog__body) {
  padding: var(--spacing-xl);
  max-height: calc(100vh - 200px);
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.log-detail-content {
  width: 100%;
}

.log-detail-content :deep(.el-descriptions) {
  width: 100%;
}

.log-detail-content :deep(.el-descriptions__table) {
  width: 100%;
  table-layout: auto;
}

.log-detail-content :deep(.el-descriptions__label),
.log-detail-content :deep(.el-descriptions-item__label) {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  min-width: 100px;
}

.log-detail-content :deep(.el-descriptions__content),
.log-detail-content :deep(.el-descriptions-item__content) {
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

/* 移动端日期选择器优化 */
@media (max-width: 767px) {
  /* 筛选表单移动端优化 - 强制覆盖 inline 表单样式 */
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
  
  /* 日期选择器特殊处理 */
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
  
  /* 查询和重置按钮移动端优化 */
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
    white-space: nowrap; /* 防止按钮文字换行 */
  }
  
  .filter-form :deep(.el-form-item:last-child .el-button .el-icon) {
    margin-right: var(--spacing-xs);
  }
  
  /* 移动端表格操作按钮优化 */
  .el-table :deep(.el-button--link) {
    min-height: var(--touch-target-size);
    padding: var(--spacing-xs) var(--spacing-sm);
  }
}
</style>

