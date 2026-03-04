<!--
虚拟滚动表格组件
用于优化大数据量列表的渲染性能
基于 Element Plus 的 el-table，添加虚拟滚动支持
-->
<template>
  <div class="virtual-table-container" ref="containerRef">
    <el-table
      v-loading="loading"
      :data="visibleData"
      :height="height"
      border
      stripe
      style="width: 100%"
      v-bind="$attrs"
      @selection-change="handleSelectionChange"
    >
      <slot></slot>
    </el-table>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';

const props = defineProps({
  // 数据列表
  data: {
    type: Array,
    default: () => []
  },
  // 表格高度（px）
  height: {
    type: [Number, String],
    default: 600
  },
  // 每项高度（px）
  itemHeight: {
    type: Number,
    default: 50
  },
  // 缓冲区大小（上下各保留的可见项数）
  bufferSize: {
    type: Number,
    default: 5
  },
  // 加载状态
  loading: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(['selection-change', 'scroll']);

const containerRef = ref(null);
const scrollTop = ref(0);
const containerHeight = ref(600);

// 计算可见区域
const visibleRange = computed(() => {
  const start = Math.max(0, Math.floor(scrollTop.value / props.itemHeight) - props.bufferSize);
  const end = Math.min(
    props.data.length,
    Math.ceil((scrollTop.value + containerHeight.value) / props.itemHeight) + props.bufferSize
  );
  return { start, end };
});

// 可见数据
const visibleData = computed(() => {
  const { start, end } = visibleRange.value;
  return props.data.slice(start, end).map((item, index) => ({
    ...item,
    _virtualIndex: start + index // 保留原始索引
  }));
});

// 处理滚动
const handleScroll = (event) => {
  const target = event.target;
  scrollTop.value = target.scrollTop;
  emit('scroll', {
    scrollTop: scrollTop.value,
    scrollLeft: target.scrollLeft
  });
};

// 处理选择变化
const handleSelectionChange = (selection) => {
  emit('selection-change', selection);
};

// 监听数据变化，重置滚动位置
watch(() => props.data.length, () => {
  scrollTop.value = 0;
});

// 监听高度变化
watch(() => props.height, (newHeight) => {
  containerHeight.value = typeof newHeight === 'string' 
    ? parseInt(newHeight) 
    : newHeight;
}, { immediate: true });

onMounted(() => {
  // 设置容器高度
  if (containerRef.value) {
    const height = typeof props.height === 'string' 
      ? parseInt(props.height) 
      : props.height;
    containerHeight.value = height;
    
    // 监听滚动事件
    const tableBody = containerRef.value.querySelector('.el-table__body-wrapper');
    if (tableBody) {
      tableBody.addEventListener('scroll', handleScroll);
    }
  }
});

onUnmounted(() => {
  if (containerRef.value) {
    const tableBody = containerRef.value.querySelector('.el-table__body-wrapper');
    if (tableBody) {
      tableBody.removeEventListener('scroll', handleScroll);
    }
  }
});
</script>

<style scoped>
.virtual-table-container {
  position: relative;
  width: 100%;
}

/* 优化滚动性能 */
.virtual-table-container :deep(.el-table__body-wrapper) {
  overflow-y: auto;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .virtual-table-container {
    font-size: var(--font-size-base);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .virtual-table-container :deep(.el-table) {
    min-width: 600px; /* 确保表格有最小宽度，可以横向滚动 */
    font-size: var(--font-size-sm);
  }
  
  .virtual-table-container :deep(.el-table__header-wrapper),
  .virtual-table-container :deep(.el-table__body-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .virtual-table-container :deep(.el-table__cell) {
    padding: var(--spacing-xs) var(--spacing-sm);
    word-break: break-word;
  }
  
  .virtual-table-container :deep(.el-table__header th),
  .virtual-table-container :deep(.el-table__body td) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
  }
}
</style>

