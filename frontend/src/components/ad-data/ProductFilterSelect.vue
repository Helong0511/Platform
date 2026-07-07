<!--
  产品筛选下拉（含当前/历史归属标签）
  @file components/ad-data/ProductFilterSelect.vue
-->
<template>
  <el-select
    :model-value="modelValue"
    :placeholder="placeholder"
    style="width: 100%;"
    :multiple="multiple"
    :collapse-tags="multiple"
    :collapse-tags-tooltip="multiple"
    clearable
    filterable
    @update:model-value="emit('update:modelValue', $event)"
    @change="emit('change')"
  >
    <el-option
      v-for="product in options"
      :key="product.value"
      :label="product.label"
      :value="product.value"
    >
      <div class="product-filter-option">
        <span class="product-filter-option__name">{{ product.name || product.label }}</span>
        <el-tag
          v-if="getProductOwnershipTag(product.ownershipType)"
          size="small"
          :type="getProductOwnershipTag(product.ownershipType).type"
          class="product-filter-option__tag"
        >
          {{ getProductOwnershipTag(product.ownershipType).text }}
        </el-tag>
      </div>
    </el-option>
  </el-select>
</template>

<script setup>
import { getProductOwnershipTag } from '../../utils/productFilterOptions';

defineProps({
  modelValue: { type: [String, Number, Array], default: '' },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '全部产品' },
  multiple: { type: Boolean, default: false },
});

const emit = defineEmits(['update:modelValue', 'change']);
</script>

<style scoped>
.product-filter-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
}

.product-filter-option__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-filter-option__tag {
  flex-shrink: 0;
}
</style>
