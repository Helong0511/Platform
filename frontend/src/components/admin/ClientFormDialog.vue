<template>
  <el-dialog 
    v-model="visible" 
    :title="title" 
    width="750px"
    :close-on-click-modal="false"
    @close="handleClose"
    class="client-form-dialog"
    :destroy-on-close="true"
    :append-to-body="true"
  >
    <el-form 
      ref="formRef" 
      :model="localFormData" 
      :rules="formRules" 
      label-width="130px"
      class="client-form"
      :validate-on-rule-change="false"
    >
      <!-- 用户信息区域 -->
      <el-divider content-position="left" v-if="!isEdit">
        <el-icon :size="16"><User /></el-icon>
        <span style="margin-left: 8px;">用户信息</span>
      </el-divider>
      
      <!-- 创建新用户（添加客户时默认模式） -->
      <template v-if="!isEdit">
        <el-form-item label="登录名" prop="username" class="user-create-item">
          <el-input
            v-model="localFormData.username"
            placeholder="请输入登录名（用户名，必填）"
            clearable
            size="large"
            maxlength="20"
            show-word-limit
          >
            <template #prefix>
              <el-icon :size="16"><User /></el-icon>
            </template>
          </el-input>
          <div class="form-hint">登录名长度在3-20个字符之间，用于登录系统</div>
        </el-form-item>
        
        <el-form-item label="登录密码" prop="password" class="user-create-item">
          <el-input
            v-model="localFormData.password"
            type="password"
            placeholder="请输入登录密码（必填）"
            clearable
            size="large"
            show-password
            maxlength="72"
          >
            <template #prefix>
              <el-icon :size="16"><Lock /></el-icon>
            </template>
          </el-input>
          <div class="form-hint">密码长度至少6个字符，建议使用字母和数字组合</div>
        </el-form-item>
        
        <el-form-item label="邮箱" prop="email" class="user-create-item">
          <el-input
            v-model="localFormData.email"
            type="email"
            placeholder="请输入邮箱地址（必填）"
            clearable
            size="large"
            maxlength="100"
          >
            <template #prefix>
              <el-icon :size="16"><Message /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        
        <el-form-item label="全名" prop="full_name" class="user-create-item">
          <el-input
            v-model="localFormData.full_name"
            placeholder="请输入用户全名"
            clearable
            size="large"
            maxlength="100"
          >
            <template #prefix>
              <el-icon :size="16"><UserFilled /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        
        <div class="user-create-note">
          <el-icon :size="16"><InfoFilled /></el-icon>
          <span>系统将自动创建用户账号并关联到此客户，用户可以使用登录名和密码登录系统</span>
        </div>
      </template>

      <!-- 客户信息区域 -->
      <el-divider content-position="left">
        <el-icon :size="16"><OfficeBuilding /></el-icon>
        <span style="margin-left: 8px;">客户信息</span>
      </el-divider>

      <el-form-item v-if="isEdit" label="API密钥" prop="key">
        <div class="key-input-with-button">
          <div @dblclick="handleKeyDoubleClick" class="key-input-wrapper">
            <el-input 
              v-model="localFormData.key" 
              placeholder="客户API密钥UUID"
              :disabled="!isKeyEditable"
              size="large"
              class="key-input-field"
              readonly
              style="font-family: monospace; font-size: 13px;"
            >
              <template #prefix>
                <el-icon :size="16"><Key /></el-icon>
              </template>
            </el-input>
          </div>
          <el-button 
            type="primary" 
            :icon="Refresh" 
            @click="handleKeyDoubleClick"
            size="large"
            class="generate-key-button"
          >
            生成新密钥
          </el-button>
        </div>
        <div class="form-hint">
          <span v-if="!isKeyEditable">客户API密钥，由系统自动生成，点击"生成新密钥"按钮自动生成新UUID</span>
          <span v-else style="color: #e6a23c;">⚠️ 已自动生成新UUID，您可以继续编辑或直接保存</span>
        </div>
      </el-form-item>

      <el-form-item label="公司名称" prop="company_name">
        <el-input 
          v-model="localFormData.company_name" 
          placeholder="请输入公司名称（必填）"
          clearable
          size="large"
          maxlength="100"
          show-word-limit
        >
          <template #prefix>
            <el-icon :size="16"><OfficeBuilding /></el-icon>
          </template>
        </el-input>
      </el-form-item>

      <el-form-item label="联系人" prop="contact_person">
        <el-input 
          v-model="localFormData.contact_person" 
          placeholder="请输入联系人姓名"
          clearable
          size="large"
          maxlength="50"
          show-word-limit
        >
          <template #prefix>
            <el-icon :size="16"><User /></el-icon>
          </template>
        </el-input>
      </el-form-item>

      <el-form-item label="联系电话" prop="phone">
        <div>
          <el-input 
            v-model="localFormData.phone" 
            placeholder="请输入联系电话（手机号或固定电话）"
            clearable
            size="large"
            maxlength="20"
          >
            <template #prefix>
              <el-icon :size="16"><Phone /></el-icon>
            </template>
          </el-input>
          <div class="form-hint">支持格式：手机号（11位）或固定电话（区号-号码）</div>
        </div>
      </el-form-item>

      <el-form-item label="公司地址" prop="address">
        <el-input 
          v-model="localFormData.address" 
          type="textarea" 
          :rows="3" 
          placeholder="请输入公司详细地址"
          clearable
          maxlength="500"
          show-word-limit
        ></el-input>
      </el-form-item>

      <el-form-item label="状态" prop="is_active">
        <div>
          <el-switch
            v-model="localFormData.is_active"
            active-text="活跃"
            inactive-text="禁用"
            size="large"
            aria-label="切换客户状态"
          ></el-switch>
          <div class="form-hint">活跃状态的客户可以正常使用系统功能</div>
        </div>
      </el-form-item>

      <el-form-item label="API访问" prop="api_enabled">
        <div>
          <el-switch
            v-model="localFormData.api_enabled"
            active-text="启用"
            inactive-text="禁用"
            size="large"
            aria-label="切换API访问权限"
          ></el-switch>
          <div class="form-hint">开启后允许客户通过API查询产品和广告数据，并在客户端显示API对接菜单</div>
        </div>
      </el-form-item>

      <el-form-item label="允许修改密码" prop="password_change_enabled">
        <div>
          <el-switch
            v-model="localFormData.password_change_enabled"
            active-text="允许"
            inactive-text="禁止"
            size="large"
            aria-label="切换密码修改权限"
          ></el-switch>
          <div class="form-hint">开启后允许客户修改自己的登录密码，关闭后客户无法修改密码</div>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button size="large" @click="handleClose">取消</el-button>
        <el-button 
          type="primary" 
          size="large" 
          @click="handleSave" 
          :loading="saving"
          :disabled="!canSave"
          :icon="saving ? undefined : Check"
        >
          <span>{{ saving ? '保存中...' : '保存' }}</span>
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, reactive, computed, nextTick } from 'vue';
import { ElDialog, ElForm, ElFormItem, ElInput, ElSwitch, ElButton, ElIcon, ElMessage, ElDivider } from 'element-plus';
import { User, UserFilled, InfoFilled, OfficeBuilding, Phone, Check, Lock, Message, Key, Edit, Refresh } from '@element-plus/icons-vue';

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    default: '添加客户'
  },
  formData: {
    type: Object,
    required: true
  },
  rules: {
    type: Object,
    default: () => ({})
  },
  isEdit: {
    type: Boolean,
    default: false
  },
  saving: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(['update:modelValue', 'save', 'close']);

