<!--
Offer 统计组件
从 OfferManagement.vue 拆分
负责 Offer 数据统计展示
-->
<template>
  <el-card class="offer-stats-card" v-loading="loading">
    <template #header>
      <div class="card-header">
        <span class="title">Offer 统计</span>
        <el-select
          v-model="timeRange"
          size="default"
          @change="handleTimeRangeChange"
        >
          <el-option label="今日" value="day" />
          <el-option label="本周" value="week" />
          <el-option label="本月" value="month" />
        </el-select>
      </div>
    </template>

    <!-- 统计卡片 -->
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

    <!-- 趋势图表 -->
    <div ref="chartContainer" class="chart-container" v-if="chartData.length > 0"></div>
    <el-empty v-else description="暂无数据" />
  </el-card>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick, watch } from 'vue';
import * as echarts from 'echarts';
import { getOfferStats } from '@/api/offer';

// Props
const props = defineProps({
  offerId: {
    type: Number,
    required: true
  }
});

// 状态
const loading = ref(false);
const timeRange = ref('week');
const chartContainer = ref(null);
let chartInstance = null;

// 统计数据
const stats = reactive({
  clicks: 0,
  conversions: 0,
  conversion_rate: 0,
  revenue: 0
});

// 趋势
const trends = reactive({
  clicks: 0,
  conversions: 0,
  conversion_rate: 0,
  revenue: 0
});

// 图表数据
const chartData = ref([]);

// 加载统计数据
const loadStats = async () => {
  if (!props.offerId) return;
  
  loading.value = true;
  try {
    const response = await getOfferStats(props.offerId, timeRange.value);
    const data = response.data.data;
    
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
    console.error('加载统计数据失败:', error);
  } finally {
    loading.value = false;
  }
};

// 初始化图表
const initChart = () => {
  if (!chartContainer.value || chartData.value.length === 0) return;
  
  if (chartInstance) {
    chartInstance.dispose();
  }
  
  chartInstance = echarts.init(chartContainer.value);
  
  const option = {
    tooltip: {
      trigger: 'axis'
    },
    legend: {
      data: ['点击', '转化', '收入']
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: chartData.value.map(item => item.date)
    },
    yAxis: [
      {
        type: 'value',
        name: '数量'
      },
      {
        type: 'value',
        name: '收入',
        axisLabel: {
          formatter: '${value}'
        }
      }
    ],
    series: [
      {
        name: '点击',
        type: 'line',
        data: chartData.value.map(item => item.clicks)
      },
      {
        name: '转化',
        type: 'line',
        data: chartData.value.map(item => item.conversions)
      },
      {
        name: '收入',
        type: 'line',
        yAxisIndex: 1,
        data: chartData.value.map(item => item.revenue)
      }
    ]
  };
  
  chartInstance.setOption(option);
};

// 时间范围变化
const handleTimeRangeChange = () => {
  loadStats();
};

// 监听 offerId 变化
watch(() => props.offerId, () => {
  if (props.offerId) {
    loadStats();
  }
});

// 窗口大小变化时重新渲染图表
const handleResize = () => {
  if (chartInstance) {
    chartInstance.resize();
  }
};

// 生命周期
onMounted(() => {
  if (props.offerId) {
    loadStats();
  }
  window.addEventListener('resize', handleResize);
});

// 清理
import { onBeforeUnmount } from 'vue';
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize);
  if (chartInstance) {
    chartInstance.dispose();
  }
});
</script>

<style scoped>
.offer-stats-card {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-size: 16px;
  font-weight: bold;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-item {
  text-align: center;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 4px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
  margin-bottom: 8px;
}

.stat-trend {
  font-size: 12px;
}

.stat-trend.up {
  color: #67c23a;
}

.stat-trend.down {
  color: #f56c6c;
}

.chart-container {
  height: 300px;
  width: 100%;
}
</style>
