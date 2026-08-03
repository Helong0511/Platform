<template>
  <div class="monitoring-dashboard">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>系统监控仪表盘</h1>
      <p class="subtitle">实时监控系统性能、资源利用率及业务指标</p>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon qps">📊</div>
        <div class="stat-info">
          <div class="stat-value">{{ metrics.api.qps || 0 }}</div>
          <div class="stat-label">QPS (每秒请求数)</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon response-time">⏱️</div>
        <div class="stat-info">
          <div class="stat-value">{{ (metrics.api.average_duration || 0).toFixed(3) }}s</div>
          <div class="stat-label">平均响应时间</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon error-rate">⚠️</div>
        <div class="stat-info">
          <div class="stat-value" :class="{ warning: (metrics.api.error_rate || 0) > 0.05 }">
            {{ ((metrics.api.error_rate || 0) * 100).toFixed(2) }}%
          </div>
          <div class="stat-label">错误率</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon request-count">📈</div>
        <div class="stat-info">
          <div class="stat-value">{{ metrics.api.request_count || 0 }}</div>
          <div class="stat-label">总请求数</div>
        </div>
      </div>
    </div>

    <!-- 资源使用率卡片 -->
    <div class="resource-section">
      <h2>系统资源</h2>
      <div class="resource-grid">
        <div class="resource-card">
          <div class="resource-header">
            <span class="resource-icon">💻</span>
            <span class="resource-name">CPU</span>
          </div>
          <div class="resource-bar-container">
            <div 
              class="resource-bar cpu" 
              :style="{ width: (metrics.resources.cpu?.current || 0) + '%' }"
            ></div>
          </div>
          <div class="resource-info">
            <span class="resource-value">{{ (metrics.resources.cpu?.current || 0).toFixed(1) }}%</span>
            <span class="resource-range">({{ (metrics.resources.cpu?.min || 0).toFixed(1) }}% - {{ (metrics.resources.cpu?.max || 0).toFixed(1) }}%)</span>
          </div>
        </div>
        <div class="resource-card">
          <div class="resource-header">
            <span class="resource-icon">🧠</span>
            <span class="resource-name">内存</span>
          </div>
          <div class="resource-bar-container">
            <div 
              class="resource-bar memory" 
              :style="{ width: (metrics.resources.memory?.current || 0) + '%' }"
            ></div>
          </div>
          <div class="resource-info">
            <span class="resource-value">{{ (metrics.resources.memory?.current || 0).toFixed(1) }}%</span>
            <span class="resource-range">({{ (metrics.resources.memory?.min || 0).toFixed(1) }}% - {{ (metrics.resources.memory?.max || 0).toFixed(1) }}%)</span>
          </div>
        </div>
        <div class="resource-card">
          <div class="resource-header">
            <span class="resource-icon">💾</span>
            <span class="resource-name">磁盘</span>
          </div>
          <div class="resource-bar-container">
            <div 
              class="resource-bar disk" 
              :style="{ width: (metrics.resources.disk?.current || 0) + '%' }"
            ></div>
          </div>
          <div class="resource-info">
            <span class="resource-value">{{ (metrics.resources.disk?.current || 0).toFixed(1) }}%</span>
            <span class="resource-range">({{ (metrics.resources.disk?.min || 0).toFixed(1) }}% - {{ (metrics.resources.disk?.max || 0).toFixed(1) }}%)</span>
          </div>
        </div>
        <div class="resource-card" :class="{ 'resource-warn': logsSoftHit, 'resource-critical': logsHardHit }">
          <div class="resource-header">
            <span class="resource-icon">📜</span>
            <span class="resource-name">应用日志</span>
            <button
              type="button"
              class="logs-cleanup-btn"
              :disabled="logsCleanupLoading"
              title="清理超期备份/归档；冷却优先走 Redis 跨进程"
              @click="handleLogsCleanup"
            >
              {{ logsCleanupLoading ? '清理中…' : '立即清理' }}
            </button>
          </div>
          <div class="resource-bar-container">
            <div
              class="resource-bar logs"
              :class="{ warn: logsSoftHit, critical: logsHardHit }"
              :style="{ width: Math.min(logsUsagePercent, 100) + '%' }"
            ></div>
          </div>
          <div class="resource-info">
            <span class="resource-value">{{ logsUsageMb.toFixed(1) }} / {{ logsSoftLimitMb }} MB</span>
            <span class="resource-range">
              软 {{ logsSoftLimitMb }} / 硬 {{ logsHardLimitMb }}
              <template v-if="logsHardHit"> · 硬限制</template>
              <template v-else-if="logsSoftHit"> · 软限制</template>
              <template v-if="logQueueDroppedDelta > 0"> · 本进程队列丢弃 +{{ logQueueDroppedDelta }}</template>
              <template v-else-if="logQueueUsageRatio >= 0.8"> · 本进程队列积压</template>
            </span>
          </div>
          <p v-if="logsCleanupHint" class="logs-cleanup-hint">{{ logsCleanupHint }}</p>
        </div>
      </div>
    </div>

    <!-- 百分位数统计 -->
    <div class="percentiles-section">
      <h2>响应时间百分位数</h2>
      <div class="percentiles-grid">
        <div class="percentile-card">
          <div class="percentile-label">P50</div>
          <div class="percentile-value">{{ (metrics.api.percentiles?.p50 || 0).toFixed(3) }}s</div>
        </div>
        <div class="percentile-card">
          <div class="percentile-label">P90</div>
          <div class="percentile-value">{{ (metrics.api.percentiles?.p90 || 0).toFixed(3) }}s</div>
        </div>
        <div class="percentile-card">
          <div class="percentile-label">P95</div>
          <div class="percentile-value">{{ (metrics.api.percentiles?.p95 || 0).toFixed(3) }}s</div>
        </div>
        <div class="percentile-card">
          <div class="percentile-label">P99</div>
          <div class="percentile-value" :class="{ critical: (metrics.api.percentiles?.p99 || 0) > 5 }">
            {{ (metrics.api.percentiles?.p99 || 0).toFixed(3) }}s
          </div>
        </div>
      </div>
    </div>

    <!-- 慢请求列表 -->
    <div class="slow-requests-section">
      <div class="section-header">
        <h2>慢请求 TOP 10</h2>
        <span class="badge">{{ metrics.slow_requests?.length || 0 }} 条</span>
      </div>
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>方法</th>
              <th>路径</th>
              <th>状态码</th>
              <th>耗时</th>
              <th>客户端IP</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(req, index) in metrics.slow_requests?.slice(0, 10)" :key="index">
              <td><span class="method-badge" :class="req.method.toLowerCase()">{{ req.method }}</span></td>
              <td class="path-cell">{{ req.path }}</td>
              <td>{{ req.status_code }}</td>
              <td class="duration-cell">{{ req.duration.toFixed(3) }}s</td>
              <td>{{ req.client_ip }}</td>
              <td>{{ formatTime(req.timestamp) }}</td>
            </tr>
            <tr v-if="!metrics.slow_requests?.length">
              <td colspan="6" class="empty">暂无慢请求记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 告警列表 -->
    <div class="alerts-section">
      <div class="section-header">
        <h2>最近告警</h2>
        <span class="badge warning">{{ unacknowledgedCount }} 条未确认</span>
      </div>
      <div class="alerts-list">
        <div 
          v-for="(alert, index) in metrics.alerts" 
          :key="index"
          class="alert-item"
          :class="[alert.level.toLowerCase(), { acknowledged: alert.acknowledged }]"
        >
          <div class="alert-header">
            <span class="alert-level">{{ alert.level }}</span>
            <span class="alert-rule">{{ alert.rule_name }}</span>
            <span v-if="alert.acknowledged" class="alert-ack">✓ 已确认</span>
          </div>
          <div class="alert-description">{{ alert.description }}</div>
          <div class="alert-meta">
            <span>当前值: {{ alert.value }}</span>
            <span>阈值: {{ alert.threshold }}</span>
            <span>{{ formatTime(alert.timestamp) }}</span>
          </div>
        </div>
        <div v-if="!metrics.alerts?.length" class="empty-alerts">
          暂无告警
        </div>
      </div>
    </div>

    <!-- 路径性能排行 -->
    <div class="paths-section">
      <div class="section-header">
        <h2>路径性能排行</h2>
      </div>
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>方法</th>
              <th>路径</th>
              <th>请求数</th>
              <th>平均耗时</th>
              <th>错误率</th>
              <th>慢请求数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(path, index) in metrics.paths" :key="index">
              <td><span class="method-badge" :class="path.method.toLowerCase()">{{ path.method }}</span></td>
              <td class="path-cell">{{ path.path }}</td>
              <td>{{ path.request_count }}</td>
              <td>{{ (path.average_duration || 0).toFixed(3) }}s</td>
              <td>{{ ((path.error_rate || 0) * 100).toFixed(2) }}%</td>
              <td>{{ path.slow_request_count || 0 }}</td>
            </tr>
            <tr v-if="!metrics.paths?.length">
              <td colspan="6" class="empty">暂无路径数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getMonitoringMetrics, cleanupFileLogsNow } from '@/api/monitoring'