const formRef = ref(null);
const visible = ref(props.modelValue);
const isKeyEditable = ref(false);  // key字段是否可编辑


// 创建本地表单数据副本
const localFormData = reactive({
  // 创建新用户字段（添加客户时必填）
  username: '',
  password: '',
  email: '',
  full_name: '',
  // 客户信息字段
  key: '',  // 客户API密钥UUID
  company_name: '',
  contact_person: '',
  phone: '',
  address: '',
  is_active: true,
  api_enabled: false,  // API访问开关，默认关闭
  password_change_enabled: true  // 密码修改开关，默认允许
});

// 计算是否可以保存
const canSave = computed(() => {
  if (props.isEdit) {
    return localFormData.company_name.trim().length > 0;
  }
  
  // 添加模式：需要填写用户信息和公司名称
  return localFormData.username.trim().length >= 3 &&
         localFormData.password.trim().length >= 6 &&
         localFormData.email.trim().length > 0 &&
         localFormData.company_name.trim().length > 0;
});

// 表单验证规则
const formRules = computed(() => {
  const rules = {
    username: props.isEdit ? [] : [
      { required: true, message: '请输入登录名', trigger: 'blur' },
      { min: 3, max: 20, message: '登录名长度在 3 到 20 个字符之间', trigger: 'blur' },
      {
        validator: (rule, value, callback) => {
          if (!value || value.trim().length < 3) {
            callback(new Error('登录名至少需要3个字符'));
          } else if (value.trim().length > 20) {
            callback(new Error('登录名不能超过20个字符'));
          } else {
            callback();
          }
        },
        trigger: 'blur'
      }
    ],
    password: props.isEdit ? [] : [
      { required: true, message: '请输入登录密码', trigger: 'blur' },
      { min: 6, message: '密码长度不能少于 6 个字符', trigger: 'blur' },
      {
        validator: (rule, value, callback) => {
          if (!value || value.trim().length < 6) {
            callback(new Error('密码长度不能少于 6 个字符'));
          } else {
            callback();
          }
        },
        trigger: 'blur'
      }
    ],
    email: props.isEdit ? [] : [
      { required: true, message: '请输入邮箱', trigger: 'blur' },
      { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
    ],
    full_name: props.isEdit ? [] : [
      { max: 100, message: '全名不能超过100个字符', trigger: 'blur' }
    ],
    company_name: [
      { required: true, message: '请输入公司名称', trigger: 'blur' },
      { min: 2, max: 100, message: '公司名称长度在 2 到 100 个字符之间', trigger: 'blur' },
      {
        validator: (rule, value, callback) => {
          if (!value || value.trim().length === 0) {
            callback(new Error('公司名称不能为空'));
          } else if (value.trim().length < 2) {
            callback(new Error('公司名称至少需要2个字符'));
          } else {
            callback();
          }
        },
        trigger: 'blur'
      }
    ],
    contact_person: [
      { max: 50, message: '联系人姓名不能超过50个字符', trigger: 'blur' }
    ],
    phone: [
      {
        validator: (rule, value, callback) => {
          if (!value || value.trim() === '') {
            callback(); // 可选字段
          } else {
            const phonePattern = /^1[3-9]\d{9}$|^0\d{2,3}-?\d{7,8}$/;
            if (!phonePattern.test(value.trim())) {
              callback(new Error('请输入正确的电话号码格式（手机号或固定电话）'));
            } else {
              callback();
            }
          }
        },
        trigger: 'blur'
      }
    ],
    address: [
      { max: 500, message: '地址不能超过500个字符', trigger: 'blur' }
    ],
    key: [
      {
        validator: (rule, value, callback) => {
          if (!value || value.trim() === '') {
            callback(); // 可选字段
          } else {
            const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
            if (!uuidPattern.test(value.trim())) {
              callback(new Error('UUID格式不正确，请使用有效的UUID格式（例如：xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx）'));
            } else {
              callback();
            }
          }
        },
        trigger: 'blur'
      }
    ]
  };
  return rules;
});


// 初始化表单数据
const initFormData = () => {
  const formData = props.formData || {};
  Object.assign(localFormData, {
    username: formData.username || '',
    password: formData.password || '',
    email: formData.email || '',
    full_name: formData.full_name || '',
    key: formData.key || '',
    company_name: formData.company_name || '',
    contact_person: formData.contact_person || '',
    phone: formData.phone || '',
    address: formData.address || '',
    is_active: formData.is_active !== undefined ? formData.is_active : true,
    api_enabled: formData.api_enabled !== undefined ? formData.api_enabled : false,
    password_change_enabled: formData.password_change_enabled !== undefined ? formData.password_change_enabled : true
  });
  
  // 添加模式：重置用户信息字段
  if (!props.isEdit) {
    localFormData.username = '';
    localFormData.password = '';
    localFormData.email = '';
    localFormData.full_name = '';
  }
  
  // 重置key字段编辑状态
  isKeyEditable.value = false;
};


// 监听props.formData变化
watch(() => props.formData, (newData) => {
  if (newData) {
    initFormData();
  }
}, { deep: true, immediate: true });

// 监听对话框显示状态
watch(() => props.modelValue, (val) => {
  visible.value = val;
  if (val) {
    initFormData();
    nextTick(() => {
      if (formRef.value) {
        formRef.value.clearValidate();
      }
    });
  }
});

watch(visible, (val) => {
  emit('update:modelValue', val);
});

const handleClose = () => {
  visible.value = false;
  isKeyEditable.value = false;  // 关闭时重置编辑状态
  emit('close');
};

// 处理key字段双击事件 - 直接生成新的UUID
const handleKeyDoubleClick = (event) => {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  
  if (props.isEdit) {
    // 直接生成新的UUID并启用编辑
    const newUUID = generateUUID();
    localFormData.key = newUUID;
    isKeyEditable.value = true;
    ElMessage.success('已自动生成新的UUID，您可以继续编辑或直接保存');
  }
};

// 生成UUID的函数
const generateUUID = () => {
  // 使用crypto.randomUUID()如果可用，否则使用备用方法
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // 备用方法：生成标准UUID v4格式
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
};

const handleSave = async () => {
  if (!formRef.value) return;
  
  // 添加模式：验证用户信息
  if (!props.isEdit) {
    // 创建新用户模式：验证用户信息是否完整
    if (!localFormData.username || !localFormData.password || !localFormData.email) {
      ElMessage.error('请填写完整的用户信息（登录名、密码、邮箱）');
      return;
    }
  }
  
  try {
    await formRef.value.validate();
    
    // 准备提交数据
    const formDataToSave = {
      company_name: localFormData.company_name.trim(),
      contact_person: localFormData.contact_person?.trim() || null,
      phone: localFormData.phone?.trim() || null,
      address: localFormData.address?.trim() || null,
      is_active: localFormData.is_active,
      api_enabled: localFormData.api_enabled,
      password_change_enabled: localFormData.password_change_enabled
    };
    
    // 如果key字段被编辑了，添加到提交数据中
    if (props.isEdit && isKeyEditable.value && localFormData.key) {
      formDataToSave.key = localFormData.key.trim();
    }
    
    if (!props.isEdit) {
      // 添加模式：提供用户信息（创建新用户）
      formDataToSave.username = localFormData.username.trim();
      formDataToSave.password = localFormData.password;
      formDataToSave.email = localFormData.email.trim();
      if (localFormData.full_name) {
        formDataToSave.full_name = localFormData.full_name.trim();
      }
    }
    
    emit('save', formDataToSave);
  } catch (error) {
    // 表单验证失败
    const firstError = Object.keys(error).find(key => error[key] && error[key].length > 0);
    if (firstError) {
      ElMessage.warning('请检查表单填写是否正确');
    }
  }
};

defineExpose({
  validate: () => formRef.value?.validate(),
  clearValidate: () => formRef.value?.clearValidate()
});
</script>

<style scoped>
.client-form-dialog :deep(.el-dialog) {
  border-radius: var(--radius-xxl);
}

.client-form-dialog :deep(.el-dialog__header) {
  padding: var(--spacing-xxl) var(--spacing-xxxl);
  border-bottom: 1px solid var(--border-lighter);
}

.client-form-dialog :deep(.el-dialog__body) {
  padding: var(--spacing-xxxl);
}

.client-form-dialog :deep(.el-dialog__footer) {
  padding: var(--spacing-xl) var(--spacing-xxxl);
  border-top: 1px solid var(--border-lighter);
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-md);
}

