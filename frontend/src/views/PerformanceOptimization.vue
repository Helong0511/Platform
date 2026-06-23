<template>
    <div class="performance-optimization">
        <div class="page-header">
            <h1>性能优化管理</h1>
            <p class="subtitle">建立性能优化闭环流程</p>
        </div>

        <!-- 优化效果概览 -->
        <div class="effectiveness-section">
            <h2>优化效果概览</h2>
            <div class="effectiveness-grid">
                <div class="effectiveness-card">
                    <div class="effectiveness-icon">📊</div>
                    <div class="effectiveness-info">
                        <div class="effectiveness-value">{{ effectiveness.total_plans || 0 }}</div>
                        <div class="effectiveness-label">总方案数</div>
                    </div>
                </div>
                <div class="effectiveness-card">
                    <div class="effectiveness-icon">✅</div>
                    <div class="effectiveness-info">
                        <div class="effectiveness-value">{{ effectiveness.verified_plans || 0 }}</div>
                        <div class="effectiveness-label">已验证方案</div>
                    </div>
                </div>
                <div class="effectiveness-card">
                    <div class="effectiveness-icon">📈</div>
                    <div class="effectiveness-info">
                        <div class="effectiveness-value">{{ ((effectiveness.avg_actual_improvement || 0) *
                            100).toFixed(1) }}%</div>
                        <div class="effectiveness-label">平均改进率</div>
                    </div>
                </div>
                <div class="effectiveness-card">
                    <div class="effectiveness-icon">⏱️</div>
                    <div class="effectiveness-info">
                        <div class="effectiveness-value">{{ effectiveness.total_effort_hours || 0 }}h</div>
                        <div class="effectiveness-label">总投入工时</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 瓶颈检测 -->
        <div class="bottlenecks-section">
            <div class="section-header">
                <h2>检测到的瓶颈</h2>
                <button class="btn-primary" @click="detectBottlenecks">🔍 检测瓶颈</button>
            </div>
            <div class="bottlenecks-list">
                <div v-for="(bottleneck, index) in bottlenecks" :key="index" class="bottleneck-card">
                    <div class="bottleneck-header">
                        <span class="bottleneck-type">{{ getBottleneckTypeName(bottleneck.bottleneck_type) }}</span>
                        <span class="bottleneck-time">{{ formatTime(bottleneck.timestamp) }}</span>
                    </div>
                    <p class="bottleneck-description">{{ bottleneck.description }}</p>
                    <div class="bottleneck-metrics">
                        <span>当前值: {{ bottleneck.current_value }}</span>
                        <span>阈值: {{ bottleneck.threshold }}</span>
                    </div>
                </div>
                <div v-if="!bottlenecks.length" class="empty-state">
                    暂无检测到的瓶颈
                </div>
            </div>
        </div>

        <!-- 优化方案列表 -->
        <div class="plans-section">
            <div class="section-header">
                <h2>优化方案</h2>
                <button class="btn-primary" @click="showAddPlanModal = true">+ 添加方案</button>
            </div>
            <div class="plans-grid">
                <div v-for="plan in plans" :key="plan.id" class="plan-card" :class="plan.status.toLowerCase()">
                    <div class="plan-header">
                        <span class="plan-status" :class="plan.status.toLowerCase()">{{ getStatusText(plan.status)
                            }}</span>
                        <span class="plan-priority" :class="plan.priority.toLowerCase()">{{ plan.priority }}</span>
                    </div>
                    <h3 class="plan-title">{{ plan.title }}</h3>
                    <p class="plan-description">{{ plan.description }}</p>
                    <div class="plan-details">
                        <div class="detail-item">
                            <span class="detail-label">瓶颈类型</span>
                            <span class="detail-value">{{ getBottleneckTypeName(plan.bottleneck_type) }}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">预估工时</span>
                            <span class="detail-value">{{ plan.estimated_effort }}h</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">预期改进</span>
                            <span class="detail-value">{{ (plan.expected_improvement * 100).toFixed(0) }}%</span>
                        </div>
                        <div v-if="plan.actual_improvement" class="detail-item">
                            <span class="detail-label">实际改进</span>
                            <span class="detail-value highlight">{{ (plan.actual_improvement * 100).toFixed(1)
                                }}%</span>
                        </div>
                    </div>
                    <div class="plan-actions">
                        <button v-if="plan.status === 'PENDING'" @click="approvePlan(plan.id)"
                            class="btn-action approve">批准</button>
                        <button v-if="plan.status === 'APPROVED'" @click="startPlan(plan.id)"
                            class="btn-action start">开始</button>
                        <button v-if="plan.status === 'IMPLEMENTING'" @click="completePlan(plan.id)"
                            class="btn-action complete">完成</button>
                        <button v-if="plan.status === 'COMPLETED'" @click="verifyPlan(plan.id)"
                            class="btn-action verify">验证</button>
                        <button v-if="plan.status === 'PENDING'" @click="rejectPlan(plan.id)"
                            class="btn-action reject">拒绝</button>
                        <button @click="viewPlan(plan)" class="btn-action view">详情</button>
                    </div>
                </div>
                <div v-if="!plans.length" class="empty-state">
                    暂无优化方案
                </div>
            </div>
        </div>

        <!-- 添加方案弹窗 -->
        <div v-if="showAddPlanModal" class="modal-overlay" @click.self="showAddPlanModal = false">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>添加优化方案</h3>
                    <button class="modal-close" @click="showAddPlanModal = false">×</button>
                </div>
                <form @submit.prevent="addPlan">
                    <div class="form-group">
                        <label>方案标题</label>
                        <input v-model="newPlan.title" type="text" required />
                    </div>
                    <div class="form-group">
                        <label>方案描述</label>
                        <textarea v-model="newPlan.description" required></textarea>
                    </div>
                    <div class="form-group">
                        <label>瓶颈类型</label>
                        <select v-model="newPlan.bottleneck_type" required>
                            <option value="API_RESPONSE_TIME">API响应时间</option>
                            <option value="HIGH_ERROR_RATE">高错误率</option>
                            <option value="HIGH_CPU_USAGE">高CPU使用率</option>
                            <option value="HIGH_MEMORY_USAGE">高内存使用率</option>
                            <option value="DATABASE_QUERY">数据库查询慢</option>
                            <option value="NETWORK_LATENCY">网络延迟</option>
                            <option value="THROUGHPUT">吞吐量不足</option>
                            <option value="MEMORY_LEAK">内存泄漏</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>优先级</label>
                        <select v-model="newPlan.priority" required>
                            <option value="CRITICAL">CRITICAL</option>
                            <option value="HIGH">HIGH</option>
                            <option value="MEDIUM">MEDIUM</option>
                            <option value="LOW">LOW</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>预估工时（小时）</label>
                        <input v-model.number="newPlan.estimated_effort" type="number" min="1" required />
                    </div>
                    <div class="form-group">
                        <label>预期改进率</label>
                        <input v-model.number="newPlan.expected_improvement" type="number" min="0" max="1" step="0.01"
                            required />
                        <span class="input-hint">0.2 表示预期改进20%</span>
                    </div>
                    <div class="form-group">
                        <label>负责人</label>
                        <input v-model="newPlan.owner" type="text" />
                    </div>
                    <div class="form-actions">
                        <button type="button" class="btn-secondary" @click="showAddPlanModal = false">取消</button>
                        <button type="submit" class="btn-primary">添加</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- 方案详情弹窗 -->
        <div v-if="selectedPlan" class="modal-overlay" @click.self="selectedPlan = null">
            <div class="modal-content large">
                <div class="modal-header">
                    <h3>{{ selectedPlan.title }}</h3>
                    <button class="modal-close" @click="selectedPlan = null">×</button>
                </div>
                <div class="plan-details-full">
                    <div class="detail-row">
                        <span class="detail-label">状态</span>
                        <span class="detail-value"><span class="status-badge"
                                :class="selectedPlan.status.toLowerCase()">{{ getStatusText(selectedPlan.status)
                                }}</span></span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">优先级</span>
                        <span class="detail-value"><span class="priority-badge"
                                :class="selectedPlan.priority.toLowerCase()">{{ selectedPlan.priority }}</span></span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">瓶颈类型</span>
                        <span class="detail-value">{{ getBottleneckTypeName(selectedPlan.bottleneck_type) }}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">描述</span>
                        <span class="detail-value">{{ selectedPlan.description }}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">负责人</span>
                        <span class="detail-value">{{ selectedPlan.owner || '-' }}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">预估工时</span>
                        <span class="detail-value">{{ selectedPlan.estimated_effort }} 小时</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">预期改进</span>
                        <span class="detail-value">{{ (selectedPlan.expected_improvement * 100).toFixed(0) }}%</span>
                    </div>
                    <div v-if="selectedPlan.actual_improvement" class="detail-row">
                        <span class="detail-label">实际改进</span>
                        <span class="detail-value highlight">{{ (selectedPlan.actual_improvement * 100).toFixed(1)
                            }}%</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">创建时间</span>
                        <span class="detail-value">{{ formatTime(selectedPlan.created_at) }}</span>
                    </div>
                    <div v-if="selectedPlan.metrics_before" class="metrics-compare">
                        <h4>优化前后对比</h4>
                        <div class="metrics-grid">
                            <div class="metric-item">
                                <span class="metric-label">优化前平均响应时间</span>
                                <span class="metric-value">{{ (selectedPlan.metrics_before.api?.average_duration ||
                                    0).toFixed(3) }}s</span>
                            </div>
                            <div class="metric-item">
                                <span class="metric-label">优化后平均响应时间</span>
                                <span class="metric-value">{{ (selectedPlan.metrics_after.api?.average_duration ||
                                    0).toFixed(3) }}s</span>
                            </div>
                            <div class="metric-item">
                                <span class="metric-label">优化前QPS</span>
                                <span class="metric-value">{{ selectedPlan.metrics_before.api?.qps || 0 }}</span>
                            </div>
                            <div class="metric-item">
                                <span class="metric-label">优化后QPS</span>
                                <span class="metric-value">{{ selectedPlan.metrics_after.api?.qps || 0 }}</span>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="form-actions">
                    <button class="btn-secondary" @click="selectedPlan = null">关闭</button>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import {
  getBottlenecks,
  detectBottlenecks as detectBottlenecksApi,
  getOptimizationPlans,
  getOptimizationEffectiveness,
  createOptimizationPlan,
  approveOptimizationPlan,
  startOptimizationPlan,
  completeOptimizationPlan,
  verifyOptimizationPlan,
  rejectOptimizationPlan,
} from '@/api/optimization'
import { handleApiError } from '@/utils/api'

