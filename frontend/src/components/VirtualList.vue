<!--
虚拟滚动列表组件
用于优化大数据量列表的渲染性能
适用于简单的列表场景（非表格）
-->
<template>
  <!-- 页面主模板 -->
<div 
    class="virtual-list-container" 
    ref="containerRef"
    :style="{ height: `${height}px`, overflow: 'auto' }"
    @scroll="handleScroll"
  >
    <div 
      class="virtual-list-spacer"
      :style="{ height: `${spacerTop}px` }"
    ></div>
    <div class="virtual-list-content">
      <slot :items="visibleItems" :startIndex="visibleRange.start"></slot>
    </div>
    <div 
      class="virtual-list-spacer"
      :style="{ height: `${spacerBottom}px` }"
    ></div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue';

const props = defineProps({
  // 数据列表
  items: {
    type: Array,
    default: () => []
  },
  // 容器高度（px）
  height: {
    type: Number,
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
  }
});

const emit = defineEmits(['scroll']);

const containerRef = ref(null);
const scrollTop = ref(0);

// 计算可见区域
const visibleRange = computed(() => {
  const start = Math.max(0, Math.floor(scrollTop.value / props.itemHeight) - props.bufferSize);
  const end = Math.min(
    props.items.length,
    Math.ceil((scrollTop.value + props.height) / props.itemHeight) + props.bufferSize
  );
  return { start, end };
});

// 可见数据
const visibleItems = computed(() => {
  const { start, end } = visibleRange.value;
  return props.items.slice(start, end);
});

// 上方占位高度
const spacerTop = computed(() => {
  return visibleRange.value.start * props.itemHeight;
});

// 下方占位高度
const spacerBottom = computed(() => {
  const { end } = visibleRange.value;
  return (props.items.length - end) * props.itemHeight;
});

// 处理滚动
const handleScroll = (event) => {
  scrollTop.value = event.target.scrollTop;
  emit('scroll', {
    scrollTop: scrollTop.value
  });
};

// 监听数据变化，重置滚动位置
watch(() => props.items.length, () => {
  scrollTop.value = 0;
  if (containerRef.value) {
    containerRef.value.scrollTop = 0;
  }
});
</script>

<style scoped>
.virtual-list-container {
  position: relative;
  width: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
}

.virtual-list-spacer {
  width: 100%;
}

.virtual-list-content {
  width: 100%;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .virtual-list-container {
    font-size: var(--font-size-base);
  }
}
</style>