.client-form {
  padding: var(--spacing-md) 0;
}

.client-form :deep(.el-form-item) {
  margin-bottom: var(--spacing-xxl);
}

.client-form :deep(.el-form-item__label) {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

.client-form-dialog :deep(.el-divider__text) {
  display: flex;
  align-items: center;
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-md);
  color: var(--text-primary);
  background-color: var(--bg-primary);
  padding: 0 var(--spacing-lg);
}

/* 用户搜索区域 */
.user-search-item {
  margin-bottom: var(--spacing-xxl);
}

.user-search-wrapper {
  width: 100%;
}

.user-info-card {
  margin-top: 12px;
  padding: 16px;
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border: 2px solid #0ea5e9;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(14, 165, 233, 0.15);
}

.user-info-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 600;
  color: #0369a1;
}

.user-info-title {
  font-size: 14px;
}

.user-info-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-info-row {
  display: flex;
  align-items: center;
  font-size: 13px;
}

.user-info-row .label {
  color: #64748b;
  min-width: 70px;
  font-weight: 500;
}

.user-info-row .value {
  color: #1e293b;
  font-weight: 500;
}

.user-info-row .value.highlight {
  color: #0ea5e9;
  font-weight: 700;
  font-size: 14px;
}

.user-relation-note {
  margin-top: 8px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #0369a1;
}

