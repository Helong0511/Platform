<!-- Offer 统计面板（生产 OfferManagement 详情 Tab 使用） -->
<template>
  <div class="offer-stats-panel" v-loading="loading">
    <div class="panel-toolbar">
      <span class="toolbar-title">数据概览</span>
      <el-select v-model="timeRange" size="default" @change="handleTimeRangeChange">
        <el-option label="今日" value="day" />
        <el-option label="本周" value="week" />
        <el-option label="本月" value="month" />
      </el-select>
    </div>

    <el-row :gutter="16" class="stats-row">
      <el-col :span="6">
        <div class="stat-item">
          <div class="stat-label">总点击</div>
          <div class="stat-value">{{ stats.clicks || 0 }}</div>
          <div class="stat-trend" :class="trends.clicks >= 0 ? 'up' : 'down'">
            {{ trends.clicks >= 0 ? '↑' : '↓' }} {{ Math.abs(trends.clicks) }}%
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-item">
          <div class="stat-label">总转化</div>
          <div class="stat-value">{{ stats.conversions || 0 }}</div>
          <div class="stat-trend" :class="trends.conversions >= 0 ? 'up' : 'down'">
            {{ trends.conversions >= 0 ? '↑' : '↓' }} {{ Math.abs(trends.conversions) }}%
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-item">
          <div class="stat-label">转化率</div>
          <div class="stat-value">{{ ((stats.conversion_rate || 0) * 100).toFixed(2) }}%</div>
          <div class="stat-trend" :class="trends.conversion_rate >= 0 ? 'up' : 'down'">
            {{ trends.conversion_rate >= 0 ? '↑' : '↓' }} {{ Math.abs(trends.conversion_rate) }}%
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-item">
          <div class="stat-label">总收入</div>
          <div class="stat-value">${{ (stats.revenue || 0).toFixed(2) }}</div>
          <div class="stat-trend" :class="trends.revenue >= 0 ? 'up' : 'down'">
            {{ trends.revenue >= 0 ? '↑' : '↓' }} {{ Math.abs(trends.revenue) }}%
          </div>
        </div>
      </el-col>
    </el-row>

    <div ref="chartContainer" class="chart-container" v-if="chartData.length > 0"></div>
    <el-empty v-else description="暂无统计数据" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick, watch, onBeforeUnmount } from 'vue';
import * as echarts from 'echarts';
import { getOfferStats } from '@/api/offer';
import { logger } from '@/utils/logger';

const props = defineProps({
  offerId: { type: Number, required: true }
});

const loading = ref(false);
const timeRange = ref('week');
const chartContainer = ref(null);
let chartInstance = null;

const stats = reactive({ clicks: 0, conversions: 0, conversion_rate: 0, revenue: 0 });
const trends = reactive({ clicks: 0, conversions: 0, conversion_rate: 0, revenue: 0 });
const chartData = ref([]);

const loadStats = async () => {
  if (!props.offerId) return;
  loading.value = true;
  try {
    const data = await getOfferStats(props.offerId, timeRange.value);
    Object.assign(stats, {
      clicks: data.clicks || 0,
      conversions: data.conversions || 0,
      conversion_rate: data.conversion_rate || 0,
      revenue: data.revenue || 0
    });
    Object.assign(trends, {
      clicks: data.trends?.clicks || 0,
      conversions: data.trends?.conversions || 0,
      conversion_rate: data.trends?.conversion_rate || 0,
      revenue: data.trends?.revenue || 0
    });
    chartData.value = data.chart_data || [];
    await nextTick();
    initChart();
  } catch (error) {
    logger.error('加载 Offer 统计失败:', error);
  } finally {
    loading.value = false;
  }
};

const initChart = () => {
  if (!chartContainer.value || chartData.value.length === 0) return;
  if (chartInstance) chartInstance.dispose();
  chartInstance = echarts.init(chartContainer.value);
  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['点击', '转化', '收入'] },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: chartData.value.map((item) => item.date)
    },
    yAxis: [
      { type: 'value', name: '数量' },
      { type: 'value', name: '收入', axisLabel: { formatter: '${value}' } }
    ],
    series: [
      { name: '点击', type: 'line', data: chartData.value.map((item) => item.clicks) },
      { name: '转化', type: 'line', data: chartData.value.map((item) => item.conversions) },
      { name: '收入', type: 'line', yAxisIndex: 1, data: chartData.value.map((item) => item.revenue) }
    ]
  });
};

const handleTimeRangeChange = () => loadStats();

watch(() => props.offerId, () => {
  if (props.offerId) loadStats();
});

const handleResize = () => chartInstance?.resize();

onMounted(() => {
  if (props.offerId) loadStats();
  window.addEventListener('resize', handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize);
  chartInstance?.dispose();
});
</script>

<style scoped>
.offer-stats-panel { padding: 4px 0; }
.panel-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar-title { font-size: 15px; font-weight: 600; }
.stats-row { margin-bottom: 20px; }
.stat-item {
  text-align: center;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 4px;
}
.stat-label { font-size: 14px; color: #909399; margin-bottom: 8px; }
.stat-value { font-size: 24px; font-weight: bold; color: #303133; margin-bottom: 8px; }
.stat-trend { font-size: 12px; }
.stat-trend.up { color: #67c23a; }
.stat-trend.down { color: #f56c6c; }
.chart-container { height: 300px; width: 100%; }
</style>
