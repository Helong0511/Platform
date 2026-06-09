<!--
  审计日志管理页面（AuditLogManagement.vue）

  功能区块：
  1. 统计卡片：总日志数、成功/失败数、活跃用户数
  2. 筛选区：用户名、操作类型、资源类型、时间范围、状态
  3. 日志表格：分页展示操作记录，支持列显隐配置
  4. 详情弹窗：查看单条日志的请求/响应详情

  数据与筛选逻辑由 composable useAuditLogs.js 提供。
-->
<template>
  <!-- 页面主模板 -->
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
    <!-- 筛选区 -->
    <el-card class="filter-card" shadow="never">
      <!-- 表单区域 -->
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
          <el-select v-model="searchForm.action_type" placeholder="全部" clearable style="width: 150px;" name="action_type" popper-class="select-dropdown" :teleported="true">
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
            <el-option label="撤销会话" value="REVOKE_SESSION"></el-option>
            <el-option label="撤销全部会话" value="REVOKE_ALL_SESSIONS"></el-option>
            <el-option label="CSRF违规" value="CSRF_VIOLATION"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="资源类型">
          <el-select v-model="searchForm.resource_type" placeholder="全部" clearable style="width: 150px;" name="resource_type" popper-class="select-dropdown" :teleported="true">
            <el-option label="全部" value=""></el-option>
            <el-option label="用户" value="USER"></el-option>
            <el-option label="客户" value="CLIENT"></el-option>
            <el-option label="产品" value="PRODUCT"></el-option>
            <el-option label="广告数据" value="AD_DATA"></el-option>
            <el-option label="定时任务" value="SCHEDULED_TASK"></el-option>
            <el-option label="系统" value="SYSTEM"></el-option>
            <el-option label="前端" value="FRONTEND"></el-option>
            <el-option label="会话" value="SESSION"></el-option>
            <el-option label="Offer" value="OFFER"></el-option>
            <el-option label="渠道" value="PUBLISHER"></el-option>
            <el-option label="广告主" value="ADVERTISER"></el-option>
            <el-option label="转化扣减配置" value="CONVERSION_DEDUCTION_CONFIG"></el-option>
            <el-option label="斗篷配置" value="CLOAK_CONFIG"></el-option>
            <el-option label="通知配置" value="NOTIFICATION_CONFIG"></el-option>
            <el-option label="短链接" value="SHORT_LINK"></el-option>
            <el-option label="Cap配置" value="OFFER_CAP"></el-option>
            <el-option label="扣量配置" value="OFFER_DISCOUNT"></el-option>
            <el-option label="敏感路径黑名单IP" value="SENSITIVE_BLOCKED_IP"></el-option>
            <el-option label="敏感路径拦截日志" value="SENSITIVE_PATH_PROBE_LOG"></el-option>
            <el-option label="第三方上报日志" value="THIRD_PARTY_REPORT_LOG"></el-option>
            <el-option label="TB搜索数据" value="TB_SEARCH_DATA"></el-option>
            <el-option label="Postback转发日志" value="POSTBACK_FORWARD_LOG"></el-option>
            <el-option label="Postback转化" value="POSTBACK_CONVERSION"></el-option>
            <el-option label="Postback待确认转化" value="POSTBACK_PENDING_CONVERSION"></el-option>
            <el-option label="Postback IP白名单" value="POSTBACK_IP_WHITELIST"></el-option>
            <el-option label="产品分配" value="PRODUCT_ASSIGNMENT"></el-option>
            <el-option label="下游测试" value="AFFILIATE_TEST"></el-option>
            <el-option label="Telegram" value="TELEGRAM"></el-option>
            <el-option label="点击记录" value="CLICK"></el-option>
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
          <el-select v-model="searchForm.success" placeholder="全部" clearable style="width: 120px;" name="success" popper-class="select-dropdown" :teleported="true">
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
      <!-- 卡片标题栏 -->
    <template #header>
        <div class="table-header">
          <span>日志列表</span>
          <el-button 
            type="text" 
            :icon="Setting" 
            @click="columnSettingVisible = true"
            style="float: right;"
          >
            列设置
          </el-button>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="logs"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column v-if="columnVisibility.id" prop="id" label="ID" width="80" align="center" />
        <el-table-column v-if="columnVisibility.username" prop="username" label="用户名" width="120" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.username || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.action_type" prop="action_type" label="操作类型" width="120" align="center">
          <template #default="scope">
            <el-tag :type="getActionTypeTag(scope.row.action_type)">
              {{ getActionTypeLabel(scope.row.action_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.resource_type" prop="resource_type" label="资源类型" width="120" show-overflow-tooltip>
          <template #default="scope">
            {{ getResourceTypeLabel(scope.row.resource_type) || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.resource_name" prop="resource_name" label="资源名称" min-width="150" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.resource_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.ip_address" prop="ip_address" label="IP地址" width="130" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.ip_address || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.request_method" prop="request_method" label="请求方法" width="100" align="center">
          <template #default="scope">
            <el-tag v-if="scope.row.request_method" size="small">
              {{ scope.row.request_method }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.request_path" prop="request_path" label="请求路径" min-width="200" show-overflow-tooltip />
        <el-table-column v-if="columnVisibility.status_code" prop="status_code" label="状态码" width="100" align="center">
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
        <el-table-column v-if="columnVisibility.success" prop="success" label="状态" width="80" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.success ? 'success' : 'danger'" size="small">
              {{ scope.row.success ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.created_at" prop="created_at" label="时间" width="180">
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
      :append-to-body="true"
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
        <el-descriptions-item label="资源类型">{{ getResourceTypeLabel(currentLog.resource_type) || '-' }}</el-descriptions-item>
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

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="500px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="id" :disabled="true">ID（固定显示）</el-checkbox>
        <el-checkbox label="username">用户名</el-checkbox>
        <el-checkbox label="action_type">操作类型</el-checkbox>
        <el-checkbox label="resource_type">资源类型</el-checkbox>
        <el-checkbox label="resource_name">资源名称</el-checkbox>
        <el-checkbox label="ip_address">IP地址</el-checkbox>
        <el-checkbox label="request_method">请求方法</el-checkbox>
        <el-checkbox label="request_path">请求路径</el-checkbox>
        <el-checkbox label="status_code">状态码</el-checkbox>
        <el-checkbox label="success">状态</el-checkbox>
        <el-checkbox label="created_at" :disabled="true">时间（固定显示）</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import {
  ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem,
  ElInput, ElSelect, ElOption, ElTag, ElDialog, ElIcon, ElMessage,
  ElDescriptions, ElDescriptionsItem, ElDatePicker, ElAlert, ElCheckboxGroup, ElCheckbox,
} from 'element-plus';
import { Search, Refresh, Loading, Setting } from '@element-plus/icons-vue';
import { useAuthStore } from '../../store';
import { formatDateTime } from '../../utils/dateFormat';
import { useDevice } from '../../composables/useDevice';
import { useAuditLogs } from '../../composables/useAuditLogs';
import { useAuditLogColumnVisibility } from '../../composables/useAuditLogColumnVisibility';
import {
  formatAuditJson,
  getActionTypeLabel,
  getActionTypeTag,
  getResourceTypeLabel,
  getStatusCodeTag,
} from '../../utils/auditLogFormat';

const { isMobile } = useDevice();
const router = useRouter();
const authStore = useAuthStore();

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility,
} = useAuditLogColumnVisibility();

const {
  logs,
  loading,
  stats,
  pagination,
  searchForm,
  dateRange,
  detailDialogVisible,
  currentLog,
  fetchLogs,
  resetFilter,
  handleViewDetail,
  bindPaginationWatch,
  finishInitializing,
} = useAuditLogs(authStore, router);

const formatJson = formatAuditJson;

bindPaginationWatch();

onMounted(async () => {
  loadColumnVisibility();
  await nextTick();
  setTimeout(async () => {
    try {
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => {
          reject(new Error('页面加载超时，请检查网络连接或刷新页面'));
        }, 20000);
      });
      await Promise.race([fetchLogs(), timeoutPromise]);
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

