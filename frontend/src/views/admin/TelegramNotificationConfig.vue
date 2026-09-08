<!--
  管理端 - Telegram 通知配置
  @file views/admin/TelegramNotificationConfig.vue
-->
<template>
  <!-- 页面主模板 -->
  <div class="telegram-notification-config">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>Telegram 通知配置</h2>
      <p class="page-description">配置管理员的 Telegram 通知设置</p>
    </div>

    <!-- 配置表单 -->
    <el-card class="config-card" v-loading="loading">
      <!-- 表单区域 -->
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="180px"
      >
        <!-- 基础配置 -->
        <el-divider content-position="left">
          <el-icon :size="16"><Setting /></el-icon>
          <span style="margin-left: 8px;">基础配置</span>
        </el-divider>

        <el-form-item label="启用 Telegram 通知" prop="telegram_enabled">
          <el-switch v-model="formData.telegram_enabled" />
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>关闭后，所有 Telegram 通知将不会发送</span>
          </div>
        </el-form-item>

        <el-form-item
          label="Telegram Chat ID"
          prop="telegram_chat_id"
          :rules="[
            { required: formData.telegram_enabled, message: '启用通知时必须填写 Chat ID', trigger: 'blur' },
            { pattern: /^-?\d+$/, message: 'Chat ID 必须是数字（可以是负数）', trigger: 'blur' }
          ]"
        >
          <el-input
            v-model="formData.telegram_chat_id"
            placeholder="输入 Telegram Chat ID（例如：-1001234567890）"
            clearable
            :disabled="!formData.telegram_enabled"
            style="width: 400px;"
          >
            <template #append>
              <el-button
                @click="handleTestConnection"
                :loading="testingConnection"
                :disabled="!formData.telegram_chat_id || !formData.telegram_enabled"
              >
                测试连接
              </el-button>
            </template>
          </el-input>
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>
              获取 Chat ID：与 @BotFather 创建的机器人对话，发送 /start，然后发送任意消息，
              <el-link href="https://t.me/userinfobot" target="_blank" rel="noopener noreferrer" type="primary">点击这里</el-link>
              获取您的 Chat ID
            </span>
          </div>
        </el-form-item>

        <el-divider content-position="left">
          <el-icon :size="16"><Bell /></el-icon>
          <span style="margin-left: 8px;">通知场景配置</span>
        </el-divider>

        <el-form-item label="通知所有转化" prop="notify_all_conversions">
          <el-switch
            v-model="formData.notify_all_conversions"
            :disabled="!formData.telegram_enabled"
          />
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>当系统内任何转化发生时，发送通知给管理员</span>
          </div>
        </el-form-item>

        <el-form-item label="通知转发失败" prop="notify_forward_failure">
          <el-switch
            v-model="formData.notify_forward_failure"
            :disabled="!formData.telegram_enabled"
          />
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>当 Postback 转发给渠道失败时，发送告警</span>
          </div>
        </el-form-item>

        <el-form-item label="通知转发成功" prop="notify_forward_success">
          <el-switch
            v-model="formData.notify_forward_success"
            :disabled="!formData.telegram_enabled"
          />
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>当 Postback 转发给渠道成功时，发送通知（可选，默认关闭）</span>
          </div>
        </el-form-item>

        <el-form-item label="通知系统异常" prop="notify_system_errors">
          <el-switch
            v-model="formData.notify_system_errors"
            :disabled="!formData.telegram_enabled"
          />
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>当系统发生异常时，发送告警</span>
          </div>
        </el-form-item>

        <el-form-item label="定时统计通知" prop="notify_statistics">
          <el-switch
            v-model="formData.notify_statistics"
            :disabled="!formData.telegram_enabled"
          />
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>定时发送系统统计信息</span>
          </div>
        </el-form-item>

        <el-form-item
          v-if="formData.notify_statistics"
          label="统计频率"
          prop="statistics_frequency"
        >
          <el-radio-group
            v-model="formData.statistics_frequency"
            :disabled="!formData.telegram_enabled || !formData.notify_statistics"
          >
            <el-radio label="hourly">每小时</el-radio>
            <el-radio label="daily">每天</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 消息预览 -->
        <el-divider content-position="left">
          <el-icon :size="16"><View /></el-icon>
          <span style="margin-left: 8px;">消息预览</span>
        </el-divider>

        <el-form-item label="预览消息类型">
          <el-select
            v-model="previewMessageType"
            placeholder="选择消息类型"
            style="width: 200px;"
          >
            <el-option label="转化通知" value="conversion" />
            <el-option label="转发失败告警" value="forward_failure" />
            <el-option label="系统异常告警" value="system_error" />
          </el-select>
        </el-form-item>

        <el-form-item label="消息预览">
          <el-input
            v-model="previewMessage"
            type="textarea"
            :rows="15"
            readonly
            style="font-family: monospace; font-size: 12px;"
          />
        </el-form-item>
      </el-form>

      <!-- 操作按钮 -->
      <div class="action-buttons">
        <el-button type="primary" @click="handleSave" :loading="saving" size="large">
          <el-icon><Check /></el-icon>
          <span>保存配置</span>
        </el-button>
        <el-button @click="handleReset" size="large">
          <el-icon><Refresh /></el-icon>
          <span>重置</span>
        </el-button>
        <el-button
          @click="handleTestSend"
          :loading="testingMessage"
          :disabled="!formData.telegram_chat_id || !formData.telegram_enabled"
          size="large"
        >
          <el-icon><Message /></el-icon>
          <span>测试发送</span>
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  Setting,
  Bell,
  View,
  InfoFilled,
  Check,
  Refresh,
  Message
} from '@element-plus/icons-vue';
import {
  getAdminNotificationConfig,
  saveAdminNotificationConfig,
  testTelegramConnection,
  sendTestMessage
} from '../../api/notification';
import { logger } from '../../utils/logger';
import { TelegramNotificationService } from '../../services/telegram_notification_service';

