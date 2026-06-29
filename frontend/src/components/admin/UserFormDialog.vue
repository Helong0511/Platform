<!--
  用户添加/编辑表单弹窗
  @file components/admin/UserFormDialog.vue
-->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    :width="isMobile ? '95%' : '800px'"
    :close-on-click-modal="false"
    :append-to-body="true"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form
      ref="formRef"
      :model="userForm"
      :rules="formRules"
      :label-width="isMobile ? '0' : '120px'"
      @submit.prevent
    >
      <el-divider content-position="left">用户信息</el-divider>
      <el-row :gutter="20">
        <el-col :xs="24" :sm="24" :md="12" :lg="12">
          <el-form-item label="登录名" prop="username">
            <el-input
              v-model="userForm.username"
              name="username"
              placeholder="请输入登录名（用户名）"
              clearable
              :disabled="!!currentUserId && editingUserRole === 'admin'"
              @blur="emit('username-blur')"
            />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="24" :md="12" :lg="12">
          <el-form-item label="全名" prop="full_name">
            <el-input v-model="userForm.full_name" name="full_name" placeholder="请输入全名" clearable />
          </el-form-item>
          <div class="form-hint form-hint-offset">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>全局使用</span>
          </div>
        </el-col>
      </el-row>
      <el-row :gutter="20">
        <el-col :xs="24" :sm="24" :md="12" :lg="12">
          <el-form-item label="邮箱" prop="email">
            <el-input v-model="userForm.email" name="email" type="email" placeholder="请输入邮箱" clearable />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="24" :md="12" :lg="12">
          <el-form-item label="角色" prop="role">
            <el-select
              v-model="userForm.role"
              name="role"
              placeholder="请选择角色"
              style="width: 100%;"
              popper-class="select-dropdown"
              :teleported="true"
              :disabled="!!currentUserId && editingUserRole === 'admin'"
              @change="emit('role-change')"
            >
              <el-option label="管理员" value="admin" />
              <el-option label="客户" value="client" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="20">
        <el-col :xs="24" :sm="24" :md="12" :lg="12">
          <el-form-item label="密码" :prop="!currentUserId ? 'password' : undefined">
            <el-input
              v-model="userForm.password"
              name="password"
              type="password"
              :placeholder="!currentUserId ? '请输入密码（至少8位，最多72字符）' : '留空则不修改密码'"
              show-password
              clearable
              maxlength="72"
            />
            <div v-if="!currentUserId" class="form-hint form-hint-offset">
              <el-icon :size="16"><InfoFilled /></el-icon>
              <span>密码长度限制：8-72个字符（bcrypt算法限制）</span>
            </div>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="24" :md="12" :lg="12">
          <el-form-item label="状态">
            <el-switch
              v-model="userForm.is_active"
              active-text="启用"
              inactive-text="禁用"
              aria-label="切换用户状态"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <template v-if="showClientForm">
        <el-divider content-position="left">客户信息</el-divider>
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="API密钥">
              <div class="key-input-with-button">
                <div class="key-input-wrapper" @dblclick="emit('key-double-click', $event)">
                  <el-input
                    v-model="userForm.client_key"
                    name="client_key"
                    placeholder="客户API密钥UUID（创建时自动生成）"
                    :disabled="!userForm.isKeyEditable && !currentUserId"
                    class="key-input-field"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                    :prefix-icon="Key"
                  />
                </div>
                <el-button
                  v-if="currentUserId"
                  type="primary"
                  :icon="Refresh"
                  class="generate-key-button"
                  @click="emit('key-double-click', $event)"
                >
                  生成新密钥
                </el-button>
              </div>
              <div class="key-hint">
                <span v-if="!currentUserId">客户API密钥将在创建时由系统自动生成</span>
                <span v-else-if="!userForm.isKeyEditable">客户API密钥，由系统自动生成，双击输入框或点击"生成新密钥"按钮自动生成新UUID</span>
                <span v-else class="key-hint-warn">⚠️ 已自动生成新UUID，您可以继续编辑或直接保存</span>
              </div>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :xs="24" :sm="24" :md="12" :lg="12">
            <el-form-item label="公司名称" prop="company_name">
              <el-input v-model="userForm.company_name" name="company_name" placeholder="请输入公司名称" clearable />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="24" :md="12" :lg="12">
            <el-form-item label="联系人" prop="contact_person">
              <el-input v-model="userForm.contact_person" name="contact_person" placeholder="请输入联系人姓名" clearable />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :xs="24" :sm="24" :md="12" :lg="12">
            <el-form-item label="联系电话" prop="phone">
              <el-input v-model="userForm.phone" name="phone" placeholder="请输入联系电话" clearable />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="24" :md="24" :lg="24">
            <el-form-item label="地址" prop="address">
              <el-input
                v-model="userForm.address"
                name="address"
                type="textarea"
                :rows="3"
                placeholder="请输入公司地址"
                clearable
              />
            </el-form-item>
          </el-col>
        </el-row>
      </template>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" :loading="loading" @click="handleSave">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue';
import {
  ElButton,
  ElCol,
  ElDialog,
  ElDivider,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElOption,
  ElRow,
  ElSelect,
  ElSwitch,
} from 'element-plus';
import { InfoFilled, Key, Refresh } from '@element-plus/icons-vue';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '添加用户' },
  isMobile: { type: Boolean, default: false },
  userForm: { type: Object, required: true },
  formRules: { type: Object, required: true },
  currentUserId: { type: Number, default: null },
  editingUserRole: { type: String, default: null },
  showClientForm: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
});

const emit = defineEmits([
  'update:modelValue',
  'save',
  'username-blur',
  'role-change',
  'key-double-click',
]);

const formRef = ref(null);

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      nextTick(() => formRef.value?.clearValidate());
    }
  },
);

async function handleSave() {
  if (!formRef.value) return;
  await formRef.value.validate();
  emit('save');
}

defineExpose({
  clearValidate: () => formRef.value?.clearValidate(),
});
</script>

<style scoped>
.form-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.form-hint-offset {
  margin-left: 120px;
}

.key-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.key-hint-warn {
  color: #e6a23c;
}
</style>

<style scoped src="../../styles/user-management.css"></style>