.user-relation-note strong {
  color: #0ea5e9;
  font-weight: 700;
}

.user-error-card {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #dc2626;
  font-size: 13px;
}

.user-hint-card {
  margin-top: 12px;
  padding: 12px 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #64748b;
  font-size: 12px;
}

.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.success-icon {
  color: #67c23a;
  font-size: 18px;
}

.error-icon {
  color: #f56c6c;
  font-size: 18px;
}

.is-loading {
  animation: rotating 2s linear infinite;
  color: var(--primary-color);
}

@keyframes rotating {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.dialog-footer .el-button {
  padding: 12px 28px;
  font-size: 15px;
  font-weight: 500;
}

/* 输入框样式优化 */
:deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #dcdfe6 inset;
  transition: all 0.3s;
}

:deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #c0c4cc inset;
}

:deep(.el-input.is-focus .el-input__wrapper) {
  box-shadow: 0 0 0 1px #409eff inset;
}

/* Key字段样式 */
.key-input-with-button {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  width: 100%;
}

.key-input-wrapper {
  flex: 1;
  cursor: pointer;
  min-width: 350px; /* 确保有足够空间显示完整的UUID */
}

.key-input-field {
  cursor: pointer;
  transition: all 0.3s;
  width: 100%;
}

.key-input-field :deep(.el-input__wrapper) {
  overflow: visible;
  width: 100%;
}

