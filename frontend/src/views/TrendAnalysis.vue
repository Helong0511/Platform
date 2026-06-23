<template>
  <div class="trend-analysis">
    <div class="page-header">
      <h1>趋势分析与预测</h1>
      <p class="subtitle">查看历史数据趋势和未来预测</p>
    </div>

    <!-- 时间范围选择 -->
    <div class="time-selector">
      <span>时间范围:</span>
      <button 
        v-for="range in timeRanges" 
        :key="range.value"
        class="time-btn"
        :class="{ active: selectedRange === range.value }"
        @click="selectedRange = range.value"
      >
        {{ range.label }}
      </button>
    </div>

    <!-- 图表区域 -->
    <div class="charts-grid">
      <div class="chart-card">
        <h3>响应时间趋势</h3>
        <div class="chart-container">
          <canvas ref="responseTimeChart"></canvas>
        </div>
      </div>
      <div class="chart-card">
        <h3>QPS 趋势</h3>
        <div class="chart-container">
          <canvas ref="qpsChart"></canvas>
        </div>
      </div>
      <div class="chart-card">
        <h3>错误率趋势</h3>
        <div class="chart-container">
          <canvas ref="errorRateChart"></canvas>
        </div>
      </div>
      <div class="chart-card">
        <h3>资源使用率</h3>
        <div class="chart-container">
          <canvas ref="resourceChart"></canvas>
        </div>
      </div>
    </div>

    <!-- 预测数据 -->
    <div class="prediction-section">
      <h2>趋势预测</h2>
      <div class="prediction-grid">
        <div class="prediction-card">
          <div class="prediction-header">
            <span class="prediction-icon">⏱️</span>
            <span class="prediction-title">响应时间预测</span>
          </div>
          <div class="prediction-content">
            <div class="prediction-item">
              <span class="label">未来1小时平均</span>
              <span class="value">{{ predictedDurationAtHorizon.toFixed(3) }}s</span>
            </div>
            <div class="prediction-item">
              <span class="label">预测趋势</span>
              <span class="value" :class="getTrendClass(responseTimeTrend)">
                {{ responseTimeTrend }}
              </span>
            </div>
          </div>
        </div>
        <div class="prediction-card">
          <div class="prediction-header">
            <span class="prediction-icon">📊</span>
            <span class="prediction-title">错误率预测</span>
          </div>
          <div class="prediction-content">
            <div class="prediction-item">
              <span class="label">未来1小时平均</span>
              <span class="value">{{ (predictedErrorRateAtHorizon * 100).toFixed(2) }}%</span>
            </div>
            <div class="prediction-item">
              <span class="label">预测趋势</span>
              <span class="value" :class="getTrendClass(errorRateTrend)">
                {{ errorRateTrend }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 统计摘要 -->
    <div class="summary-section">
      <h2>统计摘要</h2>
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-label">平均响应时间</span>
          <span class="summary-value">{{ summary.avg_duration?.toFixed(3) || 0 }}s</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">峰值QPS</span>
          <span class="summary-value">{{ summary.peak_qps || 0 }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">总请求数</span>
          <span class="summary-value">{{ summary.total_requests || 0 }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">平均错误率</span>
          <span class="summary-value">{{ ((summary.avg_error_rate || 0) * 100).toFixed(2) }}%</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">最大CPU使用率</span>
          <span class="summary-value">{{ summary.max_cpu?.toFixed(1) || 0 }}%</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">最大内存使用率</span>
          <span class="summary-value">{{ summary.max_memory?.toFixed(1) || 0 }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { getTrendData, getTrendPredict, getTrendSummary } from '@/api/monitoring'
import { handleApiError } from '@/utils/api'
import { lineChartIndexToX, prepareCanvasForDisplay } from '@/utils/canvasDisplay'
import {
  PREDICTION_HORIZON_MINUTES,
  pickPredictionValue,
} from '@/utils/trendPrediction'

const selectedRange = ref('6h')
const trendData = ref({})
const prediction = ref({})
const predictionSteps = ref(PREDICTION_HORIZON_MINUTES)
const summary = ref({})

const responseTimeChart = ref(null)
const qpsChart = ref(null)
const errorRateChart = ref(null)
const resourceChart = ref(null)

const timeRanges = [
  { label: '1小时', value: '1h' },
  { label: '6小时', value: '6h' },
  { label: '24小时', value: '24h' },
  { label: '7天', value: '7d' }
]

/** 对比前半段与后半段均值，判断序列趋势（短序列用对半切分，长序列用最近5 vs 前5） */
function computeSeriesTrend(values) {
  if (!values || values.length < 2) return '稳定'

  let earlier
  let recent
  if (values.length >= 10) {
    recent = values.slice(-5)
    earlier = values.slice(-10, -5)
  } else {
    const mid = Math.max(1, Math.floor(values.length / 2))
    earlier = values.slice(0, mid)
    recent = values.slice(mid)
  }

  if (!earlier.length || !recent.length) return '稳定'

  const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length
  const earlierAvg = earlier.reduce((a, b) => a + b, 0) / earlier.length
  if (!Number.isFinite(recentAvg) || !Number.isFinite(earlierAvg)) return '稳定'

  if (recentAvg > earlierAvg * 1.1) return '上升'
  if (recentAvg < earlierAvg * 0.9) return '下降'
  return '稳定'
}

const responseTimeTrend = computed(() => {
  return computeSeriesTrend(trendData.value.avg_durations || [])
})

const errorRateTrend = computed(() => {
  return computeSeriesTrend(trendData.value.error_rates || [])
})

const predictedDurationAtHorizon = computed(() =>
  pickPredictionValue(
    prediction.value.predicted_avg_durations,
    PREDICTION_HORIZON_MINUTES,
    predictionSteps.value,
  )
)

const predictedErrorRateAtHorizon = computed(() =>
  pickPredictionValue(
    prediction.value.predicted_error_rates,
    PREDICTION_HORIZON_MINUTES,
    predictionSteps.value,
  )
)

const getTrendClass = (trend) => {
  return {
    'trend-up': trend === '上升',
    'trend-down': trend === '下降',
    'trend-stable': trend === '稳定'
  }
}

const fetchTrendData = async () => {
  try {
    const hours = getHours(selectedRange.value)
    const [trend, pred, summaryData] = await Promise.all([
      getTrendData(hours),
      getTrendPredict(PREDICTION_HORIZON_MINUTES),
      getTrendSummary(hours),
    ])
    predictionSteps.value = PREDICTION_HORIZON_MINUTES
    trendData.value = trend
    prediction.value = pred
    summary.value = summaryData

    await nextTick()
    renderCharts()
  } catch (error) {
    handleApiError(error, '获取趋势数据失败', { logContext: '趋势分析' })
  }
}

const getHours = (range) => {
  const hours = {
    '1h': 1,
    '6h': 6,
    '24h': 24,
    '7d': 168
  }
  return hours[range] || 6
}

const renderCharts = () => {
  // 使用简单的条形图展示数据
  renderResponseTimeChart()
  renderQpsChart()
  renderErrorRateChart()
  renderResourceChart()
}

const renderResponseTimeChart = () => {
  const canvas = responseTimeChart.value
  if (!canvas || !trendData.value.timestamps) return

  const prepared = prepareCanvasForDisplay(canvas)
  if (!prepared) return

  const { ctx, width, height } = prepared
  const data = trendData.value.avg_durations || []
  const maxValue = Math.max(...data, 1)

  drawSimpleBarChart(ctx, width, height, data, maxValue, '#3b82f6')
}

const renderQpsChart = () => {
  const canvas = qpsChart.value
  if (!canvas || !trendData.value.timestamps) return

  const prepared = prepareCanvasForDisplay(canvas)
  if (!prepared) return

  const { ctx, width, height } = prepared
  const data = trendData.value.qps_values || []
  const maxValue = Math.max(...data, 1)

  drawSimpleBarChart(ctx, width, height, data, maxValue, '#10b981')
}

const renderErrorRateChart = () => {
  const canvas = errorRateChart.value
  if (!canvas || !trendData.value.timestamps) return

  const prepared = prepareCanvasForDisplay(canvas)
  if (!prepared) return

  const { ctx, width, height } = prepared
  const data = trendData.value.error_rates || []
  const maxValue = Math.max(...data, 0.1)

  drawSimpleBarChart(ctx, width, height, data, maxValue, '#ef4444')
}

const renderResourceChart = () => {
  const canvas = resourceChart.value
  if (!canvas || !trendData.value.timestamps) return

  const prepared = prepareCanvasForDisplay(canvas)
  if (!prepared) return

  const { ctx, width, height } = prepared
  const cpuData = trendData.value.cpu_values || []
  const memData = trendData.value.memory_values || []
  const pointCount = Math.min(cpuData.length, memData.length)

  drawDualLineChart(
    ctx,
    width,
    height,
    cpuData.slice(0, pointCount),
    memData.slice(0, pointCount),
    100,
  )
}

const drawSimpleBarChart = (ctx, width, height, data, maxValue, color) => {
  ctx.clearRect(0, 0, width, height)
  
  if (!data.length) {
    ctx.fillStyle = '#9ca3af'
    ctx.font = '14px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('暂无数据', width / 2, height / 2)
    return
  }
  
  const padding = 40
  const chartWidth = width - padding * 2
  const chartHeight = height - padding * 2
  const barWidth = Math.max(2, (chartWidth / data.length) * 0.8)
  const gap = chartWidth / data.length - barWidth
  
  ctx.fillStyle = '#6b7280'
  ctx.font = '10px sans-serif'
  
  for (let i = 0; i < data.length; i += Math.max(1, Math.floor(data.length / 10))) {
    const x = padding + i * (barWidth + gap)
    ctx.fillText(String(i), x, height - 10)
  }
  
  for (let i = 0; i <= 4; i++) {
    const y = padding + (chartHeight / 4) * i
    const value = (maxValue * (4 - i)) / 4
    ctx.fillText(value.toFixed(2), 5, y + 3)
    ctx.strokeStyle = '#e5e7eb'
    ctx.beginPath()
    ctx.moveTo(padding, y)
    ctx.lineTo(width - padding, y)
    ctx.stroke()
  }
  
  ctx.fillStyle = color
  data.forEach((value, index) => {
    const x = padding + index * (barWidth + gap)
    const barHeight = (value / maxValue) * chartHeight
    ctx.fillRect(x, padding + chartHeight - barHeight, barWidth, barHeight)
  })
}

const drawDualLineChart = (ctx, width, height, data1, data2, maxValue) => {
  ctx.clearRect(0, 0, width, height)
  
  if (!data1.length || !data2.length) {
    ctx.fillStyle = '#9ca3af'
    ctx.font = '14px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('暂无数据', width / 2, height / 2)
    return
  }
  
  const padding = 40
  const chartWidth = width - padding * 2
  const chartHeight = height - padding * 2
  
  ctx.fillStyle = '#6b7280'
  ctx.font = '10px sans-serif'
  
  for (let i = 0; i <= 4; i++) {
    const y = padding + (chartHeight / 4) * i
    const value = ((4 - i) / 4) * maxValue
    ctx.fillText(value.toFixed(0) + '%', 5, y + 3)
    ctx.strokeStyle = '#e5e7eb'
    ctx.beginPath()
    ctx.moveTo(padding, y)
    ctx.lineTo(width - padding, y)
    ctx.stroke()
  }
  
  const drawLine = (data, color) => {
    if (!data.length) {
      return
    }

    ctx.strokeStyle = color
    ctx.lineWidth = 2

    if (data.length === 1) {
      const x = lineChartIndexToX(0, 1, padding, chartWidth)
      const y = padding + chartHeight - (data[0] / maxValue) * chartHeight
      ctx.fillStyle = color
      ctx.beginPath()
      ctx.arc(x, y, 4, 0, Math.PI * 2)
      ctx.fill()
      return
    }

    ctx.beginPath()
    data.forEach((value, index) => {
      const x = lineChartIndexToX(index, data.length, padding, chartWidth)
      const y = padding + chartHeight - (value / maxValue) * chartHeight
      if (index === 0) {
        ctx.moveTo(x, y)
      } else {
        ctx.lineTo(x, y)
      }
    })
    ctx.stroke()
  }
  
  drawLine(data1, '#3b82f6')
  drawLine(data2, '#10b981')
  
  ctx.font = '10px sans-serif'
  ctx.fillStyle = '#3b82f6'
  ctx.fillText('CPU', width - padding + 5, padding + 15)
  ctx.fillStyle = '#10b981'
  ctx.fillText('内存', width - padding + 5, padding + 30)
}

const handleChartResize = () => {
  if (trendData.value.timestamps?.length) {
    renderCharts()
  }
}

onMounted(() => {
  fetchTrendData()
  window.addEventListener('resize', handleChartResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleChartResize)
})

watch(selectedRange, () => {
  fetchTrendData()
})
</script>

<style scoped>
.trend-analysis {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 20px;
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

/* 时间选择器 */
.time-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.time-selector span {
  color: #6b7280;
}

.time-btn {
  padding: 8px 16px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
  color: #374151;
}

.time-btn.active {
  background: #3b82f6;
  color: #fff;
  border-color: #3b82f6;
}

/* 图表网格 */
.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}

.chart-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.chart-card h3 {
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
  color: #374151;
}

.chart-container {
  height: 200px;
}

.chart-container canvas {
  display: block;
}

/* 预测区域 */
.prediction-section {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.prediction-section h2 {
  margin: 0 0 16px 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.prediction-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
}

.prediction-card {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
}

.prediction-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.prediction-icon {
  font-size: 20px;
}

.prediction-title {
  font-weight: 600;
  color: #374151;
}

.prediction-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prediction-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.prediction-item .label {
  font-size: 14px;
  color: #6b7280;
}

.prediction-item .value {
  font-weight: 600;
  color: #1f2937;
}

.trend-up { color: #ef4444; }
.trend-down { color: #10b981; }
.trend-stable { color: #6b7280; }

/* 统计摘要 */
.summary-section {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.summary-section h2 {
  margin: 0 0 16px 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.summary-item {
  text-align: center;
  padding: 12px;
  background: #f9fafb;
  border-radius: 8px;
}

.summary-label {
  display: block;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}

.summary-value {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
}

@media (max-width: 768px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
  
  .prediction-grid {
    grid-template-columns: 1fr;
  }
  
  .summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>