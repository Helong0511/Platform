<template>
  <el-dialog
    :model-value="visible"
    :title="title"
    :width="isMobile ? '95%' : '600px'"
    :append-to-body="true"
    @update:model-value="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-width="120px"
    >
      <el-form-item label="原始URL" prop="original_url">
        <el-input
          v-model="formData.original_url"
          type="textarea"
          :rows="5"
          placeholder="https://example.com/very/long/url"
          clearable
        />
        <div class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>必须包含协议（http://或https://）</span>
        </div>
      </el-form-item>

      <el-form-item label="自定义代码" prop="short_code">
        <div style="display: flex; gap: 8px;">
          <el-input
            v-model="formData.short_code"
            placeholder="留空则自动生成（3-20个字符，字母、数字、连字符、下划线）"
            clearable
            :disabled="isEdit"
            style="flex: 1;"
          />
          <el-button
            v-if="!isEdit"
            @click="handleGenerateCode"
            :loading="generatingCode"
            :icon="Refresh"
          >
            自动生成
          </el-button>
        </div>
        <div class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span v-if="isEdit">编辑时不可修改代码</span>
          <span v-else>点击"自动生成"按钮生成唯一代码，或手动输入自定义代码</span>
        </div>
      </el-form-item>

      <el-form-item label="标题" prop="title">
        <el-input
          v-model="formData.title"
          placeholder="短链接标题（可选）"
          clearable
          maxlength="200"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="描述" prop="description">
        <el-input
          v-model="formData.description"
          type="textarea"
          :rows="3"
          placeholder="短链接描述（可选）"
          maxlength="500"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="关联Offer" prop="offer_id">
        <el-select
          v-model="formData.offer_id"
          placeholder="选择关联的Offer（可选）"
          filterable
          clearable
          popper-class="select-dropdown"
          :teleported="true"
          style="width: 100%;"
        >
          <el-option
            v-for="offer in offerList"
            :key="offer.id"
            :label="`${offer.offer_name} (ID: ${offer.id})`"
            :value="offer.id"
          />
        </el-select>
        <div class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>选择关联的Offer，用于标识短链接所属的Offer</span>
        </div>
      </el-form-item>

      <el-form-item label="关联渠道" prop="channel_id">
        <el-select
          v-model="formData.channel_id"
          placeholder="选择关联的渠道（可选）"
          filterable
          clearable
          popper-class="select-dropdown"
          :teleported="true"
          style="width: 100%;"
        >
          <el-option
            v-for="channel in channelList"
            :key="channel.id"
            :label="`${channel.publisher_name} (ID: ${channel.id})`"
            :value="channel.id"
          />
        </el-select>
        <div class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>选择关联的渠道，用于标识短链接所属的渠道</span>
        </div>
      </el-form-item>

      <el-form-item label="过期时间" prop="expires_at">
        <el-date-picker
          v-model="formData.expires_at"
          type="datetime"
          placeholder="选择过期时间（可选）"
          format="YYYY-MM-DD HH:mm:ss"
          value-format="YYYY-MM-DD HH:mm:ss"
          style="width: 100%;"
        />
      </el-form-item>

      <el-form-item label="状态" prop="is_active">
        <el-switch v-model="formData.is_active" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue';
import { InfoFilled, Refresh } from '@element-plus/icons-vue';
import { useDevice } from '@/composables/useDevice';

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  formData: {
    type: Object,
    required: true
  },
  formRules: {
    type: Object,
    required: true
  },
  isEdit: {
    type: Boolean,
    default: false
  },
  offerList: {
    type: Array,
    default: () => []
  },
  channelList: {
    type: Array,
    default: () => []
  },
  generatingCode: {
    type: Boolean,
    default: false
  },
  saving: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(['update:modelValue', 'save', 'generate-code', 'close']);

const { isMobile } = useDevice();
const formRef = ref(null);

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
});

const title = computed(() => props.isEdit ? '编辑短链接' : '创建短链接');

const handleClose = () => {
  emit('close');
};

const handleSave = async () => {
  if (!formRef.value) return;
  await formRef.value.validate((valid) => {
    if (valid) {
      emit('save');
    }
  });
};

const handleGenerateCode = () => {
  emit('generate-code');
};
</script>

<style scoped>
.form-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