import { extractErrorMessage, handleApiError, isErrorHandled } from '@/utils/api'

const metrics = ref({
  api: {},
  paths: [],
  slow_requests: [],
  resources: {},
  alerts: []
})

let updateInterval = null
let metricsLoading = false
const logsCleanupLoading = ref(false)
const logsCleanupHint = ref('')

const unacknowledgedCount = computed(() => {
  return metrics.value.alerts?.filter(a => !a.acknowledged).length || 0
})

const logsInfo = computed(() => metrics.value.resources?.logs || {})
const logsUsageMb = computed(() => Number(logsInfo.value.usage_mb || 0))
const logsSoftLimitMb = computed(() => Number(logsInfo.value.soft_limit_mb || 2048))
const logsHardLimitMb = computed(() => Number(logsInfo.value.hard_limit_mb || 4096))
const logsUsagePercent = computed(() => Number(logsInfo.value.usage_percent_soft || 0))
const logsSoftHit = computed(() => Boolean(logsInfo.value.soft_limit_hit))
const logsHardHit = computed(() => Boolean(logsInfo.value.hard_limit_hit))
const logQueueDroppedDelta = computed(() => Number(logsInfo.value.queue_dropped_delta || 0))
const logQueueUsageRatio = computed(() => Number(logsInfo.value.queue_usage_ratio || 0))

