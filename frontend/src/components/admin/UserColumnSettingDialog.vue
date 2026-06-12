<!--
  用户列表列显示设置弹窗
  @file components/admin/UserColumnSettingDialog.vue
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="列显示设置"
    width="400px"
    @update:model-value="emit('update:modelValue', $event)"
    @close="emit('save')"
  >
    <el-checkbox-group :model-value="columnVisibilityArray" @update:model-value="emit('update:columnVisibilityArray', $event)">
      <el-checkbox label="id" :disabled="true">ID（固定显示）</el-checkbox>
      <el-checkbox label="username" :disabled="true">登录用户名（固定显示）</el-checkbox>
      <el-checkbox label="full_name">全名</el-checkbox>
      <el-checkbox label="role">角色</el-checkbox>
      <el-checkbox label="email">邮箱</el-checkbox>
      <el-checkbox v-if="hasClientUsers" label="company_name">公司名称</el-checkbox>
      <el-checkbox v-if="hasClientUsers" label="contact_person">联系人</el-checkbox>
      <el-checkbox label="is_active">状态</el-checkbox>
      <el-checkbox v-if="hasClientUsers" label="api_enabled">API访问</el-checkbox>
      <el-checkbox v-if="hasClientUsers" label="password_change_enabled">允许修改密码</el-checkbox>
      <el-checkbox label="created_at">创建时间</el-checkbox>
    </el-checkbox-group>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="onConfirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, default: false },
  columnVisibilityArray: { type: Array, default: () => [] },
  hasClientUsers: { type: Boolean, default: false },
});

const emit = defineEmits(['update:modelValue', 'update:columnVisibilityArray', 'save']);

function onConfirm() {
  emit('save');
  emit('update:modelValue', false);
}
</script>