const bottlenecks = ref([])
const plans = ref([])
const effectiveness = ref({})
const showAddPlanModal = ref(false)
const selectedPlan = ref(null)

const newPlan = reactive({
    title: '',
    description: '',
    bottleneck_type: 'API_RESPONSE_TIME',
    priority: 'MEDIUM',
    estimated_effort: 8,
    expected_improvement: 0.2,
    owner: ''
})

const getBottleneckTypeName = (type) => {
    const types = {
        API_RESPONSE_TIME: 'API响应时间',
        HIGH_ERROR_RATE: '高错误率',
        HIGH_CPU_USAGE: '高CPU使用率',
        HIGH_MEMORY_USAGE: '高内存使用率',
        DATABASE_QUERY: '数据库查询慢',
        NETWORK_LATENCY: '网络延迟',
        THROUGHPUT: '吞吐量不足',
        MEMORY_LEAK: '内存泄漏'
    }
    return types[type] || type
}

const getStatusText = (status) => {
    const texts = {
        PENDING: '待审核',
        APPROVED: '已批准',
        IMPLEMENTING: '实施中',
        COMPLETED: '已完成',
        VERIFIED: '已验证',
        REJECTED: '已拒绝'
    }
    return texts[status] || status
}

const formatTime = (timestamp) => {
    if (!timestamp) return '-'
    const date = new Date(timestamp)
    return date.toLocaleString('zh-CN')
}

