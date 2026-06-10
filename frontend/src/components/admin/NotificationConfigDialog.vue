<!--
  通知配置弹窗（客户 / 产品通用）
  @file components/admin/NotificationConfigDialog.vue
-->
<template>
  <el-dialog
    v-model="visible"
    :title="`${entityName} - 通知配置`"
    :width="isMobile ? '95%' : '800px'"
    :close-on-click-modal="false"
    append-to-body
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-width="150px"
      v-loading="loading"
    >
      <el-form-item label="启用通知" prop="notification_enabled">
        <el-switch v-model="formData.notification_enabled" />
        <div class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>{{ entityConfig.enabledHint }}</span>
        </div>
      </el-form-item>

      <el-divider />

      <el-form-item label="通知转化事件" prop="notify_on_conversion">
        <el-switch
          v-model="formData.notify_on_conversion"
          :disabled="!formData.notification_enabled"
        />
        <div v-if="entityConfig.conversionHint" class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>{{ entityConfig.conversionHint }}</span>
        </div>
      </el-form-item>

      <el-form-item label="高价值转化通知" prop="notify_on_high_value">
        <el-switch
          v-model="formData.notify_on_high_value"
          :disabled="!formData.notification_enabled"
        />
        <div v-if="entityConfig.highValueHint" class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>{{ entityConfig.highValueHint }}</span>
        </div>
      </el-form-item>

      <el-form-item
        v-if="formData.notify_on_high_value"
        label="高价值阈值"
        prop="high_value_threshold"
      >
        <el-input-number
          v-model="formData.high_value_threshold"
          :min="0"
          :precision="2"
          :step="10"
          style="width: 100%;"
          placeholder="输入金额阈值（美元）"
        />
        <div v-if="entityConfig.thresholdHint" class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>{{ entityConfig.thresholdHint }}</span>
        </div>
      </el-form-item>

      <el-divider />

      <el-form-item label="通知渠道" prop="notify_channels">
        <el-checkbox-group v-model="selectedChannels" :disabled="!formData.notification_enabled">
          <el-checkbox label="telegram">Telegram</el-checkbox>
          <el-checkbox label="email">邮箱</el-checkbox>
          <el-checkbox label="sms">短信</el-checkbox>
        </el-checkbox-group>
        <div v-if="entityConfig.channelsHint" class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>{{ entityConfig.channelsHint }}</span>
        </div>
      </el-form-item>

      <el-form-item
        v-if="selectedChannels.includes('telegram')"
        label="Telegram Chat ID"
        prop="telegram_chat_id"
      >
        <el-input
          v-model="formData.telegram_chat_id"
          placeholder="输入 Telegram Chat ID（例如：-1001234567890）"
          clearable
        />
        <div class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>
            获取 Chat ID：与 @BotFather 创建的机器人对话后发送消息，
            <el-link href="https://t.me/userinfobot" target="_blank" type="primary">点击这里</el-link>
            获取您的 Chat ID
          </span>
        </div>
      </el-form-item>

      <el-form-item
        v-if="selectedChannels.includes('email')"
        label="邮箱地址"
        prop="email_address"
      >
        <el-input
          v-model="formData.email_address"
          type="email"
          placeholder="输入邮箱地址"
          clearable
        />
      </el-form-item>

      <el-form-item
        v-if="selectedChannels.includes('sms')"
        label="手机号"
        prop="phone_number"
      >
        <el-input
          v-model="formData.phone_number"
          placeholder="输入手机号"
          clearable
        />
      </el-form-item>

      <el-divider />

      <el-form-item label="通知频率" prop="notification_frequency">
        <el-radio-group
          v-model="formData.notification_frequency"
          :disabled="!formData.notification_enabled"
        >
          <el-radio label="realtime">实时通知</el-radio>
          <el-radio label="hourly">每小时汇总</el-radio>
          <el-radio label="daily">每天汇总</el-radio>
        </el-radio-group>
        <div class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>实时：立即发送；每小时/每天：汇总后发送</span>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue';
import { ElMessage, ElLink } from 'element-plus';
import { InfoFilled } from '@element-plus/icons-vue';
import {
  getClientNotificationConfig,
  saveClientNotificationConfig,
  getProductNotificationConfig,
  saveProductNotificationConfig,
} from '../../api/notification';
import { useDevice } from '../../composables/useDevice';
import { logger } from '../../utils/logger';