const formRef = ref(null);
const loading = ref(false);
const saving = ref(false);
const testingConnection = ref(false);
const testingMessage = ref(false);

const DEFAULT_ADMIN_TELEGRAM_CHAT_ID = '5312177749';

const formData = reactive({
  telegram_enabled: true,
  telegram_chat_id: DEFAULT_ADMIN_TELEGRAM_CHAT_ID,
  notify_all_conversions: true,
  notify_forward_failure: true,
  notify_forward_success: false,
  notify_system_errors: true,
  notify_statistics: false,
  statistics_frequency: 'hourly'
});

const previewMessageType = ref('conversion');
const previewMessage = computed(() => {
  // 使用前端服务构建预览消息
  return TelegramNotificationService.buildTestMessage(previewMessageType.value);
});

const formRules = {
  telegram_chat_id: [
    {
      validator: (rule, value, callback) => {
        if (formData.telegram_enabled && (!value || !value.trim())) {
          callback(new Error('启用通知时必须填写 Chat ID'));
        } else if (value && !/^-?\d+$/.test(value)) {
          callback(new Error('Chat ID 必须是数字（可以是负数）'));
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
  loading.value = true;
  try {
    const config = await getAdminNotificationConfig();
    if (config) {
      Object.assign(formData, {
        telegram_enabled: config.telegram_enabled ?? true,
        telegram_chat_id: config.telegram_chat_id || DEFAULT_ADMIN_TELEGRAM_CHAT_ID,
        notify_all_conversions: config.notify_all_conversions ?? true,
        notify_forward_failure: config.notify_forward_failure ?? true,
        notify_forward_success: config.notify_forward_success ?? false,
        notify_system_errors: config.notify_system_errors ?? true,
        notify_statistics: config.notify_statistics ?? false,
        statistics_frequency: config.statistics_frequency || 'hourly'
      });
    }
  } catch (error) {
    logger.error('加载管理员通知配置失败:', error);
    ElMessage.error('加载配置失败，请刷新页面重试');
  } finally {
    loading.value = false;
  }
};

// 保存配置
const handleSave = async () => {
  if (!formRef.value) return;
  
  try {
    await formRef.value.validate();
  } catch (error) {
    ElMessage.warning('请检查表单填写是否正确');
    return;
  }

  saving.value = true;
  try {
    await saveAdminNotificationConfig(formData);
    ElMessage.success('配置已保存');
  } catch (error) {
    logger.error('保存管理员通知配置失败:', error);
    ElMessage.error('保存配置失败，请重试');
  } finally {
    saving.value = false;
  }
};

// 重置配置
const handleReset = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要重置为默认配置吗？',
      '确认重置',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    
    Object.assign(formData, {
      telegram_enabled: true,
      telegram_chat_id: DEFAULT_ADMIN_TELEGRAM_CHAT_ID,
      notify_all_conversions: true,
      notify_forward_failure: true,
      notify_forward_success: false,
      notify_system_errors: true,
      notify_statistics: false,
      statistics_frequency: 'hourly'
    });
    
    ElMessage.success('已重置为默认配置');
  } catch (error) {
    // 用户取消
  }
};

// 测试连接
const handleTestConnection = async () => {
  if (!formData.telegram_chat_id) {
    ElMessage.warning('请先输入 Telegram Chat ID');
    return;
  }

  testingConnection.value = true;
  try {
    const result = await testTelegramConnection(formData.telegram_chat_id);
    if (result && result.success) {
      ElMessage.success('连接成功，测试消息已发送');
    } else {
      ElMessage.error((result && result.message) || '连接失败，请检查 Chat ID 是否正确');
    }
  } catch (error) {
    logger.error('测试 Telegram 连接失败:', error);
    const detail = error?.response?.data?.detail || error?.message || '请检查 Chat ID 是否正确';
    ElMessage.error(`测试连接失败：${detail}`);
  } finally {
    testingConnection.value = false;
  }
};

// 测试发送
const handleTestSend = async () => {
  if (!formData.telegram_chat_id) {
    ElMessage.warning('请先输入 Telegram Chat ID');
    return;
  }

  testingMessage.value = true;
  try {
    const result = await sendTestMessage(formData.telegram_chat_id, previewMessageType.value);
    if (result && result.success) {
      ElMessage.success('测试消息已发送');
    } else {
      ElMessage.error((result && result.message) || '发送失败，请检查 Chat ID 是否正确');
    }
  } catch (error) {
    logger.error('发送测试消息失败:', error);
    const detail = error?.response?.data?.detail || error?.message || '请重试';
    ElMessage.error(`发送测试消息失败：${detail}`);
  } finally {
    testingMessage.value = false;
  }
};

// 页面加载时获取配置
onMounted(() => {
  loadConfig();
});
</script>

<style scoped>
.telegram-notification-config {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
}

.page-description {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.config-card {
  max-width: 1200px;
}

.form-hint {
  display: flex;
  align-items: center;
  margin-top: 8px;
  color: #909399;
  font-size: 12px;
  gap: 4px;
}

.action-buttons {
  margin-top: 30px;
  display: flex;
  gap: 12px;
  justify-content: flex-start;
}

:deep(.el-divider__text) {
  font-weight: 600;
  color: #303133;
}
</style>