const fetchBottlenecks = async () => {
  try {
    bottlenecks.value = await getBottlenecks()
  } catch (error) {
    handleApiError(error, '获取瓶颈列表失败', { logContext: '性能优化' })
  }
}

const fetchPlans = async () => {
  try {
    plans.value = await getOptimizationPlans()
  } catch (error) {
    handleApiError(error, '获取优化方案失败', { logContext: '性能优化' })
  }
}

const fetchEffectiveness = async () => {
  try {
    effectiveness.value = await getOptimizationEffectiveness()
  } catch (error) {
    handleApiError(error, '获取优化效果失败', { logContext: '性能优化' })
  }
}

const detectBottlenecks = async () => {
  try {
    const data = await detectBottlenecksApi()
    await fetchBottlenecks()
    alert(data.message)
  } catch (error) {
    handleApiError(error, '检测瓶颈失败', { logContext: '性能优化' })
  }
}

const addPlan = async () => {
  try {
    await createOptimizationPlan({ ...newPlan })
    await fetchPlans()
    showAddPlanModal.value = false
    Object.assign(newPlan, {
      title: '',
      description: '',
      bottleneck_type: 'API_RESPONSE_TIME',
      priority: 'MEDIUM',
      estimated_effort: 8,
      expected_improvement: 0.2,
      owner: '',
    })
  } catch (error) {
    handleApiError(error, '添加方案失败', { logContext: '性能优化' })
  }
}

