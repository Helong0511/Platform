<!--
  GAM 产品白名单编辑器

  支持：标签展示、从平台产品选择、批量粘贴添加（每行一个产品名称）
-->
<template>
  <div class="gam-whitelist-editor">
    <div class="editor-section">
      <div class="section-title">
        已选产品名称
        <el-tag size="small" type="info">{{ modelValue.length }} 个</el-tag>
      </div>
      <div v-if="modelValue.length" class="tag-list">
        <el-tag
          v-for="name in modelValue"
          :key="name"
          closable
          class="product-tag"
          @close="removeName(name)"
        >
          {{ name }}
        </el-tag>
      </div>
      <el-empty
        v-else
        :image-size="56"
        description="暂未选择产品，留空表示全量拉取"
      />
    </div>

    <div class="editor-section">
      <div class="section-title">从平台选择</div>
      <div class="picker-row">
        <el-select
          v-model="pickerSelection"
          multiple
          filterable
          clearable
          collapse-tags
          collapse-tags-tooltip
          :loading="productsLoading"
          placeholder="搜索并选择平台产品名称"
          class="picker-select"
        >
          <el-option
            v-for="name in availablePlatformNames"
            :key="name"
            :label="name"
            :value="name"
          />
        </el-select>
        <el-button type="primary" plain :disabled="!pickerSelection.length" @click="addFromPicker">
          添加选中
        </el-button>
      </div>
    </div>

    <div class="editor-section">
      <div class="section-title">批量添加</div>
      <el-input
        v-model="bulkText"
        type="textarea"
        :rows="4"
        placeholder="每行一个产品名称，也支持逗号分隔&#10;例如：&#10;puzzlegames.shop&#10;iogames.quest&#10;casualgames.quest"
      />
      <div class="bulk-actions">
        <el-button type="primary" plain :disabled="!bulkText.trim()" @click="addFromBulkText">
          添加以上名称
        </el-button>
        <span class="bulk-hint">输入后点击「添加以上名称」，不会自动保存，需点弹窗底部「保存」</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { request } from '../../utils/api';
import {
  extractPlatformProductNames,
  mergeGamProductNames,
  normalizeGamProductName,
  parseGamProductNamesFromText,
} from '../../utils/gamProductWhitelist';

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(['update:modelValue']);

const productsLoading = ref(false);
const platformProductNames = ref([]);
const pickerSelection = ref([]);
const bulkText = ref('');

const availablePlatformNames = computed(() => {
  const selected = new Set((props.modelValue || []).map(normalizeGamProductName));
  return platformProductNames.value.filter((name) => !selected.has(name));
});

function emitNames(names) {
  emit('update:modelValue', mergeGamProductNames([], names));
}

function removeName(name) {
  const target = normalizeGamProductName(name);
  emitNames((props.modelValue || []).filter((item) => normalizeGamProductName(item) !== target));
}

function addFromPicker() {
  if (!pickerSelection.value.length) return;
  emitNames(mergeGamProductNames(props.modelValue, pickerSelection.value));
  pickerSelection.value = [];
}

function addFromBulkText() {
  const parsed = parseGamProductNamesFromText(bulkText.value);
  if (!parsed.length) return;
  emitNames(mergeGamProductNames(props.modelValue, parsed));
  bulkText.value = '';
}

async function loadPlatformProducts() {
  productsLoading.value = true;
  try {
    const allProducts = [];
    let page = 1;
    const pageSize = 100;
    let hasMore = true;

    while (hasMore) {
      const response = await request(
        {
          url: '/api/v1/products/',
          method: 'get',
          params: { page, page_size: pageSize },
        },
        { paginated: true },
      );
      const batch = response.data || [];
      allProducts.push(...batch);

      const total = response.total || 0;
      if (!batch.length || allProducts.length >= total || batch.length < pageSize) {
        hasMore = false;
      } else {
        page += 1;
      }
    }

    platformProductNames.value = extractPlatformProductNames(allProducts);
  } catch {
    platformProductNames.value = [];
  } finally {
    productsLoading.value = false;
  }
}

watch(
  () => props.modelValue,
  (names) => {
    pickerSelection.value = pickerSelection.value.filter((item) =>
      !(names || []).map(normalizeGamProductName).includes(normalizeGamProductName(item)),
    );
  },
  { deep: true },
);

onMounted(() => {
  loadPlatformProducts();
});
</script>

<style scoped>
.gam-whitelist-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.editor-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px;
  border: 1px dashed var(--border-lighter);
  border-radius: var(--radius-md);
  min-height: 44px;
}

.product-tag {
  max-width: 100%;
}

.picker-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.picker-select {
  flex: 1;
  min-width: 0;
}

.bulk-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.bulk-hint {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

@media (max-width: 767px) {
  .picker-row {
    flex-direction: column;
  }

  .picker-row .el-button {
    width: 100%;
  }
}
</style>
