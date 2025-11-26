<template>
  <div class="dashboard-container">

    <!-- 趋势图表 -->
    <el-card class="chart-card">
      <h2>广告效果趋势</h2>
      <el-select v-model="timeRange" @change="handleTimeRangeChange" class="time-select" placeholder="选择时间范围">
        <el-option label="今日" value="day"></el-option>
        <el-option label="本周" value="week"></el-option>
        <el-option label="本月" value="month"></el-option>
        <el-option label="上月" value="last_month"></el-option>
      </el-select>
      <div ref="chartContainer" v-if="trendData && trendData.dates && trendData.dates.length > 0" style="width: 100%; height: 300px;"></div>
      <div v-else class="chart-placeholder">
        <p>暂无数据</p>
        <p v-if="loading" class="loading-text">数据加载中...</p>
      </div>
    </el-card>
    <br>
    <div class="stats-grid">
      <!-- 统计卡片 -->
      <template v-for="stat in stats" :key="stat.id">
        <el-card v-if="stat && stat.id && stat.icon" class="stat-card">
          <el-statistic
            :title="stat.label"
            :value="stat.value"
            :precision="stat.precision || 0"
            :value-style="{ fontSize: '24px' }"
          >
            <template #prefix>
              <el-icon :size="24">
                <component :is="stat.icon" />
              </el-icon>
            </template>
            <template #suffix>
              <span :class="stat.trend > 0 ? 'trend-up' : 'trend-down'">
                {{ stat.trend > 0 ? '+' : '' }}{{ stat.trend }}%
              </span>
            </template>
          </el-statistic>
        </el-card>
      </template>
    </div>

    
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch, onBeforeUnmount, nextTick, markRaw } from 'vue';
import { useRoute } from 'vue-router';
import { useAuthStore } from '../store';
import { ElCard, ElStatistic, ElIcon, ElSelect, ElOption, ElMessage } from 'element-plus';
import * as echarts from 'echarts';

import { View, Money, User, PieChart } from '@element-plus/icons-vue';
import {
  getDashboardStats, getTrendData
} from '../api/dashboard';
import { extractErrorMessage, isErrorHandled } from '../utils/api';

// 防抖函数
const debounce = (fn, delay) => {
  let timeoutId;
  return (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn.apply(this, args), delay);
  };
};

// 初始化Pinia Store
const authStore = useAuthStore();

// 用户角色判断
const isAdmin = computed(() => authStore.isAdmin);

// 状态管理
const stats = ref([]);
const trendData = ref({ dates: [], series: [] });
const timeRange = ref('week');
const loading = ref(true);

const handleTimeRangeChange = debounce(async (newValue) => {
  loading.value = true;
  try {
    await Promise.all([
      fetchStats(newValue),
      fetchTrendData(newValue)
    ]);
    // 确保图表已初始化并更新
    await nextTick();
    if (chartContainer.value && !chartInstance) {
      initChart();
    }
    updateChart();
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
  } finally {
    loading.value = false;
  }
}, 300);

// 图标映射（使用 markRaw 防止组件被变成响应式对象）
const iconMap = {
  requests: markRaw(View),
  matches: markRaw(View),
  coverage: markRaw(PieChart),
  impressions: markRaw(PieChart),
  display_rate: markRaw(PieChart),
  clicks: markRaw(View),
  ctr: markRaw(View),
  ecpm_deducted: markRaw(Money),
  revenue_deducted: markRaw(Money),
  ecpm_undeducted: markRaw(Money),
  revenue_undeducted: markRaw(Money),
  conversions: markRaw(Money),
  cpc: markRaw(PieChart),
  cpa: markRaw(User)
};

