<template>
  <div class="alert-management">
    <div class="page-header">
      <h1>告警管理</h1>
      <p class="subtitle">管理告警规则和查看告警记录</p>
    </div>

    <!-- 告警统计 -->
    <p class="stats-hint">
      以下为<strong>已触发</strong>的告警记录数量（非规则数）；指标未超阈值时尚无记录。
      当前已配置 {{ rules.length }} 条规则。
    </p>
    <div class="stats-row">
      <div class="stat-item">
        <span class="stat-num critical">{{ stats.critical }}</span>
        <span class="stat-label">严重</span>
      </div>
      <div class="stat-item">
        <span class="stat-num error">{{ stats.error }}</span>
        <span class="stat-label">错误</span>
      </div>
      <div class="stat-item">
        <span class="stat-num warning">{{ stats.warning }}</span>
        <span class="stat-label">警告</span>
      </div>
      <div class="stat-item">
        <span class="stat-num info">{{ stats.info }}</span>
        <span class="stat-label">信息</span>
      </div>
      <div class="stat-item">
        <span class="stat-num total">{{ stats.total }}</span>
        <span class="stat-label">总计</span>
      </div>
    </div>

    <!-- 告警规则列表 -->
    <div class="section">
      <div class="section-header">
        <h2>告警规则</h2>
        <button class="btn-primary" @click="showAddRuleModal = true">添加规则</button>
      </div>
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>规则名称</th>
              <th>指标名称</th>
              <th>比较方式</th>
              <th>阈值</th>
              <th>级别</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rule in rules" :key="rule.id">
              <td>{{ rule.rule_name }}</td>
              <td>{{ rule.metric_name }}</td>
              <td>{{ getOperatorText(rule.operator) }}</td>
              <td>{{ rule.threshold }}</td>
              <td><span class="level-badge" :class="rule.level.toLowerCase()">{{ rule.level }}</span></td>
              <td><span class="status-badge" :class="{ active: rule.enabled }">{{ rule.enabled ? '启用' : '禁用' }}</span></td>
              <td>
                <button class="btn-action" @click="toggleRule(rule)">
                  {{ rule.enabled ? '禁用' : '启用' }}
                </button>
                <button class="btn-action danger" @click="deleteRule(rule.id)">删除</button>
              </td>
            </tr>
            <tr v-if="!rules.length">
              <td colspan="7" class="empty">暂无告警规则</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 告警记录 -->
    <div class="section">
      <div class="section-header">
        <h2>告警记录</h2>
        <button class="btn-secondary" @click="acknowledgeAll">全部确认</button>
      </div>
      <div class="alerts-list">
        <div 
          v-for="alert in alerts" 
          :key="alert.id"
          class="alert-card"
          :class="[alert.level.toLowerCase(), { acknowledged: alert.acknowledged }]"
        >
          <div class="alert-header">
            <span class="alert-level">{{ alert.level }}</span>
            <span class="alert-rule">{{ alert.rule_name }}</span>
            <button 
              v-if="!alert.acknowledged" 
              class="btn-ack" 
              @click="acknowledgeAlertHandler(alert.id)"
            >确认</button>
          </div>
          <div class="alert-body">
            <p class="alert-description">{{ alert.description }}</p>
            <div class="alert-details">
              <span>指标: {{ alert.metric_name }}</span>
              <span>当前值: {{ alert.value }}</span>
              <span>阈值: {{ alert.threshold }}</span>
            </div>
          </div>
          <div class="alert-footer">
            <span>{{ formatTime(alert.timestamp) }}</span>
            <span v-if="alert.acknowledged" class="ack-status">✓ 已确认</span>
          </div>
        </div>
        <div v-if="!alerts.length" class="empty-state">
          暂无告警记录
        </div>
      </div>
    </div>

    <!-- 添加规则弹窗 -->
    <div v-if="showAddRuleModal" class="modal-overlay" @click.self="showAddRuleModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>添加告警规则</h3>
          <button class="modal-close" @click="showAddRuleModal = false">×</button>
        </div>
        <form @submit.prevent="addRule">
          <div class="form-group">
            <label>规则名称</label>
            <input v-model="newRule.rule_name" type="text" required />
          </div>
          <div class="form-group">
            <label>指标名称</label>
            <select v-model="newRule.metric_name" required>
              <option value="api.average_duration">API平均响应时间</option>
              <option value="api.error_rate">API错误率</option>
              <option value="api.slow_request_rate">API慢请求率</option>
              <option value="api.response_time_p95">API P95响应时间</option>
              <option value="api.response_time_p99">API P99响应时间</option>
              <option value="api.qps">API QPS</option>
              <option value="system.cpu_usage">CPU使用率</option>
              <option value="system.memory_usage">内存使用率</option>
              <option value="system.disk_usage">磁盘使用率</option>
              <option value="system.logs_usage_ratio_soft">日志目录/软限制（1=触顶）</option>
              <option value="system.logs_usage_ratio_hard">日志目录/硬限制（1=触顶）</option>
              <option value="system.logs_usage_mb">日志目录用量(MB)</option>
              <option value="system.log_queue_dropped_delta">日志队列本进程窗口丢弃数</option>
              <option value="system.log_queue_usage_ratio">日志队列本进程积压比例</option>
              <option value="system.log_queue_qsize">日志队列本进程当前长度</option>
              <option value="system.log_queue_dropped">日志队列本进程累计丢弃数</option>
            </select>
          </div>
          <div class="form-group">
            <label>比较方式</label>
            <select v-model="newRule.operator" required>
              <option value="gt">大于 (&gt;)</option>
              <option value="lt">小于 (&lt;)</option>
              <option value="ge">大于等于 (&gt;=)</option>
              <option value="le">小于等于 (&lt;=)</option>
            </select>
          </div>
          <div class="form-group">
            <label>阈值</label>
            <input v-model.number="newRule.threshold" type="number" step="any" required />
          </div>
          <div class="form-group">
            <label>告警级别</label>
            <select v-model="newRule.level" required>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
              <option value="CRITICAL">CRITICAL</option>
            </select>
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="newRule.description"></textarea>
          </div>
          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="showAddRuleModal = false">取消</button>
            <button type="submit" class="btn-primary">添加</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import {
  getAlertRules,
  getAlerts,
  createAlertRule,
  toggleAlertRule,
  deleteAlertRule,
  acknowledgeAlert,
  acknowledgeAllAlerts,
} from '@/api/monitoring'
import { handleApiError } from '@/utils/api'

