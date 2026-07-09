<!--
  定时任务管理页面（ScheduledTaskManagement.vue）

  功能区块：
  1. 统计卡片：总任务数、启用/运行中/失败数量
  2. 筛选区：任务名称、启用状态
  3. 任务表格：Cron 表达式、上次/下次执行、手动触发
  4. 编辑弹窗：配置任务参数与 Cron 调度规则

  列表与操作逻辑由 composable useScheduledTasks.js 提供。
-->
<template>
  <!-- 页面主模板 -->
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
    <!-- 筛选区 -->
    <el-card class="filter-card" shadow="never">
      <!-- 表单区域 -->
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="任务名称">
          <el-input 
            v-model="searchForm.task_name" 
            placeholder="输入任务名称搜索" 
            clearable
            @keyup.enter="() => fetchTasks(true)"
            style="width: 200px;"
            name="task_name"
          >
            <template #prefix>
              <el-icon :size="16"><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="状态">
          <el-select 
            v-model="searchForm.is_active" 
            placeholder="全部状态" 
            clearable 
            style="width: 150px;"
            aria-label="选择任务状态"
            name="is_active"
          >
            <el-option label="全部状态" value=""></el-option>
            <el-option label="启用" :value="true"></el-option>
            <el-option label="禁用" :value="false"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="运行状态">
          <el-select 
            v-model="searchForm.is_running" 
            placeholder="全部" 
            clearable 
            style="width: 150px;"
            aria-label="选择运行状态"
            name="is_running"
          >
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
      <!-- 卡片标题栏 -->
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
        <el-table-column prop="task_name" label="任务名称" min-width="240" show-overflow-tooltip>
          <template #default="scope">
            <div class="task-name-cell">
              <span class="task-name-text">{{ scope.row.task_name }}</span>
              <el-button
                v-if="isGamSchedulerTask(scope.row)"
                type="success"
                link
                size="small"
                class="gam-config-link"
                @click="goToGamSchedulerConfig"
              >
                账号配置
              </el-button>
              <el-tag
                v-if="isTaskRunning(scope.row)"
                type="warning"
                size="small"
                effect="dark"
                style="margin-left: 8px;"
              >
                正在运行
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.description || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="cron_expression" label="Cron表达式" width="150" align="center">
          <template #default="scope">
            <el-tag v-if="scope.row.cron_expression" type="info" size="small">
              {{ scope.row.cron_expression }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="function_name" label="执行函数" min-width="250" show-overflow-tooltip>
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
        <el-table-column prop="is_active" label="状态" width="140" align="center">
          <template #default="scope">
            <!-- 运行中：展示「正在运行」，禁用启用开关，不可切换激活 -->
            <div v-if="isTaskRunning(scope.row)" class="running-status-cell">
              <el-tag type="warning" size="small" effect="dark">正在运行</el-tag>
              <el-tooltip content="任务正在运行，无法切换启用状态" placement="top">
                <el-switch
                  :model-value="scope.row.is_active"
                  disabled
                  :active-text="scope.row.is_active ? '启用' : ''"
                  :inactive-text="!scope.row.is_active ? '禁用' : ''"
                  aria-label="任务正在运行，无法切换启用状态"
                />
              </el-tooltip>
            </div>
            <el-switch
              v-else
              v-model="scope.row.is_active"
              @change="handleToggleActive(scope.row)"
              :active-text="scope.row.is_active ? '启用' : ''"
              :inactive-text="!scope.row.is_active ? '禁用' : ''"
              aria-label="切换任务状态"
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
        <el-table-column label="操作" width="360" fixed="right" align="center" class-name="action-column">
          <template #default="scope">
            <div class="action-buttons">
              <el-button
                v-if="isGamSchedulerTask(scope.row)"
                type="success"
                size="small"
                @click="goToGamSchedulerConfig"
                class="action-btn"
              >
                账号配置
              </el-button>
              <el-button
                type="primary"
                size="small"
                @click="handleTrigger(scope.row)"
                :disabled="!scope.row.is_active || isTaskRunning(scope.row)"
                class="action-btn"
                :icon="VideoPlay"
              >
                {{ isTaskRunning(scope.row) ? '运行中' : '触发' }}
              </el-button>
              <el-button
                type="warning"
                size="small"
                @click="handleReleaseLock(scope.row)"
                :disabled="!isTaskRunning(scope.row)"
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

    <!-- 手动触发任务日期选择对话框 -->
    <el-dialog
      v-model="triggerDialogVisible"
      title="手动触发任务"
      width="500px"
      :append-to-body="true"
    >
      <el-form :model="triggerParams" label-width="100px">
        <el-form-item label="起始日期">
          <el-date-picker
            v-model="triggerParams.start_date"
            type="date"
            placeholder="选择起始日期（可选）"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结束日期">
          <el-date-picker
            v-model="triggerParams.end_date"
            type="date"
            placeholder="选择结束日期（可选，不填则使用起始日期）"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item>
          <el-alert
            type="info"
            :closable="false"
            show-icon
          >
            <template #title>
              <div>提示：</div>
              <div>• 不填写日期则使用默认逻辑（0-8点获取昨天，其他时间获取今天）</div>
              <div>• 只填写起始日期时，结束日期将使用起始日期</div>
              <div>• 部分任务只需要一个日期参数</div>
            </template>
          </el-alert>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="triggerDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmTrigger">确定触发</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { onMounted, onUnmounted, onBeforeUnmount, nextTick } from 'vue';
import { onBeforeRouteLeave, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Search, Refresh, VideoPlay, Unlock, Document, Folder } from '@element-plus/icons-vue';
import { formatDateTime } from '../../utils/dateFormat';
import { isGamSchedulerTask } from '../../constants/scheduledTasks';
import { isTaskRunning } from '../../utils/scheduledTaskStatus';
import { useDevice } from '../../composables/useDevice';
import { useScheduledTasks } from '../../composables/useScheduledTasks';
import { useScheduledTaskActions } from '../../composables/useScheduledTaskActions';

const router = useRouter();
const { isMobile } = useDevice();

const {
  loading,
  tasks,
  searchForm,
  pagination,
  stats,
  fetchTasks,
  resetFilter,
  bindPaginationWatch,
  cleanup,
  setupAutoRefresh,
  finishInitializing,
} = useScheduledTasks();

const {
  triggerDialogVisible,
  currentTriggerTask,
  triggerParams,
  handleToggleActive,
  handleTrigger,
  confirmTrigger,
  handleReleaseLock,
} = useScheduledTaskActions({ fetchTasks });

const goToGamSchedulerConfig = () => {
  router.push('/app/admin/gam-scheduler');
};

bindPaginationWatch();

onMounted(async () => {
  await nextTick();

  setTimeout(async () => {
    try {
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => {
          reject(new Error('页面加载超时，请检查网络连接或刷新页面'));
        }, 20000);
      });
      await Promise.race([fetchTasks(true), timeoutPromise]);
    } catch (error) {
      if (error.message?.includes('超时')) {
        ElMessage.error(error.message);
        loading.value = false;
      } else if (error.response?.status === 401) {
        loading.value = false;
      } else {
        loading.value = false;
      }
    } finally {
      await nextTick();
      finishInitializing();
    }
  }, 0);

  setupAutoRefresh();
});

onBeforeRouteLeave(() => {
  cleanup();
});

onBeforeUnmount(() => {
  cleanup();
});

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

.running-status-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.task-name-cell {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.gam-config-link {
  padding: 0 4px;
  font-size: 12px;
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

