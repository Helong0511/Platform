<!--
  用户详情查看弹窗
  @file components/admin/UserDetailDialog.vue
-->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="viewingUser?.role === 'admin' ? '管理员详情' : '客户详情'"
    :width="isMobile ? '95%' : '700px'"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="resetApiKeyState"
  >
    <div v-if="viewingUser" class="user-detail">
      <el-descriptions :column="isMobile ? 1 : 2" border>
        <el-descriptions-item label="用户ID">{{ viewingUser.id }}</el-descriptions-item>
        <el-descriptions-item label="登录用户名">{{ viewingUser.username }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ viewingUser.email || '-' }}</el-descriptions-item>
        <el-descriptions-item label="全名">{{ viewingUser.full_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="角色">
          <el-tag :type="viewingUser.role === 'admin' ? 'primary' : 'success'">
            {{ viewingUser.role === 'admin' ? '管理员' : '客户' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="viewingUser.is_active ? 'success' : 'danger'">
            {{ viewingUser.is_active ? '启用' : '禁用' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间" :span="2">
          {{ formatDate(viewingUser.created_at) }}
        </el-descriptions-item>

        <template v-if="viewingUser.role === 'admin'">
          <el-descriptions-item label="最后更新" :span="2">
            {{ formatDate(viewingUser.updated_at) }}
          </el-descriptions-item>
        </template>

        <template v-if="viewingUser.role === 'client'">
          <el-divider content-position="left">客户信息</el-divider>
          <template v-if="viewingUser.client">
            <el-descriptions-item label="客户ID">{{ viewingUser.client.id }}</el-descriptions-item>
            <el-descriptions-item label="API密钥" :span="2">
              <template v-if="viewingUser.client.has_api_key">
                <span v-if="revealedApiKey" class="mono-key">{{ revealedApiKey }}</span>
                <span v-else class="text-muted">已配置（点击显示）</span>
                <el-button
                  link
                  type="primary"
                  :loading="apiKeyLoading"
                  style="margin-left: 8px"
                  @click="handleRevealApiKey"
                >
                  {{ revealedApiKey ? '重新加载' : '显示密钥' }}
                </el-button>
              </template>
              <span v-else class="text-muted">-</span>
            </el-descriptions-item>
            <el-descriptions-item label="客户状态">
              <el-tag :type="viewingUser.client.is_active ? 'success' : 'danger'" size="small">
                {{ viewingUser.client.is_active ? '启用' : '禁用' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="公司名称" :span="2">{{ viewingUser.client.company_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="联系人">{{ viewingUser.client.contact_person || '-' }}</el-descriptions-item>
            <el-descriptions-item label="联系电话">{{ viewingUser.client.phone || '-' }}</el-descriptions-item>
            <el-descriptions-item label="公司地址" :span="2">{{ viewingUser.client.address || '-' }}</el-descriptions-item>
          </template>
          <template v-else>
            <el-descriptions-item label="客户信息" :span="2">
              <el-tag type="warning" size="small">暂无客户信息</el-tag>
            </el-descriptions-item>
          </template>
        </template>
      </el-descriptions>
    </div>
    <template #footer>
      <div class="dialog-footer">
        <el-button type="primary" @click="emit('update:modelValue', false)">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getAdminClientApiKey } from '@/api/client';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  viewingUser: { type: Object, default: null },
  isMobile: { type: Boolean, default: false },
  formatDate: { type: Function, required: true },
});

const emit = defineEmits(['update:modelValue']);

const revealedApiKey = ref('');
const apiKeyLoading = ref(false);

const resetApiKeyState = () => {
  revealedApiKey.value = '';
  apiKeyLoading.value = false;
};

const handleRevealApiKey = async () => {
  const clientId = props.viewingUser?.client?.id;
  if (!clientId) return;
  apiKeyLoading.value = true;
  try {
    const data = await getAdminClientApiKey(clientId);
    revealedApiKey.value = data?.key || '';
    if (!revealedApiKey.value) {
      ElMessage.warning('未找到 API 密钥');
    }
  } catch {
    ElMessage.error('获取 API 密钥失败');
  } finally {
    apiKeyLoading.value = false;
  }
};
</script>

<style scoped>
.mono-key {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  word-break: break-all;
}
.text-muted {
  color: #909399;
}
</style>
