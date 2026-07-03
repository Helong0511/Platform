<!--
  GAM 报表类型多选（单账号）
-->
<template>
  <div class="gam-report-types-editor">
    <div class="editor-header">
      <div class="header-left">
        <span class="section-title">报表类型</span>
        <el-tag v-if="networkLabel" type="success" size="small">{{ networkLabel }}</el-tag>
      </div>
      <el-button
        size="small"
        :loading="refreshing"
        :disabled="!canRefresh"
        @click="$emit('refresh')"
      >
        刷新本账号
      </el-button>
    </div>

    <div v-if="!options.length" class="report-type-empty">
      请先填写密钥并点击「刷新本账号」，从 Google API 拉取该账号可用报表类型。
    </div>

    <el-checkbox-group
      v-else
      :model-value="modelValue"
      class="report-types-group"
      @change="onChange"
    >
      <el-checkbox
        v-for="item in options"
        :key="item.key"
        :label="item.key"
        class="report-type-item"
      >
        <span class="report-type-label">{{ item.label }}</span>
        <span class="report-type-dims">（{{ formatDimensions(item.dimensions) }}）</span>
        <el-tag
          v-if="!item.includes_product_name"
          type="info"
          size="small"
          class="report-type-tag"
        >
          无产品维度
        </el-tag>
      </el-checkbox>
    </el-checkbox-group>

    <div v-if="modelValue?.includes('daily')" class="report-type-hint">
      「按日汇总」不含产品维度；若该账号配置了产品白名单，定时任务会自动跳过该报表。
    </div>
  </div>
</template>

<script setup>
defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  options: {
    type: Array,
    default: () => [],
  },
  refreshing: {
    type: Boolean,
    default: false,
  },
  canRefresh: {
    type: Boolean,
    default: true,
  },
  networkLabel: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['update:modelValue', 'refresh']);

const DIMENSION_LABELS = {
  DATE: '日期',
  AD_UNIT_NAME: '广告单元',
  COUNTRY_CODE: '国家',
  SITE_NAME: '站点',
};

const formatDimensions = (dimensions = []) =>
  dimensions.map((item) => DIMENSION_LABELS[item] || item).join(' + ') || '-';

const onChange = (value) => {
  emit('update:modelValue', value);
};
</script>

<style scoped>
.gam-report-types-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.report-type-empty {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.report-types-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.report-type-item {
  height: auto;
  margin-right: 0;
  align-items: flex-start;
}

.report-type-label {
  font-weight: 500;
}

.report-type-dims {
  margin-left: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.report-type-tag {
  margin-left: 8px;
}

.report-type-hint {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}
</style>