const formatTime = (timestamp) => {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const fetchMetrics = async () => {
  if (metricsLoading) return
  metricsLoading = true
  try {
    metrics.value = await getMonitoringMetrics()
  } catch (error) {
    handleApiError(error, '获取监控数据失败', { logContext: '监控仪表盘' })
  } finally {
    metricsLoading = false
  }
}

const handleLogsCleanup = async () => {
  if (logsCleanupLoading.value) return
  try {
    await ElMessageBox.confirm(
      '将清理超期轮转备份、归档 gzip、孤儿文件，并执行磁盘守卫。不会删除正在写入的活跃日志主文件。\n\n冷却默认 60 秒（优先 Redis 跨进程；Redis 不可用时仅本进程生效）。是否继续？',
      '立即清理文件日志',
      {
        confirmButtonText: '开始清理',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch {
    return
  }

  logsCleanupLoading.value = true
  logsCleanupHint.value = ''
  try {
    const data = await cleanupFileLogsNow()
    const result = data?.result || data || {}
    const deleted = Number(result.deleted_count || 0)
    const archived = Number(result.archived_count || 0)
    const freedMb = Number(result.bytes_freed || 0) / (1024 * 1024)
    const msg =
      data?.message ||
      result.message ||
      `清理完成：删除 ${deleted}，归档 ${archived}，释放约 ${freedMb.toFixed(1)} MB`
    const errors = Array.isArray(result.errors) ? result.errors.filter(Boolean) : []
    logsCleanupHint.value = errors.length ? `${msg}；部分失败：${errors.slice(0, 3).join('；')}` : msg
    if (errors.length) {
      ElMessage.warning(logsCleanupHint.value)
    } else {
      ElMessage.success(msg)
    }
    if (result.logs_stats) {
      metrics.value = {
        ...metrics.value,
        resources: {
          ...(metrics.value.resources || {}),
          logs: result.logs_stats,
        },
      }
    } else {
      await fetchMetrics()
    }
  } catch (error) {
    const errMsg = extractErrorMessage(error) || '清理失败'
    logsCleanupHint.value = errMsg
    if (!isErrorHandled(error)) {
      ElMessage.error(errMsg)
    }
  } finally {
    logsCleanupLoading.value = false
  }
}

onMounted(() => {
  fetchMetrics()
  updateInterval = setInterval(fetchMetrics, 10000)
})

onUnmounted(() => {
  if (updateInterval) {
    clearInterval(updateInterval)
  }
})
</script>

<style scoped>
.monitoring-dashboard {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 28px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 8px 0;
}

.subtitle {
  color: #6b7280;
  margin: 0;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.stat-icon.qps {
  background: #dbeafe;
}

.stat-icon.response-time {
  background: #fef3c7;
}

.stat-icon.error-rate {
  background: #fee2e2;
}

.stat-icon.request-count {
  background: #dcfce7;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #1f2937;
}

.stat-value.warning {
  color: #f59e0b;
}

.stat-label {
  font-size: 12px;
  color: #6b7280;
}

/* 资源使用 */
.resource-section,
.percentiles-section,
.slow-requests-section,
.alerts-section,
.paths-section {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.resource-section h2,
.percentiles-section h2,
.slow-requests-section h2,
.alerts-section h2,
.paths-section h2 {
  margin: 0 0 16px 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.badge {
  background: #10b981;
  color: #fff;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.badge.warning {
  background: #f59e0b;
}

.resource-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 16px;
}

.resource-card {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
}

.resource-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.resource-icon {
  font-size: 18px;
}

.resource-name {
  font-weight: 500;
  color: #374151;
}

.logs-cleanup-btn {
  margin-left: auto;
  border: 1px solid #d1d5db;
  background: #fff;
  color: #374151;
  font-size: 12px;
  line-height: 1;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
}

.logs-cleanup-btn:hover:not(:disabled) {
  border-color: #9ca3af;
  background: #f9fafb;
}

.logs-cleanup-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.logs-cleanup-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #6b7280;
  line-height: 1.4;
}

.resource-bar-container {
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
}

.resource-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.resource-bar.cpu {
  background: linear-gradient(90deg, #3b82f6, #1d4ed8);
}

.resource-bar.memory {
  background: linear-gradient(90deg, #10b981, #059669);
}

.resource-bar.disk {
  background: linear-gradient(90deg, #f59e0b, #d97706);
}

.resource-bar.logs {
  background: linear-gradient(90deg, #6366f1, #818cf8);
}

.resource-bar.logs.warn {
  background: linear-gradient(90deg, #f59e0b, #fbbf24);
}

.resource-bar.logs.critical {
  background: linear-gradient(90deg, #ef4444, #f87171);
}

.resource-card.resource-warn {
  box-shadow: 0 0 0 1px rgba(245, 158, 11, 0.35);
}

.resource-card.resource-critical {
  box-shadow: 0 0 0 1px rgba(239, 68, 68, 0.45);
}

.resource-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.resource-value {
  font-weight: 600;
  color: #1f2937;
}

.resource-range {
  font-size: 12px;
  color: #6b7280;
}

/* 百分位数 */
.percentiles-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.percentile-card {
  text-align: center;
  padding: 16px;
  background: #f9fafb;
  border-radius: 8px;
}

.percentile-label {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}

.percentile-value {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
}

.percentile-value.critical {
  color: #ef4444;
}

/* 表格 */
.table-container {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.data-table th {
  text-align: left;
  padding: 12px;
  background: #f9fafb;
  font-weight: 600;
  color: #374151;
  border-bottom: 2px solid #e5e7eb;
}

.data-table td {
  padding: 12px;
  border-bottom: 1px solid #e5e7eb;
  color: #4b5563;
}

.data-table tr:hover td {
  background: #f9fafb;
}

.data-table .empty {
  text-align: center;
  color: #9ca3af;
}

.method-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
}

.method-badge.get {
  background: #10b981;
}

.method-badge.post {
  background: #3b82f6;
}

.method-badge.put {
  background: #f59e0b;
}

.method-badge.delete {
  background: #ef4444;
}

.path-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.duration-cell {
  font-family: monospace;
}

/* 告警列表 */
.alerts-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.alert-item {
  padding: 16px;
  border-radius: 8px;
  border-left: 4px solid;
}

.alert-item.info {
  background: #eff6ff;
  border-color: #3b82f6;
}

.alert-item.warning {
  background: #fffbeb;
  border-color: #f59e0b;
}

.alert-item.error {
  background: #fef2f2;
  border-color: #ef4444;
}

.alert-item.critical {
  background: #fef2f2;
  border-color: #dc2626;
}

.alert-item.acknowledged {
  opacity: 0.6;
}

.alert-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.alert-level {
  font-weight: 700;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  color: #fff;
}

.alert-item.info .alert-level {
  background: #3b82f6;
}

.alert-item.warning .alert-level {
  background: #f59e0b;
}

.alert-item.error .alert-level {
  background: #ef4444;
}

.alert-item.critical .alert-level {
  background: #dc2626;
}

.alert-rule {
  font-weight: 600;
  color: #1f2937;
}

.alert-ack {
  margin-left: auto;
  font-size: 12px;
  color: #10b981;
}

.alert-description {
  color: #4b5563;
  margin-bottom: 8px;
}

.alert-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #6b7280;
}

.empty-alerts {
  text-align: center;
  padding: 32px;
  color: #9ca3af;
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .resource-grid {
    grid-template-columns: 1fr;
  }
  
  .percentiles-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .section-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>