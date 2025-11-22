# 虚拟滚动组件使用说明

## 概述

为了优化大数据量列表的渲染性能，我们提供了两个虚拟滚动组件：

1. **VirtualTable.vue** - 基于 Element Plus el-table 的虚拟滚动表格组件
2. **VirtualList.vue** - 简单的虚拟滚动列表组件

## VirtualTable 组件

### 使用场景
- 需要显示大量数据的表格（1000+ 行）
- 需要保持 Element Plus 表格的所有功能（排序、筛选、选择等）

### 使用方法

```vue
<template>
  <VirtualTable
    :data="largeDataList"
    :height="600"
    :item-height="50"
    :loading="loading"
    @selection-change="handleSelectionChange"
  >
    <el-table-column type="selection" width="55"></el-table-column>
    <el-table-column prop="name" label="名称"></el-table-column>
    <el-table-column prop="date" label="日期"></el-table-column>
  </VirtualTable>
</template>

<script setup>
import VirtualTable from '@/components/VirtualTable.vue';
import { ref } from 'vue';

const largeDataList = ref([]);
const loading = ref(false);

const handleSelectionChange = (selection) => {
  console.log('选中的项:', selection);
};
</script>
```

### Props

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| data | Array | [] | 数据列表 |
| height | Number/String | 600 | 表格高度（px） |
| itemHeight | Number | 50 | 每项高度（px） |
| bufferSize | Number | 5 | 缓冲区大小（上下各保留的可见项数） |
| loading | Boolean | false | 加载状态 |

### Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| selection-change | selection | 选择变化时触发 |
| scroll | { scrollTop, scrollLeft } | 滚动时触发 |

## VirtualList 组件

### 使用场景
- 简单的列表展示（非表格）
- 需要自定义列表项样式

### 使用方法

```vue
<template>
  <VirtualList
    :items="largeDataList"
    :height="600"
    :item-height="60"
  >
    <template #default="{ items, startIndex }">
      <div
        v-for="(item, index) in items"
        :key="startIndex + index"
        class="list-item"
      >
        {{ item.name }}
      </div>
    </template>
  </VirtualList>
</template>

<script setup>
import VirtualList from '@/components/VirtualList.vue';
import { ref } from 'vue';

const largeDataList = ref([]);
</script>

<style scoped>
.list-item {
  height: 60px;
  padding: 10px;
  border-bottom: 1px solid #eee;
}
</style>
```

### Props

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| items | Array | [] | 数据列表 |
| height | Number | 600 | 容器高度（px） |
| itemHeight | Number | 50 | 每项高度（px） |
| bufferSize | Number | 5 | 缓冲区大小（上下各保留的可见项数） |

### Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| scroll | { scrollTop } | 滚动时触发 |

### Slot

| 插槽名 | 参数 | 说明 |
|--------|------|------|
| default | { items, startIndex } | 列表项内容 |

## 性能优化建议

1. **合理设置 itemHeight**：确保每项高度与实际高度一致，避免滚动位置计算错误
2. **调整 bufferSize**：根据实际需求调整缓冲区大小，平衡性能和用户体验
3. **使用分页**：对于超大数据量（10000+），建议结合后端分页使用
4. **避免频繁更新数据**：虚拟滚动适合数据相对稳定的场景

## 注意事项

1. VirtualTable 组件基于 Element Plus 的 el-table，保留了所有原生功能
2. 虚拟滚动只渲染可见区域的数据，大幅提升性能
3. 如果数据项高度不一致，建议使用固定高度或使用 VirtualList 组件自定义渲染
4. 移动端已优化滚动性能，使用 `-webkit-overflow-scrolling: touch`

## 示例

### 广告数据列表（大数据量场景）

```vue
<template>
  <VirtualTable
    :data="adDataList"
    :height="tableHeight"
    :item-height="50"
    :loading="loading"
    @selection-change="handleSelectionChange"
  >
    <el-table-column type="selection" width="55"></el-table-column>
    <el-table-column prop="date" label="数据日期"></el-table-column>
    <el-table-column prop="product_name" label="产品名称"></el-table-column>
    <el-table-column prop="request_count" label="请求数"></el-table-column>
    <!-- 更多列... -->
  </VirtualTable>
</template>
```

## 迁移指南

如果现有页面需要迁移到虚拟滚动：

1. 导入组件：`import VirtualTable from '@/components/VirtualTable.vue';`
2. 替换 `el-table` 为 `VirtualTable`
3. 添加必要的 props（height, itemHeight）
4. 测试滚动和交互功能

注意：虚拟滚动适合数据量较大的场景（1000+ 行），如果数据量较小，使用普通表格即可。