// 获取统计数据
const fetchStats = async (selectedTimeRange) => {
  try {
    loading.value = true;
    const data = await getDashboardStats(selectedTimeRange);
    
    // 安全处理数据，防止空值错误
    if (!data || !data.stats) {
      stats.value = [];
      return;
    }
    
    // 根据用户角色筛选指标
    const statsArray = Array.isArray(data.stats) ? data.stats : [];
    const filteredStats = isAdmin.value 
      ? statsArray 
      : statsArray.filter(stat => 
          ['requests', 'matches', 'coverage', 'impressions', 'display_rate', 'clicks', 'ctr', 'ecpm_deducted', 'revenue_deducted'].includes(stat.id)
        );
    
    stats.value = filteredStats
      .filter(stat => stat && stat.id) // 过滤无效的 stat
      .map(stat => {
        // 确保 icon 是有效的组件函数
        let icon = iconMap[stat.id];
        if (!icon || typeof icon !== 'function') {
          icon = View;
        }
        return {
          ...stat,
          icon: icon
        };
      });
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
    stats.value = [];
  } finally {
    loading.value = false;
  }
};

// 图表容器引用
const chartContainer = ref(null);
let chartInstance = null;

// 窗口大小调整处理函数
const handleResize = () => {
  if (chartInstance) {
    chartInstance.resize();
  }
};

// 初始化图表
const initChart = () => {
  if (!chartContainer.value) return;
  
  // 如果图表实例已存在，先销毁
  if (chartInstance) {
    chartInstance.dispose();
    window.removeEventListener('resize', handleResize);
  }
  
  // 创建新的图表实例
  chartInstance = echarts.init(chartContainer.value);
  
  // 监听窗口大小变化，自动调整图表大小
  window.addEventListener('resize', handleResize);
};

// 更新图表数据
const updateChart = () => {
  if (!chartInstance || !trendData.value || !trendData.value.dates || trendData.value.dates.length === 0) {
    return;
  }
  
  const { dates, series } = trendData.value;
  
  // 构建 ECharts 系列数据
  const echartsSeries = series.map(item => ({
    name: item.name,
    type: 'line',
    data: item.data,
    smooth: true,
    symbol: 'circle',
    symbolSize: 6
  }));
  
  // 配置图表选项
  const option = {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        let result = `${params[0].axisValue}<br/>`;
        params.forEach(param => {
          result += `${param.seriesName}: ${param.value}<br/>`;
        });
        return result;
      }
    },
    legend: {
      data: series.map(s => s.name),
      bottom: 0
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dates
    },
    yAxis: {
      type: 'value'
    },
    series: echartsSeries
  };
  
  chartInstance.setOption(option);
};

// 获取趋势数据
const fetchTrendData = async (selectedTimeRange) => {
  try {
    loading.value = true;
    const data = await getTrendData(selectedTimeRange);
    
    // 安全处理数据，防止空值错误
    if (!data || !data.dates || !data.series) {
      trendData.value = { dates: [], series: [] };
      return;
    }
    
    // 直接使用后端返回的数据格式（dates 和 series）
    trendData.value = data;
    
    // 等待 DOM 更新后更新图表
    await nextTick();
    if (chartContainer.value && !chartInstance) {
      initChart();
    }
    updateChart();
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
    trendData.value = { dates: [], series: [] };
  } finally {
    loading.value = false;
  }
};

// 路由实例
const route = useRoute();

// 加载数据的函数
const loadDashboardData = async () => {
  try {
    loading.value = true;
    await Promise.all([fetchStats(timeRange.value), fetchTrendData(timeRange.value)]);
  } catch (error) {
    // 初始化失败时的错误处理
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(`页面初始化失败: ${errorMsg}`);
    }
  } finally {
    loading.value = false;
  }
};

// 标记是否已经初始化
let isInitialized = false;

// 全局错误处理器，捕获并忽略 ElOnlyChild 错误
const handleGlobalError = (event) => {
  // 忽略 Element Plus 的 ElOnlyChild 错误
  const errorMessage = event?.message || event?.error?.message || '';
  if (typeof errorMessage === 'string' && errorMessage.includes('ElOnlyChild')) {
    event.preventDefault();
    event.stopPropagation();
    return true;
  }
  return false;
};

const handleUnhandledRejection = (event) => {
  // 处理未捕获的 Promise 拒绝
  const errorMessage = event?.reason?.message || event?.reason?.error?.message || '';
  if (typeof errorMessage === 'string' && errorMessage.includes('ElOnlyChild')) {
    event.preventDefault();
    return true;
  }
  return false;
};