.key-input-field :deep(.el-input__inner) {
  font-family: monospace;
  font-size: 13px;
  letter-spacing: 0.5px;
  overflow: visible;
  text-overflow: clip;
  white-space: nowrap;
  width: 100%;
}

.generate-key-button {
  white-space: nowrap;
  flex-shrink: 0;
}

.key-input-field:deep(.el-input__wrapper) {
  transition: all 0.3s;
}

.key-input-field:deep(.el-input.is-disabled .el-input__wrapper) {
  cursor: pointer;
  background-color: #f5f7fa;
}

.key-input-field:deep(.el-input.is-disabled .el-input__wrapper:hover) {
  background-color: #ebedf0;
  box-shadow: 0 0 0 1px #c0c4cc inset;
}

.key-input-field:deep(.el-input:not(.is-disabled) .el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}

.edit-hint-icon {
  color: #909399;
  font-size: 14px;
  cursor: pointer;
  transition: color 0.3s;
}

.edit-hint-icon:hover {
  color: var(--primary-color);
}

/* 响应式设计 */
@media (max-width: 767px) {
  .client-form-dialog :deep(.el-dialog) {
    width: 95% !important;
    max-width: 95% !important;
    margin: var(--spacing-md) auto !important;
  }
  
  .client-form-dialog :deep(.el-dialog__header) {
    padding: var(--spacing-md) var(--spacing-lg);
  }
  
  .client-form-dialog :deep(.el-dialog__title) {
    font-size: var(--font-size-lg);
  }
  
  .client-form-dialog :deep(.el-dialog__body) {
    padding: var(--spacing-md);
    max-height: calc(100vh - 200px);
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .client-form-dialog :deep(.el-dialog__footer) {
    padding: var(--spacing-md) var(--spacing-lg);
    display: flex;
    flex-direction: row;
    gap: var(--spacing-sm);
  }
  
  .client-form-dialog :deep(.el-dialog__footer .el-button) {
    flex: 1;
    min-height: var(--touch-target-size);
  }
  
  /* 表单移动端优化 */
  .client-form :deep(.el-form-item__label) {
    width: 100% !important;
    text-align: left !important;
    margin-bottom: var(--spacing-xs) !important;
    padding: 0 !important;
  }
  
  .client-form :deep(.el-form-item__content) {
    width: 100% !important;
    margin-left: 0 !important;
  }
  
  .client-form :deep(.el-input),
  .client-form :deep(.el-select),
  .client-form :deep(.el-textarea) {
    width: 100% !important;
  }
  
  .client-form :deep(.el-input__wrapper) {
    min-height: var(--touch-target-size);
  }
  
  .client-form :deep(.el-select .el-input__wrapper) {
    min-height: var(--touch-target-size);
  }
  
  .client-form :deep(.el-textarea .el-textarea__inner) {
    min-height: 80px;
    font-size: var(--font-size-base);
  }
  
  /* 分隔线优化 */
  .client-form :deep(.el-divider) {
    margin: var(--spacing-md) 0 !important;
  }
  
  .client-form :deep(.el-divider__text) {
    font-size: var(--font-size-base);
    padding: 0 var(--spacing-md);
  }
  
  /* 表单提示优化 */
  .form-hint {
    font-size: var(--font-size-xs);
    margin-top: var(--spacing-xs);
    padding: var(--spacing-xs) var(--spacing-sm);
  }
}
</style>