const rules = ref([])
const alerts = ref([])
const showAddRuleModal = ref(false)

const DEFAULT_NEW_RULE = {
  rule_name: '',
  metric_name: 'api.average_duration',
  operator: 'gt',
  threshold: 0,
  level: 'WARNING',
  description: ''
}

const newRule = reactive({ ...DEFAULT_NEW_RULE })

const resetNewRuleForm = () => {
  Object.assign(newRule, DEFAULT_NEW_RULE)
}

const LEVEL_STAT_KEYS = {
  CRITICAL: 'critical',
  ERROR: 'error',
  WARNING: 'warning',
  INFO: 'info',
}

const stats = computed(() => {
  const counts = { critical: 0, error: 0, warning: 0, info: 0 }
  const list = Array.isArray(alerts.value) ? alerts.value : []
  list.forEach((alert) => {
    const key = LEVEL_STAT_KEYS[String(alert?.level || '').toUpperCase()]
    if (key) counts[key] += 1
  })
  return {
    ...counts,
    total: list.length,
  }
})

const getOperatorText = (operator) => {
  const operators = {
    gt: '大于',
    lt: '小于',
    ge: '大于等于',
    le: '小于等于'
  }
  return operators[operator] || operator
}

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

const fetchRules = async () => {
  try {
    rules.value = await getAlertRules()
  } catch (error) {
    handleApiError(error, '获取告警规则失败', { logContext: '告警管理' })
  }
}

const fetchAlerts = async () => {
  try {
    const data = await getAlerts({ limit: 500 })
    alerts.value = Array.isArray(data) ? data : []
  } catch (error) {
    handleApiError(error, '获取告警记录失败', { logContext: '告警管理' })
  }
}

let refreshTimer = null

const addRule = async () => {
  try {
    await createAlertRule({ ...newRule })
    await fetchRules()
    showAddRuleModal.value = false
    resetNewRuleForm()
  } catch (error) {
    handleApiError(error, '添加规则失败', { logContext: '告警管理' })
  }
}