const approvePlan = async (planId) => {
  try {
    await approveOptimizationPlan(planId)
    await fetchPlans()
  } catch (error) {
    handleApiError(error, '批准方案失败', { logContext: '性能优化' })
  }
}

const startPlan = async (planId) => {
  try {
    await startOptimizationPlan(planId)
    await fetchPlans()
  } catch (error) {
    handleApiError(error, '开始方案失败', { logContext: '性能优化' })
  }
}

const completePlan = async (planId) => {
  try {
    await completeOptimizationPlan(planId)
    await fetchPlans()
  } catch (error) {
    handleApiError(error, '完成方案失败', { logContext: '性能优化' })
  }
}

const verifyPlan = async (planId) => {
  try {
    await verifyOptimizationPlan(planId)
    await fetchPlans()
    await fetchEffectiveness()
  } catch (error) {
    handleApiError(error, '验证方案失败', { logContext: '性能优化' })
  }
}

const rejectPlan = async (planId) => {
  const reason = prompt('请输入拒绝原因:')
  if (reason === null) return
  try {
    await rejectOptimizationPlan(planId, reason)
    await fetchPlans()
  } catch (error) {
    handleApiError(error, '拒绝方案失败', { logContext: '性能优化' })
  }
}

const viewPlan = (plan) => {
    selectedPlan.value = plan
}

onMounted(() => {
    fetchBottlenecks()
    fetchPlans()
    fetchEffectiveness()
})
</script>

<style scoped>
.performance-optimization {
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

/* 效果概览 */
.effectiveness-section {
    background: #fff;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 24px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.effectiveness-section h2 {
    margin: 0 0 16px 0;
    font-size: 18px;
    font-weight: 600;
}

.effectiveness-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
}

.effectiveness-card {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px;
    background: #f9fafb;
    border-radius: 8px;
}

.effectiveness-icon {
    font-size: 32px;
}

.effectiveness-info {
    flex: 1;
}

.effectiveness-value {
    font-size: 24px;
    font-weight: 700;
    color: #1f2937;
}

.effectiveness-label {
    font-size: 12px;
    color: #6b7280;
}

/* 按钮 */
.btn-primary,
.btn-secondary,
.btn-action {
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
    margin-right: 8px;
    font-size: 12px;
    padding: 4px 12px;
}

.btn-action.approve {
    background: #10b981;
    color: #fff;
}

.btn-action.start {
    background: #3b82f6;
    color: #fff;
}

.btn-action.complete {
    background: #f59e0b;
    color: #fff;
}

.btn-action.verify {
    background: #8b5cf6;
    color: #fff;
}

.btn-action.reject {
    background: #ef4444;
    color: #fff;
}

.btn-action.view {
    background: #e5e7eb;
    color: #374151;
}

/* 区域通用 */
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

/* 瓶颈列表 */
.bottlenecks-section {
    background: #fff;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 24px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.bottlenecks-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.bottleneck-card {
    padding: 16px;
    background: #fffbeb;
    border-radius: 8px;
    border-left: 4px solid #f59e0b;
}

.bottleneck-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
}

.bottleneck-type {
    font-weight: 600;
    color: #92400e;
}

.bottleneck-time {
    font-size: 12px;
    color: #6b7280;
}

.bottleneck-description {
    margin: 0 0 8px 0;
    color: #4b5563;
}