// 组件挂载时加载数据
onMounted(async () => {
  // 添加全局错误处理器
  window.addEventListener('error', handleGlobalError, true);
  window.addEventListener('unhandledrejection', handleUnhandledRejection, true);
  
  // 延迟加载数据，让页面先渲染出来
  setTimeout(async () => {
    await loadDashboardData();
    // 数据加载后初始化图表
    await nextTick();
    if (chartContainer.value && !chartInstance) {
      initChart();
      updateChart();
    }
    isInitialized = true;
  }, 0);
});

// 组件卸载前清理
onBeforeUnmount(() => {
  // 移除事件监听器
  window.removeEventListener('error', handleGlobalError, true);
  window.removeEventListener('unhandledrejection', handleUnhandledRejection, true);
  // 销毁图表实例
  if (chartInstance) {
    window.removeEventListener('resize', handleResize);
    chartInstance.dispose();
    chartInstance = null;
  }
});

// 监听路由变化，当从其他页面导航到 Dashboard 时自动刷新数据
watch(
  () => route.path,
  (newPath, oldPath) => {
    // 当路由路径是 /app/dashboard 且不是首次加载时，刷新数据
    // 确保是从其他页面导航过来的，而不是首次加载
    if (newPath === '/app/dashboard' && isInitialized && oldPath && oldPath !== '/app/dashboard') {
      loadDashboardData();
    }
  },
  { immediate: false }
);

// 监听时间范围变化，更新统计数据

</script>

<style scoped>
.dashboard-container {
  padding: 0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-xxl);
  margin-bottom: var(--spacing-xxxl);
  width: 100%;
}

/* 桌面端：3-4列 */
@media (min-width: 1025px) {
  .stats-grid {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: var(--spacing-xxl);
  }
}

/* 平板端：2列 */
@media (min-width: 768px) and (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: var(--spacing-xl);
  }
  
  .stat-card {
    min-width: 0; /* 允许收缩 */
  }
}

/* 移动端：1列 */
@media (max-width: 767px) {
  .stats-grid {
    grid-template-columns: 1fr;
    gap: var(--spacing-lg);
  }
}

.stat-card {
  transition: var(--transition-base);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-medium);
}

.chart-card {
  margin-top: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.chart-card :deep(.el-card__header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-card :deep(.el-card__header h2) {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.time-select {
  margin-bottom: var(--spacing-xl);
  width: 200px;
}

.chart-placeholder {
  height: 300px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  font-size: var(--font-size-base);
  background-color: var(--bg-secondary);
  border-radius: var(--radius-lg);
  gap: var(--spacing-sm);
}

.chart-placeholder .loading-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* 平板端和移动端优化 */
@media (max-width: 1024px) {
  .time-select {
    width: 100%;
    margin-bottom: var(--spacing-lg);
  }
  
  .chart-card :deep(.el-card__header) {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-md);
  }
}

/* 移动端图表高度优化 */
@media (max-width: 767px) {
  .dashboard-container {
    padding: var(--spacing-md);
  }
  
  .stats-grid {
    gap: var(--spacing-md);
    margin-bottom: var(--spacing-xl);
  }
  
  .stat-card {
    padding: var(--spacing-md) !important;
  }
  
  .stat-card :deep(.el-card__body) {
    padding: var(--spacing-md);
  }
  
  .chart-card {
    margin-top: var(--spacing-md);
  }
  
  .chart-card :deep(.el-card__header) {
    padding: var(--spacing-md);
  }
  
  .chart-card :deep(.el-card__body) {
    padding: var(--spacing-md);
  }
  
  .chart-card :deep(.el-chart) {
    height: 250px !important;
  }
  
  .chart-placeholder {
    height: 250px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
    font-size: var(--font-size-base);
  }
  
  .time-select {
    width: 100%;
    margin-bottom: var(--spacing-md);
  }
}

.trend-up {
  color: var(--success-color);
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-sm);
}

.trend-down {
  color: var(--danger-color);
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-sm);
}
</style>