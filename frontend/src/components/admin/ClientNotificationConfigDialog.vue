<template>
  <el-dialog
    v-model="visible"
    :title="`${clientName} - 通知配置`"
    :width="isMobile ? '95%' : '800px'"
    :close-on-click-modal="false"
    @close="handleClose"
    append-to-body
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
          <span>关闭后，该客户的所有产品转化都不会发送通知</span>
        </div>
      </el-form-item>

      <el-divider />

      <el-form-item label="通知转化事件" prop="notify_on_conversion">
        <el-switch v-model="formData.notify_on_conversion" :disabled="!formData.notification_enabled" />
        <div class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>是否在转化发生时发送通知</span>
        </div>
      </el-form-item>

      <el-form-item label="高价值转化通知" prop="notify_on_high_value">
        <el-switch v-model="formData.notify_on_high_value" :disabled="!formData.notification_enabled" />
        <div class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>只通知超过阈值的转化</span>
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
        <div class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>只有收益超过此金额的转化才会通知</span>
        </div>
      </el-form-item>

      <el-divider />

      <el-form-item label="通知渠道" prop="notify_channels">
        <el-checkbox-group v-model="selectedChannels" :disabled="!formData.notification_enabled">
          <el-checkbox label="telegram">Telegram</el-checkbox>
          <el-checkbox label="email">邮箱</el-checkbox>
          <el-checkbox label="sms">短信</el-checkbox>
        </el-checkbox-group>
        <div class="form-hint">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>可以选择多个通知渠道</span>
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
            获取 Chat ID：与 @BotFather 创建的机器人对话，发送 /start，然后发送任意消息，
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
        <el-radio-group v-model="formData.notification_frequency" :disabled="!formData.notification_enabled">
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
import { getClientNotificationConfig, saveClientNotificationConfig } from '../../api/notification';
import { useDevice } from '../../composables/useDevice';
import { logger } from '../../utils/logger';

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  clientId: {
    type: Number,
    required: true
  },
  clientName: {
    type: String,
    default: '客户'
  }
});

const emit = defineEmits(['update:modelValue', 'saved']);

const { isMobile } = useDevice();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
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
  notification_frequency: 'realtime'
});

const selectedChannels = ref([]);

// 监听 selectedChannels 变化，更新 formData.notify_channels
watch(selectedChannels, (newVal) => {
  formData.notify_channels = newVal.length > 0 ? JSON.stringify(newVal) : null;
}, { deep: true });

// 监听 formData.notify_channels 变化，更新 selectedChannels
watch(() => formData.notify_channels, (newVal) => {
  if (newVal) {
    try {
      selectedChannels.value = JSON.parse(newVal);
    } catch (e) {
      selectedChannels.value = [];
    }
  } else {
    selectedChannels.value = [];
  }
}, { immediate: true });

const formRules = {
  telegram_chat_id: [
    {
      validator: (rule, value, callback) => {
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
      trigger: 'blur'
    }
  ],
  high_value_threshold: [
    {
      validator: (rule, value, callback) => {
        if (formData.notify_on_high_value && (!value || value <= 0)) {
          callback(new Error('启用高价值转化通知时，必须设置阈值'));
        } else {
          callback();
        }
      },
      trigger: 'blur'
    }
  ]
};

// 加载配置
const loadConfig = async () => {
  if (!props.clientId) return;
  
  loading.value = true;
  try {
    const config = await getClientNotificationConfig(props.clientId);
    Object.assign(formData, {
      notification_enabled: config.notification_enabled ?? true,
      notify_on_conversion: config.notify_on_conversion ?? true,
      notify_on_high_value: config.notify_on_high_value ?? false,
      high_value_threshold: config.high_value_threshold,
      notify_channels: config.notify_channels,
      telegram_chat_id: config.telegram_chat_id,
      email_address: config.email_address,
      phone_number: config.phone_number,
      notification_frequency: config.notification_frequency || 'realtime'
    });
  } catch (error) {
    logger.error('加载客户通知配置失败:', error);
  } finally {
    loading.value = false;
  }
};

// 保存配置
const handleSave = async () => {
  if (!formRef.value) return;
  
  try {
    await formRef.value.validate();
    
    saving.value = true;
    await saveClientNotificationConfig(props.clientId, formData);
    ElMessage.success('通知配置保存成功');
    emit('saved');
    visible.value = false;
  } catch (error) {
    logger.error('保存客户通知配置失败:', error);
  } finally {
    saving.value = false;
  }
};

const handleClose = () => {
  visible.value = false;
};

// 监听 visible 变化，加载配置
watch(visible, (val) => {
  if (val && props.clientId) {
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