.bottleneck-metrics {
    display: flex;
    gap: 16px;
    font-size: 12px;
    color: #6b7280;
}

/* 方案列表 */
.plans-section {
    background: #fff;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.plans-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
    gap: 16px;
}

.plan-card {
    padding: 16px;
    border-radius: 8px;
    border-left: 4px solid;
}

.plan-card.pending {
    background: #f3f4f6;
    border-color: #9ca3af;
}

.plan-card.approved {
    background: #eff6ff;
    border-color: #3b82f6;
}

.plan-card.implementing {
    background: #fef3c7;
    border-color: #f59e0b;
}

.plan-card.completed {
    background: #dcfce7;
    border-color: #10b981;
}

.plan-card.verified {
    background: #e0e7ff;
    border-color: #8b5cf6;
}

.plan-card.rejected {
    background: #fee2e2;
    border-color: #ef4444;
}

.plan-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}

.plan-status {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 4px;
}

.plan-status.pending {
    background: #e5e7eb;
    color: #6b7280;
}

.plan-status.approved {
    background: #dbeafe;
    color: #1d4ed8;
}

.plan-status.implementing {
    background: #fef3c7;
    color: #d97706;
}

.plan-status.completed {
    background: #dcfce7;
    color: #059669;
}

.plan-status.verified {
    background: #e0e7ff;
    color: #6d28d9;
}

.plan-status.rejected {
    background: #fee2e2;
    color: #dc2626;
}

.plan-priority {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 4px;
}

.plan-priority.critical {
    background: #fee2e2;
    color: #dc2626;
}

.plan-priority.high {
    background: #fed7aa;
    color: #ea580c;
}

.plan-priority.medium {
    background: #fef3c7;
    color: #d97706;
}

.plan-priority.low {
    background: #dcfce7;
    color: #059669;
}

.plan-title {
    margin: 0 0 8px 0;
    font-size: 16px;
    font-weight: 600;
    color: #1f2937;
}

.plan-description {
    margin: 0 0 12px 0;
    font-size: 14px;
    color: #6b7280;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.plan-details {
    margin-bottom: 12px;
}

.detail-item {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    font-size: 13px;
}

.detail-label {
    color: #6b7280;
}

.detail-value {
    color: #374151;
    font-weight: 500;
}

.detail-value.highlight {
    color: #10b981;
}

.plan-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}

.empty-state {
    text-align: center;
    padding: 40px;
    color: #9ca3af;
    background: #f9fafb;
    border-radius: 8px;
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

.modal-content.large {
    max-width: 700px;
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
    min-height: 80px;
    resize: vertical;
}

.input-hint {
    display: block;
    font-size: 12px;
    color: #9ca3af;
    margin-top: 4px;
}

.form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    padding: 16px 20px;
    border-top: 1px solid #e5e7eb;
}

/* 方案详情 */
.plan-details-full {
    padding: 20px;
}

.detail-row {
    display: flex;
    padding: 12px 0;
    border-bottom: 1px solid #f3f4f6;
}

.detail-row:last-child {
    border-bottom: none;
}

.detail-row .detail-label {
    width: 120px;
    font-weight: 500;
    color: #6b7280;
}

.detail-row .detail-value {
    flex: 1;
    color: #1f2937;
}

.status-badge {
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 14px;
}

.priority-badge {
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 14px;
}

.metrics-compare {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #e5e7eb;
}

.metrics-compare h4 {
    margin: 0 0 12px 0;
    font-size: 16px;
}

.metrics-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
}

.metric-item {
    padding: 12px;
    background: #f9fafb;
    border-radius: 8px;
}

.metric-label {
    display: block;
    font-size: 12px;
    color: #6b7280;
    margin-bottom: 4px;
}

.metric-value {
    font-weight: 600;
    color: #1f2937;
}

@media (max-width: 768px) {
    .effectiveness-grid {
        grid-template-columns: repeat(2, 1fr);
    }

    .plans-grid {
        grid-template-columns: 1fr;
    }

    .metrics-grid {
        grid-template-columns: 1fr;
    }

    .detail-row {
        flex-direction: column;
        gap: 4px;
    }

    .detail-row .detail-label {
        width: auto;
    }
}
</style>