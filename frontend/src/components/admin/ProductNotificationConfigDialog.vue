<!--
  产品通知配置弹窗
  @file components/admin/ProductNotificationConfigDialog.vue
-->
<template>
  <!-- 页面主模板 -->
<!-- 弹窗区域 -->
<!-- 弹窗 -->
    <el-dialog
    v-model="visible"
    :title="`${productName} - 通知配置`"
    :width="isMobile ? '95%' : '800px'"
    :close-on-click-modal="false"
    @close="handleClose"
    append-to-body
  >
    <!-- 表单区域 -->
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
          <span>关闭后，该产品的转化不会发送通知（优先级高于客户配置）</span>
        </div>
      </el-form-item>

      <el-divider />

      <el-form-item label="通知转化事件" prop="notify_on_conversion">
        <el-switch v-model="formData.notify_on_conversion" :disabled="!formData.notification_enabled" />
      </el-form-item>

      <el-form-item label="高价值转化通知" prop="notify_on_high_value">
        <el-switch v-model="formData.notify_on_high_value" :disabled="!formData.notification_enabled" />
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
        />
      </el-form-item>

      <el-divider />

      <el-form-item label="通知渠道" prop="notify_channels">
        <el-checkbox-group v-model="selectedChannels" :disabled="!formData.notification_enabled">
          <el-checkbox label="telegram">Telegram</el-checkbox>
          <el-checkbox label="email">邮箱</el-checkbox>
          <el-checkbox label="sms">短信</el-checkbox>
        </el-checkbox-group>
      </el-form-item>

      <el-form-item
        v-if="selectedChannels.includes('telegram')"
        label="Telegram Chat ID"
        prop="telegram_chat_id"
      >
        <el-input v-model="formData.telegram_chat_id" placeholder="输入 Telegram Chat ID" />
      </el-form-item>

      <el-form-item
        v-if="selectedChannels.includes('email')"
        label="邮箱地址"
        prop="email_address"
      >
        <el-input v-model="formData.email_address" type="email" placeholder="输入邮箱地址" />
      </el-form-item>

      <el-form-item
        v-if="selectedChannels.includes('sms')"
        label="手机号"
        prop="phone_number"
      >
        <el-input v-model="formData.phone_number" placeholder="输入手机号" />
      </el-form-item>

      <el-divider />

      <el-form-item label="通知频率" prop="notification_frequency">
        <el-radio-group v-model="formData.notification_frequency" :disabled="!formData.notification_enabled">
          <el-radio label="realtime">实时通知</el-radio>
          <el-radio label="hourly">每小时汇总</el-radio>
          <el-radio label="daily">每天汇总</el-radio>
        </el-radio-group>
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
import { ElMessage } from 'element-plus';
import { InfoFilled } from '@element-plus/icons-vue';
import { getProductNotificationConfig, saveProductNotificationConfig } from '../../api/notification';
import { useDevice } from '../../composables/useDevice';
import { logger } from '../../utils/logger';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  productId: { type: Number, required: true },
  productName: { type: String, default: '产品' }
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

watch(selectedChannels, (newVal) => {
  formData.notify_channels = newVal.length > 0 ? JSON.stringify(newVal) : null;
}, { deep: true });

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
  high_value_threshold: [{
    validator: (rule, value, callback) => {
      if (formData.notify_on_high_value && (!value || value <= 0)) {
        callback(new Error('启用高价值转化通知时，必须设置阈值'));
      } else {
        callback();
      }
    },
    trigger: 'blur'
  }]
};

const loadConfig = async () => {
  if (!props.productId) return;
  loading.value = true;
  try {
    const config = await getProductNotificationConfig(props.productId);
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
    logger.error('加载产品通知配置失败:', error);
  } finally {
    loading.value = false;
  }
};

const handleSave = async () => {
  if (!formRef.value) return;
  try {
    await formRef.value.validate();
    saving.value = true;
    await saveProductNotificationConfig(props.productId, formData);
    ElMessage.success('通知配置保存成功');
    emit('saved');
    visible.value = false;
  } catch (error) {
    logger.error('保存产品通知配置失败:', error);
  } finally {
    saving.value = false;
  }
};

const handleClose = () => {
  visible.value = false;
};

watch(visible, (val) => {
  if (val && props.productId) {
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
</style>

