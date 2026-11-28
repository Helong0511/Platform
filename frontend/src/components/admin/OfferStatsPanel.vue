<!--
  Offer 统计面板（OfferStatsPanel.vue）

  嵌入 Offer 管理详情 Tab，展示：
  1. 点击/转化趋势图表
  2. 关键指标卡片：CTR、CVR、收益等
  3. 时间范围切换与数据刷新

  通过 props 接收 offerId，自行请求统计数据。
-->
<template>
  <!-- 页面主模板 -->
  <!-- 页面主模板 -->
<div class="offer-stats-panel" v-loading="loading">
    <!-- 工具栏 -->
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
          <div class="stat-value">
            {{ stats.revenue === null ? (revenueByCurrency.length ? '分币种查看' : '—') : formatCurrency(stats.revenue, stats.revenue_currency) }}
          </div>
          <div v-if="trends.revenue !== null" class="stat-trend" :class="trends.revenue >= 0 ? 'up' : 'down'">
            {{ trends.revenue >= 0 ? '↑' : '↓' }} {{ Math.abs(trends.revenue) }}%
          </div>
          <div v-else class="stat-trend">多币种或无可比同期</div>
        </div>
      </el-col>
    </el-row>

    <el-table v-if="revenueByCurrency.length" :data="revenueByCurrency" size="small" class="currency-revenue-table">
      <el-table-column prop="currency" label="币种" width="110" />
      <el-table-column prop="currency_source" label="币种来源" min-width="180" />
      <el-table-column label="收入" min-width="160">
        <template #default="{ row }">{{ formatCurrency(row.amount, row.currency) }}</template>
      </el-table-column>
    </el-table>
    <el-table v-if="dailyRevenueRows.length" :data="dailyRevenueRows" size="small" class="currency-revenue-table">
      <el-table-column prop="date" label="日期" width="130" />
      <el-table-column prop="currency" label="币种" width="110" />
      <el-table-column prop="currency_source" label="币种来源" min-width="180" />
      <el-table-column label="当日收入" min-width="160">
        <template #default="{ row }">{{ formatCurrency(row.amount, row.currency) }}</template>
      </el-table-column>
    </el-table>
    <div ref="chartContainer" class="chart-container" v-if="chartData.length > 0"></div>
    <el-empty v-if="chartData.length === 0" description="暂无统计数据" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick, watch, onBeforeUnmount } from 'vue';
import * as echarts from 'echarts';
import { getOfferStats } from '@/api/offer';
import { logger } from '@/utils/logger';

const props = defineProps({
  offerId: { type: Number, required: true },
  currency: { type: String, default: 'USD' }
});

const loading = ref(false);
const timeRange = ref('week');
const chartContainer = ref(null);
let chartInstance = null;

const stats = reactive({ clicks: 0, conversions: 0, conversion_rate: 0, revenue: null, revenue_currency: null });
const trends = reactive({ clicks: 0, conversions: 0, conversion_rate: 0, revenue: null });
const chartData = ref([]);
const revenueByCurrency = ref([]);
const dailyRevenueRows = ref([]);
// 金额按后端 Decimal 字符串展示，不在 UI 层转成 Number，避免精度及币种小数位丢失。
const formatCurrency = (value, currency) => {
  const code = String(currency || 'LEGACY_UNKNOWN').trim().toUpperCase();
  return code === 'LEGACY_UNKNOWN' ? `${value}（币种待核实）` : `${value} ${code}`;
};

const loadStats = async () => {
  if (!props.offerId) return;
  loading.value = true;
  try {
    const data = await getOfferStats(props.offerId, timeRange.value);
    Object.assign(stats, {
      clicks: data.clicks || 0,
      conversions: data.conversions || 0,
      conversion_rate: data.conversion_rate || 0,
      revenue: data.revenue ?? null,
      revenue_currency: data.revenue_currency || null
    });
    revenueByCurrency.value = data.revenue_by_currency || [];
    dailyRevenueRows.value = (data.chart_data || []).flatMap((day) =>
      (day.revenue_by_currency || []).map((item) => ({ date: day.date, ...item }))
    );
    Object.assign(trends, {
      clicks: data.trends?.clicks || 0,
      conversions: data.trends?.conversions || 0,
      conversion_rate: data.trends?.conversion_rate || 0,
      revenue: data.trends?.revenue ?? null
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
  // 只有唯一且可信的币种来源才绘制收入曲线，禁止跨币种共用数值轴。
  const revenueGroup = revenueByCurrency.value.length === 1 &&
    revenueByCurrency.value[0].currency !== 'LEGACY_UNKNOWN'
    ? revenueByCurrency.value[0]
    : null;
  const revenueSeries = revenueGroup ? [{
    name: `${revenueGroup.currency} · ${revenueGroup.currency_source}`,
    type: 'line',
    yAxisIndex: 1,
    data: chartData.value.map((day) => {
      const match = (day.revenue_by_currency || []).find((item) =>
        item.currency === revenueGroup.currency && item.currency_source === revenueGroup.currency_source
      );
      return match ? Number(match.amount) : null;
    })
  }] : [];
  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['点击', '转化', ...revenueSeries.map((item) => item.name)] },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: chartData.value.map((item) => item.date)
    },
    yAxis: [
      { type: 'value', name: '数量' },
      { type: 'value', name: revenueGroup ? `收入（${revenueGroup.currency}）` : '收入（多币种明细见表格）' }
    ],
    series: [
      { name: '点击', type: 'line', data: chartData.value.map((item) => item.clicks) },
      { name: '转化', type: 'line', data: chartData.value.map((item) => item.conversions) },
      ...revenueSeries
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