const ENTITY_PRESETS = {
  client: {
    enabledHint: '关闭后，该客户的所有产品转化都不会发送通知',
    conversionHint: '是否在转化发生时发送通知',
    highValueHint: '只通知超过阈值的转化',
    thresholdHint: '只有收益超过此金额的转化才会通知',
    channelsHint: '可以选择多个通知渠道',
    validateTelegram: true,
    getConfig: getClientNotificationConfig,
    saveConfig: saveClientNotificationConfig,
    loadErrorLabel: '客户',
    saveErrorLabel: '客户',
  },
  product: {
    enabledHint: '关闭后，该产品的转化不会发送通知（优先级高于客户配置）',
    conversionHint: null,
    highValueHint: null,
    thresholdHint: null,
    channelsHint: null,
    validateTelegram: false,
    getConfig: getProductNotificationConfig,
    saveConfig: saveProductNotificationConfig,
    loadErrorLabel: '产品',
    saveErrorLabel: '产品',
  },
};

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  entityType: {
    type: String,
    required: true,
    validator: (v) => ['client', 'product'].includes(v),
  },
  entityId: { type: Number, required: true },
  entityName: { type: String, default: '' },
});

const emit = defineEmits(['update:modelValue', 'saved']);

const { isMobile } = useDevice();
const entityConfig = computed(() => ENTITY_PRESETS[props.entityType]);

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
});

const formRef = ref(null);
const loading = ref(false);
const saving = ref(false);

const formData = reactive({
  notification_enabled: true,
  notify_on_conversion: true,
  notify_on_high_value: false,
  high_value_threshold: null,
  notify_channels: null,
  telegram_chat_id: null,
  email_address: null,
  phone_number: null,
  notification_frequency: 'realtime',
});

const selectedChannels = ref([]);

watch(selectedChannels, (newVal) => {
  formData.notify_channels = newVal.length > 0 ? JSON.stringify(newVal) : null;
}, { deep: true });

watch(() => formData.notify_channels, (newVal) => {
  if (newVal) {
    try {
      selectedChannels.value = JSON.parse(newVal);
    } catch {
      selectedChannels.value = [];
    }
  } else {
    selectedChannels.value = [];
  }
}, { immediate: true });

const formRules = computed(() => {
  const rules = {
    high_value_threshold: [{
      validator: (_rule, value, callback) => {
        if (formData.notify_on_high_value && (!value || value <= 0)) {
          callback(new Error('启用高价值转化通知时，必须设置阈值'));
        } else {
          callback();
        }
      },
      trigger: 'blur',
    }],
  };

  if (entityConfig.value.validateTelegram) {
    rules.telegram_chat_id = [{
      validator: (_rule, value, callback) => {
        if (selectedChannels.value.includes('telegram') && formData.notification_enabled) {
          if (!value || !value.trim()) {
            callback(new Error('选择 Telegram 渠道时必须填写 Chat ID'));
          } else if (!/^-?\d+$/.test(value.trim())) {
            callback(new Error('Chat ID 必须是数字（可以是负数）'));
          } else {
            callback();
          }
        } else {
          callback();
        }
      },
      trigger: 'blur',
    }];
  }

  return rules;
});

const loadConfig = async () => {
  if (!props.entityId) return;
  loading.value = true;
  try {
    const config = await entityConfig.value.getConfig(props.entityId);
    Object.assign(formData, {
      notification_enabled: config.notification_enabled ?? true,
      notify_on_conversion: config.notify_on_conversion ?? true,
      notify_on_high_value: config.notify_on_high_value ?? false,
      high_value_threshold: config.high_value_threshold,
      notify_channels: config.notify_channels,
      telegram_chat_id: config.telegram_chat_id,
      email_address: config.email_address,
      phone_number: config.phone_number,
      notification_frequency: config.notification_frequency || 'realtime',
    });
  } catch (error) {
    logger.error(`加载${entityConfig.value.loadErrorLabel}通知配置失败:`, error);
  } finally {
    loading.value = false;
  }
};

const handleSave = async () => {
  if (!formRef.value) return;
  try {
    await formRef.value.validate();
    saving.value = true;
    await entityConfig.value.saveConfig(props.entityId, formData);
    ElMessage.success('通知配置保存成功');
    emit('saved');
    visible.value = false;
  } catch (error) {
    logger.error(`保存${entityConfig.value.saveErrorLabel}通知配置失败:`, error);
  } finally {
    saving.value = false;
  }
};

const handleClose = () => {
  visible.value = false;
};

watch(visible, (val) => {
  if (val && props.entityId) {
    loadConfig();
  }
});
</script>

<style scoped>
.form-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.form-hint .el-icon {
  color: #409eff;
}
</style>
