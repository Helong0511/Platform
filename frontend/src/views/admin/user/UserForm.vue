<!--
用户表单组件
从 UserManagement.vue 拆分
-->
<template>
  <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑用户' : '新建用户'" width="500px" :close-on-click-modal="false" @closed="handleClosed">
    <el-form ref="formRef" :model="formData" :rules="rules" label-width="100px">
      <el-form-item label="用户名" prop="username">
        <el-input v-model="formData.username" placeholder="请输入用户名" maxlength="50" />
      </el-form-item>
      <el-form-item label="全名" prop="full_name">
        <el-input v-model="formData.full_name" placeholder="请输入全名" maxlength="100" />
      </el-form-item>
      <el-form-item label="邮箱" prop="email">
        <el-input v-model="formData.email" placeholder="请输入邮箱" maxlength="100" />
      </el-form-item>
      <el-form-item label="密码" prop="password" v-if="!isEdit">
        <el-input v-model="formData.password" type="password" placeholder="请输入密码" show-password />
      </el-form-item>
      <el-form-item label="角色" prop="role">
        <el-radio-group v-model="formData.role">
          <el-radio label="admin">管理员</el-radio>
          <el-radio label="client">客户</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="状态">
        <el-switch v-model="formData.is_active" active-text="激活" inactive-text="禁用" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { createUser, updateUser, getUserDetail } from '@/api/user';

const props = defineProps({ modelValue: Boolean, userId: { type: Number, default: null } });
const emit = defineEmits(['update:modelValue', 'success']);

const dialogVisible = computed({ get: () => props.modelValue, set: (val) => emit('update:modelValue', val) });
const isEdit = computed(() => !!props.userId);
const formRef = ref(null);
const submitLoading = ref(false);

const formData = reactive({ username: '', full_name: '', email: '', password: '', role: 'client', is_active: true });

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }, { min: 3, max: 50, message: '长度 3-50 字符', trigger: 'blur' }],
  email: [{ type: 'email', message: '请输入有效邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 6, message: '密码至少 6 位', trigger: 'blur' }]
};

const loadUser = async () => {
  if (!props.userId) return;
  try {
    const data = await getUserDetail(props.userId);
    Object.assign(formData, { username: data.username, full_name: data.full_name, email: data.email, role: data.role, is_active: data.is_active });
  } catch (error) { ElMessage.error('加载用户详情失败'); }
};

const handleSubmit = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    submitLoading.value = true;
    try {
      if (isEdit.value) { await updateUser(props.userId, formData); ElMessage.success('更新成功'); }
      else { await createUser(formData); ElMessage.success('创建成功'); }
      dialogVisible.value = false;
      emit('success');
    } catch (error) { ElMessage.error(isEdit.value ? '更新失败' : '创建失败'); }
    finally { submitLoading.value = false; }
  });
};

const handleClosed = () => {
  formRef.value?.resetFields();
  Object.assign(formData, { username: '', full_name: '', email: '', password: '', role: 'client', is_active: true });
};

watch(() => props.userId, () => { if (props.userId && dialogVisible.value) loadUser(); });
</script>
