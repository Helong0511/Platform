<template>
  <div class="scheduled-task-management-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1>定时任务管理</h1>
        <div class="stats-info" v-if="stats">
          <span class="stat-item">
            <span class="stat-label">总任务数：</span>
            <span class="stat-value">{{ stats.total || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">启用：</span>
            <span class="stat-value success">{{ stats.active || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">运行中：</span>
            <span class="stat-value warning">{{ stats.running || 0 }}</span>
          </span>
          <span class="stat-item">
            <span class="stat-label">失败：</span>
            <span class="stat-value danger">{{ stats.error || 0 }}</span>
          </span>
        </div>
      </div>
    </div>

    <!-- 筛选控件 -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="任务名称">
          <el-input 
            v-model="searchForm.task_name" 
            placeholder="输入任务名称搜索" 
            clearable
            @keyup.enter="() => fetchTasks(true)"
            style="width: 200px;"
          >
            <template #prefix>
              <el-icon :size="16"><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.is_active" placeholder="全部状态" clearable style="width: 150px;">
            <el-option label="全部状态" value=""></el-option>
            <el-option label="启用" :value="true"></el-option>
            <el-option label="禁用" :value="false"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="运行状态">
          <el-select v-model="searchForm.is_running" placeholder="全部" clearable style="width: 150px;">
            <el-option label="全部" value=""></el-option>
            <el-option label="运行中" :value="true"></el-option>
            <el-option label="空闲" :value="false"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="() => fetchTasks(true)" :loading="loading" :icon="Search">
            查询
          </el-button>
          <el-button @click="resetFilter" :icon="Refresh">
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 任务数据表格 -->
    <el-card class="data-table-card" shadow="never">
      <template #header>
        <div class="table-header">
          <span>任务列表</span>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="tasks"
        border
        stripe
        style="width: 100%"
        default-sort="{ prop: 'id', order: 'descending' }"
      >
        <el-table-column prop="id" label="ID" width="80" sortable align="center">
          <template #default="scope">
            {{ scope.row.id }}
          </template>
        </el-table-column>
        <el-table-column prop="task_name" label="任务名称" min-width="200">
          <template #default="scope">
            <div class="task-name-cell">
              <span class="task-name-text">{{ scope.row.task_name }}</span>
              <el-tag v-if="scope.row.is_running" type="warning" size="small" style="margin-left: 8px;">
                运行中
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.description || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="cron_expression" label="Cron表达式" width="150">
          <template #default="scope">
            <el-tag v-if="scope.row.cron_expression" type="info" size="small">
              {{ scope.row.cron_expression }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="function_name" label="执行函数" min-width="250">
          <template #default="scope">
            <div v-if="scope.row.function_name" class="function-info">
              <div class="function-name">
                <el-icon :size="16"><Document /></el-icon>
                <span class="function-name-text">{{ scope.row.function_name }}()</span>
              </div>
              <div v-if="scope.row.function_module" class="function-module">
                <el-icon :size="16"><Folder /></el-icon>
                <span class="module-path">{{ scope.row.function_module }}</span>
              </div>
            </div>
            <span v-else class="no-function">未注册</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100" align="center">
          <template #default="scope">
            <el-switch
              v-model="scope.row.is_active"
              @change="handleToggleActive(scope.row)"
              :disabled="scope.row.is_running"
            />
          </template>
        </el-table-column>
        <el-table-column prop="last_run_time" label="上次执行" width="180">
          <template #default="scope">
            <div v-if="scope.row.last_run_time">
              <div>{{ formatDateTime(scope.row.last_run_time) }}</div>
              <div class="run-info" v-if="scope.row.last_run_pid">
                <span class="info-text">PID: {{ scope.row.last_run_pid }}</span>
                <span class="info-text" v-if="scope.row.last_run_host">
                  | {{ scope.row.last_run_host }}
                </span>
              </div>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="run_count" label="执行统计" width="150" align="center">
          <template #default="scope">
            <div class="run-stats">
              <div>总次数: <span class="stat-number">{{ scope.row.run_count }}</span></div>
              <div>成功: <span class="stat-number success">{{ scope.row.success_count }}</span></div>
              <div>失败: <span class="stat-number danger">{{ scope.row.error_count }}</span></div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="last_error" label="最后错误" min-width="200" show-overflow-tooltip>
          <template #default="scope">
            <el-tag v-if="scope.row.last_error" type="danger" size="small" effect="plain">
              {{ scope.row.last_error }}
            </el-tag>
            <span v-else class="text-success">无错误</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right" align="center" class-name="action-column">
          <template #default="scope">
            <div class="action-buttons">
              <el-button
                type="primary"
                size="small"
                @click="handleTrigger(scope.row)"
                :disabled="!scope.row.is_active || scope.row.is_running"
                class="action-btn"
                :icon="VideoPlay"
              >
                触发
              </el-button>
              <el-button
                type="warning"
                size="small"
                @click="handleReleaseLock(scope.row)"
                :disabled="!scope.row.is_running"
                class="action-btn"
                :icon="Unlock"
              >
                释放锁
              </el-button>
            </div>
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
          class="pagination-component"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed, onBeforeUnmount, watch, nextTick } from 'vue';
import { onBeforeRouteLeave, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Search, Refresh, VideoPlay, Unlock, Document, Folder } from '@element-plus/icons-vue';
import {
  getScheduledTasks,
  updateScheduledTask,
  triggerScheduledTask,
  releaseTaskLock
} from '../../api/scheduledTask';
import { formatDateTime } from '../../utils/dateFormat';
import { extractErrorMessage, isErrorHandled, ensureCsrfToken } from '../../utils/api';
import { useDevice } from '../../composables/useDevice';
import { useAuthStore } from '../../store';

// 设备检测
const { isMobile } = useDevice();

// 响应式数据
const loading = ref(false);
const tasks = ref([]);
const searchForm = reactive({
  task_name: '',
  is_active: null,
  is_running: null
});

// 请求取消控制器（用于取消正在进行的请求）
const abortController = ref(null);

// 编辑对话框相关
const editDialogVisible = ref(false);
const editFormRef = ref(null);
const currentEditTask = ref(null);
const saving = ref(false);
const editForm = reactive({
  task_name: '',
  cron_expression: '',
  description: '',
  function_path: '',
  is_active: true
});

// Cron 表达式验证函数（前端基本格式检查，详细验证由后端完成）
const validateCronExpression = (rule, value, callback) => {
  if (!value) {
    callback(new Error('请输入Cron表达式'));
    return;
  }
  
  const trimmedValue = value.trim();
  
  // 基本格式检查：应该是5个字段，用空格分隔
  const parts = trimmedValue.split(/\s+/);
  if (parts.length !== 5) {
    callback(new Error('Cron表达式格式错误：应为5个字段（分 时 日 月 星期），用空格分隔\n例如: 0 0 * * *'));
    return;
  }
  
  // 检查每个字段不为空
  const [minute, hour, day, month, weekday] = parts;
  if (!minute || !hour || !day || !month || !weekday) {
    callback(new Error('Cron表达式格式错误：每个字段不能为空'));
    return;
  }
  
  // 基本格式验证：允许 * ? 数字 范围 列表 步长等
  // 分钟: 0-59 或 * 或 */n 或 n-m 或 n,m 或 n-m/n
  const minutePattern = /^(\*|\?|\d+(-\d+)?(\/\d+)?|(\d+,)+\d+)$/;
  if (!minutePattern.test(minute)) {
    const num = parseInt(minute);
    if (isNaN(num) || num < 0 || num > 59) {
      callback(new Error('分钟字段无效：应为 0-59 或 * 或 */n 或 n-m 或 n,m\n例如: 0, 30, */5, 0-59/10'));
      return;
    }
  }
  
  // 小时: 0-23 或 * 或 */n 或 n-m 或 n,m 或 n-m/n
  const hourPattern = /^(\*|\?|\d+(-\d+)?(\/\d+)?|(\d+,)+\d+)$/;
  if (!hourPattern.test(hour)) {
    const num = parseInt(hour);
    if (isNaN(num) || num < 0 || num > 23) {
      callback(new Error('小时字段无效：应为 0-23 或 * 或 */n 或 n-m 或 n,m\n例如: 0, 12, */2, 9-17'));
      return;
    }
  }
  
  // 日期: 1-31 或 * 或 ? 或 */n 或 n-m 或 n,m 或 L 或 LW 或 nW
  const dayPattern = /^(\*|\?|\d+(-\d+)?(\/\d+)?|(\d+,)+\d+|L|LW|\d+W)$/;
  if (!dayPattern.test(day)) {
    const num = parseInt(day);
    if (isNaN(num) || num < 1 || num > 31) {
      callback(new Error('日期字段无效：应为 1-31 或 * 或 ? 或 */n 或 n-m 或 n,m 或 L\n例如: 1, 15, L, 1W'));
      return;
    }
  }
  
  // 月份: 1-12 或 * 或 */n 或 n-m 或 n,m 或 JAN-DEC
  const monthPattern = /^(\*|\?|\d+(-\d+)?(\/\d+)?|(\d+,)+\d+|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$/i;
  if (!monthPattern.test(month)) {
    const num = parseInt(month);
    if (isNaN(num) || num < 1 || num > 12) {
      callback(new Error('月份字段无效：应为 1-12 或 * 或 */n 或 n-m 或 n,m 或 JAN-DEC\n例如: 1, 6, JAN, */3'));
      return;
    }
  }
  
  // 星期: 0-7 或 * 或 ? 或 */n 或 n-m 或 n,m 或 SUN-SAT
  const weekdayPattern = /^(\*|\?|\d+(-\d+)?(\/\d+)?|(\d+,)+\d+|SUN|MON|TUE|WED|THU|FRI|SAT)$/i;
  if (!weekdayPattern.test(weekday)) {
    const num = parseInt(weekday);
    if (isNaN(num) || num < 0 || num > 7) {
      callback(new Error('星期字段无效：应为 0-7 或 * 或 ? 或 */n 或 n-m 或 n,m 或 SUN-SAT\n例如: 1, 5, MON, 1-5'));
      return;
    }
  }
  
  // 如果所有基本检查都通过，调用回调（详细验证由后端完成）
  callback();
};

const editFormRules = {
  task_name: [
    { required: true, message: '请输入任务名称', trigger: 'blur' },
    { min: 1, max: 100, message: '任务名称长度在 1 到 100 个字符', trigger: 'blur' }
  ],
  cron_expression: [
    { required: true, message: '请输入Cron表达式', trigger: 'blur' },
    { validator: validateCronExpression, trigger: 'blur' }
  ]
};

const editDialogTitle = computed(() => {
  return currentEditTask.value ? '编辑定时任务' : '创建定时任务';
});

const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
});

// 防抖定时器，避免短时间内多次请求（使用 ref 确保响应式清理）
const fetchDebounceTimer = ref(null);
const FETCH_DEBOUNCE_DELAY = 2000; // 2秒防抖

// 统计数据
const stats = computed(() => {
  if (tasks.value.length === 0) return null;
  
  return {
    total: pagination.total,
    active: tasks.value.filter(t => t.is_active).length,
    running: tasks.value.filter(t => t.is_running).length,
    error: tasks.value.filter(t => t.error_count > 0).length
  };
});

// 获取任务列表（带防抖）
const fetchTasks = async (immediate = false) => {
  // 如果正在加载中，跳过本次请求
  if (loading.value && !immediate) {
    return;
  }
  
  // 清除之前的防抖定时器
  if (fetchDebounceTimer.value) {
    clearTimeout(fetchDebounceTimer.value);
    fetchDebounceTimer.value = null;
  }
  
  // 如果不是立即执行，使用防抖
  if (!immediate) {
    fetchDebounceTimer.value = setTimeout(() => {
      fetchTasks(true);
    }, FETCH_DEBOUNCE_DELAY);
    return;
  }
  
  loading.value = true;
  
  // 取消之前的请求（如果存在）
  if (abortController.value) {
    abortController.value.abort();
  }
  
  // 创建新的取消控制器
  abortController.value = new AbortController();
  const currentController = abortController.value;
  
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(searchForm.task_name && { task_name: searchForm.task_name }),
      ...(searchForm.is_active !== null && searchForm.is_active !== '' && { is_active: searchForm.is_active }),
      ...(searchForm.is_running !== null && searchForm.is_running !== '' && { is_running: searchForm.is_running })
    };

    const response = await getScheduledTasks(params);
    
    // 检查请求是否已被取消
    if (currentController.signal.aborted) {
      return;
    }
    
    tasks.value = response.data || [];
    pagination.total = response.total || 0;
  } catch (error) {
    // 忽略取消错误
    if (error.name === 'AbortError' || error.name === 'CanceledError') {
      return;
    }
    // 401错误已在拦截器中处理，直接返回
    if (error.response?.status === 401) {
      if (!currentController.signal.aborted) {
        loading.value = false;
      }
      return;
    }
    // 如果错误未被处理，显示错误消息
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
  } finally {
    // 只有在当前请求未被取消时才清除loading状态
    if (!currentController.signal.aborted) {
      loading.value = false;
    }
  }
};

// 重置筛选
const resetFilter = () => {
  searchForm.task_name = '';
  searchForm.is_active = null;
  searchForm.is_running = null;
  pagination.page = 1;
  fetchTasks(true); // 重置时立即执行，不使用防抖
};

// 切换启用状态
const handleToggleActive = async (task) => {
  const originalState = task.is_active;
  try {
    await updateScheduledTask(task.task_name, {
      is_active: task.is_active
    });
    // 使用防抖版本，避免立即刷新
    fetchTasks();
  } catch (error) {
    // 恢复原状态
    task.is_active = originalState;
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
  }
};

// 手动触发任务
const handleTrigger = async (task) => {
  try {
    await ElMessageBox.confirm(
      `确定要手动触发任务 "${task.task_name}" 吗？`,
      '确认触发',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    
    await triggerScheduledTask(task.task_name);
    ElMessage.success('任务已触发，正在后台执行');
    
    // 延迟刷新，等待任务状态更新（使用防抖版本）
    // 不立即刷新，让防抖机制处理，避免连续请求
    setTimeout(() => {
      fetchTasks(); // 使用防抖版本
    }, 2000); // 延迟2秒，与防抖时间一致
  } catch (error) {
    if (error !== 'cancel') {
      // 错误已在ElMessage中显示，不需要额外日志
    }
  }
};

// 释放任务锁
const handleReleaseLock = async (task) => {
  try {
    await ElMessageBox.confirm(
      `确定要释放任务 "${task.task_name}" 的锁吗？\n\n这通常用于任务异常中断导致锁未释放的情况。`,
      '确认释放锁',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    
    // 确保CSRF令牌存在
    await ensureCsrfToken(() => fetchTasks());
    
    await releaseTaskLock(task.task_name);
    // 使用防抖版本，避免立即刷新
    fetchTasks();
  } catch (error) {
    if (error !== 'cancel') {
      // 错误已在ElMessage中显示，不需要额外日志
    }
  }
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
      fetchTasks(true); // 分页变化时立即执行，不使用防抖
    }
    // 如果每页条数变化，重置到第一页并刷新
    else if (newSize !== oldSize) {
      if (pagination.page !== 1) {
        pagination.page = 1;
      } else {
        // 如果已经在第一页，直接刷新
        fetchTasks(true); // 分页变化时立即执行，不使用防抖
      }
    }
  },
  { flush: 'post' }
);

// 自动刷新定时器（使用 ref 确保响应式清理）
const refreshTimer = ref(null);
const visibilityHandler = ref(null);

// 清理所有定时器和监听器
const cleanup = () => {
  // 取消正在进行的请求
  if (abortController.value) {
    abortController.value.abort();
    abortController.value = null;
  }
  
  // 清理自动刷新定时器
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
    refreshTimer.value = null;
  }
  // 清理防抖定时器
  if (fetchDebounceTimer.value) {
    clearTimeout(fetchDebounceTimer.value);
    fetchDebounceTimer.value = null;
  }
  // 清理页面可见性监听器
  if (visibilityHandler.value) {
    document.removeEventListener('visibilitychange', visibilityHandler.value);
    visibilityHandler.value = null;
  }
  // 确保停止所有正在进行的请求（如果可能）
  loading.value = false;
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
      
      await Promise.race([
        fetchTasks(true), // 首次加载立即执行，不使用防抖
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
  
  // 每60秒自动刷新一次（获取最新状态）
  // 使用 Page Visibility API，页面不可见时停止刷新
  const startAutoRefresh = () => {
    if (refreshTimer.value) {
      clearInterval(refreshTimer.value);
    }
    
    refreshTimer.value = setInterval(() => {
      // 只在页面可见且不在加载中时刷新
      // 自动刷新使用防抖版本，避免与手动操作冲突
      if (!document.hidden && !loading.value) {
        fetchTasks(); // 使用防抖版本
      }
    }, 60000); // 改为60秒，减少请求频率
  };
  
  const stopAutoRefresh = () => {
    if (refreshTimer.value) {
      clearInterval(refreshTimer.value);
      refreshTimer.value = null;
    }
  };
  
  // 页面可见性变化时控制自动刷新
  visibilityHandler.value = () => {
    if (document.hidden) {
      stopAutoRefresh();
    } else {
      startAutoRefresh();
    }
  };
  
  document.addEventListener('visibilitychange', visibilityHandler.value);
  
  // 启动自动刷新
  startAutoRefresh();
});

// 路由离开前清理（确保切换路由时立即停止）
onBeforeRouteLeave(() => {
  cleanup();
});

// 组件卸载前清理
onBeforeUnmount(() => {
  cleanup();
});

// 组件卸载时清理（双重保险）
onUnmounted(() => {
  cleanup();
});
</script>

<style scoped>
.scheduled-task-management-container {
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

.header-left h1 {
  margin: 0 0 var(--spacing-md) 0;
  font-size: var(--font-size-title);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.stats-info {
  display: flex;
  gap: var(--spacing-lg);
  flex-wrap: wrap;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .scheduled-task-management-container {
    padding: var(--spacing-md);
  }
  
  .page-header {
    margin-bottom: var(--spacing-md);
  }
  
  .header-left h1 {
    font-size: var(--font-size-xl);
    margin-bottom: var(--spacing-sm);
  }
  
  .stats-info {
    gap: var(--spacing-md);
    flex-direction: column;
  }
  
  .stat-item {
    font-size: var(--font-size-sm);
  }
  
  .filter-card {
    margin-bottom: var(--spacing-md);
  }
  
  .data-table-card {
    margin-bottom: var(--spacing-md);
  }
  
  .table-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }
  
  .table-header .el-button {
    width: 100%;
    min-height: var(--touch-target-size);
  }
  
  .pagination-container {
    margin-top: var(--spacing-md);
    justify-content: center;
  }
  
  /* 移动端筛选表单标签左对齐 */
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
  
  .filter-form :deep(.el-form-item) {
    display: flex !important;
    flex-direction: column !important;
    align-items: flex-start !important;
  }
  
  .filter-form :deep(.el-form-item__content) {
    width: 100% !important;
    margin-left: 0 !important;
  }
}

.stat-item {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
}

.stat-label {
  margin-right: var(--spacing-xs);
}

.stat-value {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.stat-value.success {
  color: var(--success-color);
}

.stat-value.warning {
  color: var(--warning-color);
}

.stat-value.danger {
  color: var(--danger-color);
}

.filter-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.filter-form {
  margin: 0;
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
  font-weight: 600;
  font-size: 16px;
}

.task-name-cell {
  display: flex;
  align-items: center;
}

.task-name-text {
  font-weight: 500;
}

.run-info {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.info-text {
  margin-right: 8px;
}

.run-stats {
  font-size: 12px;
  line-height: 1.6;
}

.stat-number {
  font-weight: 600;
  margin-left: 4px;
}

.stat-number.success {
  color: var(--success-color);
}

.stat-number.danger {
  color: var(--danger-color);
}

.text-success {
  color: var(--success-color);
}

/* 函数信息样式 */
.function-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.function-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: var(--text-primary);
}

.function-name-text {
  font-family: 'Courier New', monospace;
  color: var(--primary-color);
}

.function-module {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.module-path {
  font-family: 'Courier New', monospace;
  word-break: break-all;
}

.no-function {
  color: var(--text-secondary);
  font-style: italic;
}

.pagination-container {
  margin-top: var(--spacing-lg);
  padding: var(--spacing-lg) 0;
  text-align: right;
  border-top: 1px solid var(--border-lighter);
}

.form-tip {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
  line-height: 1.4;
}

.action-buttons {
  display: flex;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.action-btn {
  min-height: var(--touch-target-size);
  min-width: var(--touch-target-size);
}

/* 移动端表格操作列优化 */
@media (max-width: 767px) {
  .action-buttons {
    flex-direction: row !important;
    flex-wrap: wrap !important;
    gap: var(--spacing-xs) !important;
    width: 100%;
    align-items: center;
    justify-content: flex-start;
  }
  
  .action-btn {
    flex: 0 0 auto !important;
    min-height: 36px !important;
    min-width: auto !important;
    padding: 6px 10px !important;
    font-size: 12px !important;
    white-space: nowrap !important;
    line-height: 1.2 !important;
    width: auto !important;
    height: auto !important;
  }
  
  /* 覆盖 Element Plus 按钮的默认样式 */
  .action-btn :deep(.el-button__inner) {
    font-size: 12px !important;
    padding: 0 !important;
    display: flex !important;
    align-items: center !important;
    gap: 4px !important;
  }
  
  .action-btn :deep(.el-icon) {
    margin-right: 0 !important;
    font-size: 14px !important;
    flex-shrink: 0;
  }
  
  /* 移动端按钮文字缩小显示 */
  .action-btn :deep(span) {
    font-size: 12px !important;
    line-height: 1.2 !important;
  }
  
  /* 确保按钮内容正确显示 */
  .action-btn :deep(*) {
    font-size: 12px !important;
  }
  
  /* 移动端表格列优化 */
  .el-table :deep(.action-column) {
    width: auto !important;
    min-width: 120px !important;
  }
  
  .el-table :deep(.action-column .cell) {
    padding: var(--spacing-xs) !important;
  }
  
  /* 移动端表格标题优化 - 防止截断 */
  .el-table :deep(.el-table__header th) {
    white-space: nowrap;
    overflow: visible;
    text-overflow: clip;
    padding: var(--spacing-xs) var(--spacing-sm);
    font-size: var(--font-size-xs);
    font-weight: var(--font-weight-semibold);
  }
  
  /* 移动端表格内容优化 */
  .el-table :deep(.el-table__body td) {
    padding: var(--spacing-xs) var(--spacing-sm);
    word-break: break-word;
  }
  
  /* 移动端表格容器优化 */
  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .el-table {
    min-width: 600px; /* 确保表格有最小宽度，可以横向滚动 */
    font-size: var(--font-size-sm);
  }
  
  /* 移动端分页优化 */
  .pagination-container {
    margin-top: var(--spacing-md);
    padding: var(--spacing-sm) 0;
  }
  
  .el-pagination {
    flex-wrap: wrap;
    justify-content: center;
    font-size: var(--font-size-sm);
  }
  
  .el-pagination :deep(.el-pagination__total) {
    margin-right: var(--spacing-sm);
    font-size: var(--font-size-sm);
  }
  
  .el-pagination :deep(.el-pagination__sizes) {
    margin: var(--spacing-xs) 0;
  }
  
  .el-pagination :deep(.el-pagination__jump) {
    margin: var(--spacing-xs) 0;
  }
  
  .el-pagination :deep(.btn-prev),
  .el-pagination :deep(.btn-next),
  .el-pagination :deep(.el-pager li) {
    min-width: var(--touch-target-size);
    min-height: var(--touch-target-size);
    font-size: var(--font-size-sm);
  }
  
  /* 移动端对话框优化 */
  .el-dialog {
    width: 95% !important;
    margin: var(--spacing-md) auto !important;
  }
  
  .el-dialog :deep(.el-dialog__body) {
    padding: var(--spacing-md);
  }
  
  /* 对话框footer基础样式 - 覆盖全局样式 */
  .el-dialog :deep(.el-dialog__footer) {
    padding: var(--spacing-md) var(--spacing-lg) !important;
    display: flex !important;
    flex-direction: row !important;
    gap: var(--spacing-sm) !important;
    justify-content: flex-end !important;
    align-items: center !important;
    text-align: right !important;
  }
  
  /* 处理包裹在div.dialog-footer中的按钮 - 横向排列并居中 */
  .el-dialog :deep(.el-dialog__footer .dialog-footer) {
    display: flex !important;
    flex-direction: row !important;
    justify-content: center !important;
    align-items: center !important;
    gap: 12px !important;
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    border-top: none !important;
  }
  
  /* 对话框footer中的按钮样式 - 缩小尺寸并横向排列 */
  .el-dialog :deep(.el-dialog__footer .el-button),
  .el-dialog :deep(.el-dialog__footer .dialog-footer .el-button) {
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 90px !important;
    margin: 0 !important;
    padding: 8px 20px !important;
    font-size: var(--font-size-base) !important;
  }
  
  .el-form :deep(.el-form-item__label) {
    width: 100px !important;
  }
}
</style>