const toggleRule = async (rule) => {
  try {
    const result = await toggleAlertRule(rule.id)
    if (result?.rule) {
      Object.assign(rule, result.rule)
    } else {
      rule.enabled = !rule.enabled
    }
  } catch (error) {
    handleApiError(error, '切换规则状态失败', { logContext: '告警管理' })
  }
}

const deleteRule = async (ruleId) => {
  if (!confirm('确定删除此规则？')) return
  try {
    await deleteAlertRule(ruleId)
    rules.value = rules.value.filter(r => r.id !== ruleId)
  } catch (error) {
    handleApiError(error, '删除规则失败', { logContext: '告警管理' })
  }
}

const acknowledgeAlertHandler = async (alertId) => {
  try {
    await acknowledgeAlert(alertId)
    const alert = alerts.value.find(a => a.id === alertId)
    if (alert) alert.acknowledged = true
  } catch (error) {
    handleApiError(error, '确认告警失败', { logContext: '告警管理' })
  }
}

const acknowledgeAll = async () => {
  try {
    await acknowledgeAllAlerts()
    alerts.value.forEach(alert => { alert.acknowledged = true })
  } catch (error) {
    handleApiError(error, '确认所有告警失败', { logContext: '告警管理' })
  }
}

onMounted(() => {
  fetchRules()
  fetchAlerts()
  refreshTimer = setInterval(() => {
    fetchAlerts()
  }, 15000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.alert-management {
  padding: 24px;
  max-width: 1200px;
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

.stats-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: #6b7280;
  line-height: 1.5;
}

/* 统计行 */
.stats-row {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.stat-item {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.stat-num {
  font-size: 28px;
  font-weight: 700;
  display: block;
}

.stat-num.critical { color: #dc2626; }
.stat-num.error { color: #ef4444; }
.stat-num.warning { color: #f59e0b; }
.stat-num.info { color: #3b82f6; }
.stat-num.total { color: #1f2937; }

.stat-label {
  font-size: 12px;
  color: #6b7280;
}

/* 按钮 */
.btn-primary, .btn-secondary, .btn-action {
  padding: 8px 16px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.btn-primary {
  background: #3b82f6;
  color: #fff;
}

.btn-secondary {
  background: #e5e7eb;
  color: #374151;
}

.btn-action {
  background: #f3f4f6;
  color: #374151;
  margin-right: 8px;
}

.btn-action.danger {
  background: #fee2e2;
  color: #dc2626;
}

.btn-ack {
  background: #10b981;
  color: #fff;
  border: none;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}

/* 区域 */
.section {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
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

.data-table .empty {
  text-align: center;
  color: #9ca3af;
}

.level-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
}

.level-badge.info { background: #3b82f6; }
.level-badge.warning { background: #f59e0b; }
.level-badge.error { background: #ef4444; }
.level-badge.critical { background: #dc2626; }

.status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.status-badge.active {
  background: #dcfce7;
  color: #059669;
}

.status-badge:not(.active) {
  background: #f3f4f6;
  color: #6b7280;
}

/* 告警卡片 */
.alerts-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.alert-card {
  padding: 16px;
  border-radius: 8px;
  border-left: 4px solid;
}

.alert-card.info {
  background: #eff6ff;
  border-color: #3b82f6;
}

.alert-card.warning {
  background: #fffbeb;
  border-color: #f59e0b;
}

.alert-card.error {
  background: #fef2f2;
  border-color: #ef4444;
}

.alert-card.critical {
  background: #fef2f2;
  border-color: #dc2626;
}

.alert-card.acknowledged {
  opacity: 0.6;
}

.alert-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.alert-level {
  font-weight: 700;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  color: #fff;
}

.alert-card.info .alert-level { background: #3b82f6; }
.alert-card.warning .alert-level { background: #f59e0b; }
.alert-card.error .alert-level { background: #ef4444; }
.alert-card.critical .alert-level { background: #dc2626; }

.alert-rule {
  flex: 1;
  font-weight: 600;
}

.alert-description {
  margin: 0 0 8px 0;
  color: #4b5563;
}

.alert-details {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #6b7280;
}

.alert-footer {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #9ca3af;
}

.ack-status {
  color: #10b981;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #9ca3af;
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #fff;
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
}

.modal-header h3 {
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6b7280;
}

.form-group {
  padding: 12px 20px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #374151;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
}

.form-group textarea {
  min-height: 60px;
  resize: vertical;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #e5e7eb;
}
</style>