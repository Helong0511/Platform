<!--
  管理端 - 在线会话管理
  @file views/admin/SessionManagement.vue
-->
<template>
  <!-- 页面主模板 -->
  <div class="session-management-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1>会话管理</h1>
        <div class="stats-info" v-if="activeTab === 'sessions'">
          <span class="stat-item">
            <span class="stat-label">活跃会话：</span>
            <span class="stat-value">{{ sessionsTotal || 0 }}</span>
          </span>
        </div>
        <div class="stats-info" v-if="activeTab === 'blacklist' && isAdmin">
          <span class="stat-item">
            <span class="stat-label">黑名单记录：</span>
            <span class="stat-value">{{ blacklistTotal || 0 }}</span>
          </span>
        </div>
      </div>
    </div>

    <!-- 标签页切换 -->
    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <!-- 会话列表标签页 -->
      <el-tab-pane label="我的会话" name="sessions">
        <!-- 筛选控件 -->
        <!-- 筛选区 -->
        <el-card class="filter-card" shadow="never">
          <!-- 表单区域 -->
          <el-form :inline="true" class="filter-form">
            <el-form-item>
              <el-button type="primary" @click="fetchSessions" :loading="loading" :icon="Refresh">
                刷新
              </el-button>
              <el-button 
                type="warning" 
                @click="handleRevokeAllSessions" 
                :loading="revokingAll"
                :disabled="sessionsTotal <= 1 || loading"
                :icon="Delete"
              >
                撤销所有其他会话
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 会话数据表格 -->
        <el-card class="data-table-card" shadow="never">
          <!-- 卡片标题栏 -->
    <template #header>
            <div class="table-header">
              <span>会话列表</span>
              <el-button 
                type="link" 
                :icon="Setting" 
                @click="columnSettingVisible = true"
                style="float: right;"
              >
                列设置
              </el-button>
            </div>
          </template>
          <el-table
            v-loading="loading"
            :data="sessions"
            border
            stripe
            style="width: 100%"
            empty-text="暂无会话数据"
          >
            <el-table-column prop="id" label="ID" width="80" align="center" />
            <el-table-column prop="ip_address" label="IP地址" width="150" show-overflow-tooltip>
              <template #default="scope">
                {{ scope.row.ip_address || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="device_info" label="设备信息" min-width="150" show-overflow-tooltip>
              <template #default="scope">
                {{ scope.row.device_info || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="user_agent" label="用户代理" min-width="200" show-overflow-tooltip>
              <template #default="scope">
                {{ scope.row.user_agent || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="location" label="位置" min-width="150" show-overflow-tooltip>
              <template #default="scope">
                {{ scope.row.location || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="is_active" label="状态" width="100" align="center">
              <template #default="scope">
                <el-tag :type="scope.row.is_active ? 'success' : 'danger'" size="small">
                  {{ scope.row.is_active ? '活跃' : '已撤销' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="登录时间" width="180">
              <template #default="scope">
                {{ formatDate(scope.row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column prop="last_activity" label="最后活动" width="180">
              <template #default="scope">
                {{ formatDate(scope.row.last_activity) }}
              </template>
            </el-table-column>
            <el-table-column prop="expires_at" label="过期时间" width="180">
              <template #default="scope">
                {{ formatDate(scope.row.expires_at) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="scope">
                <el-button 
                  v-if="scope.row.is_active"
                  size="small" 
                  type="danger" 
                  :icon="Delete"
                  @click="handleRevokeSession(scope.row)"
                  :loading="scope.row._revoking"
                >
                  撤销
                </el-button>
                <span v-else class="text-muted">已撤销</span>
              </template>
            </el-table-column>
          </el-table>

          <!-- 分页 -->
          <div class="pagination-container">
            <el-pagination
              v-model:current-page="sessionsPage"
              v-model:page-size="sessionsPageSize"
              :page-sizes="[10, 20, 50, 100]"
              :total="sessionsTotal"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="handleSessionsSizeChange"
              @current-change="handleSessionsPageChange"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <!-- 黑名单列表标签页（仅管理员） -->
      <el-tab-pane v-if="isAdmin" label="Token黑名单" name="blacklist">
        <!-- 筛选控件 -->
        <el-card class="filter-card" shadow="never">
          <el-form :inline="true" :model="blacklistSearchForm" class="filter-form">
            <el-form-item label="用户ID">
              <el-input 
                v-model.number="blacklistSearchForm.user_id" 
                placeholder="输入用户ID筛选" 
                clearable
                @keyup.enter="fetchBlacklist"
                style="width: 200px;"
                :prefix-icon="Search"
                type="number"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="fetchBlacklist" :loading="blacklistLoading" :icon="Search">
                查询
              </el-button>
              <el-button @click="resetBlacklistFilter" :icon="Refresh">
                重置
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 黑名单数据表格 -->
        <el-card class="data-table-card" shadow="never">
          <template #header>
            <div class="table-header">
              <span>黑名单列表</span>
            </div>
          </template>
          <el-table
            v-loading="blacklistLoading"
            :data="blacklist"
            border
            stripe
            style="width: 100%"
            empty-text="暂无黑名单记录"
          >
            <el-table-column prop="id" label="ID" width="80" align="center" />
            <el-table-column prop="user_id" label="用户ID" width="100" align="center" />
            <el-table-column prop="username" label="用户名" min-width="120" show-overflow-tooltip>
              <template #default="scope">
                {{ scope.row.username || `用户${scope.row.user_id}` }}
              </template>
            </el-table-column>
            <el-table-column prop="token_jti" label="Token JTI" min-width="200" show-overflow-tooltip>
              <template #default="scope">
                <span style="max-width: 200px; display: inline-block;">
                  {{ scope.row.token_jti }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="reason" label="撤销原因" min-width="200" show-overflow-tooltip>
              <template #default="scope">
                {{ scope.row.reason || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="revoked_at" label="撤销时间" width="180">
              <template #default="scope">
                {{ formatDate(scope.row.revoked_at) }}
              </template>
            </el-table-column>
            <el-table-column prop="expires_at" label="过期时间" width="180">
              <template #default="scope">
                {{ formatDate(scope.row.expires_at) }}
              </template>
            </el-table-column>
          </el-table>

          <!-- 分页 -->
          <div class="pagination-container">
            <el-pagination
              v-model:current-page="blacklistPage"
              v-model:page-size="blacklistPageSize"
              :page-sizes="[10, 20, 50, 100]"
              :total="blacklistTotal"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="handleBlacklistSizeChange"
              @current-change="handleBlacklistPageChange"
            />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="id" :disabled="true">ID（固定显示）</el-checkbox>
        <el-checkbox label="ip_address">IP地址</el-checkbox>
        <el-checkbox label="device_info">设备信息</el-checkbox>
        <el-checkbox label="user_agent">用户代理</el-checkbox>
        <el-checkbox label="location">位置</el-checkbox>
        <el-checkbox label="is_active">状态</el-checkbox>
        <el-checkbox label="created_at" :disabled="true">登录时间（固定显示）</el-checkbox>
        <el-checkbox label="last_activity">最后活动</el-checkbox>
        <el-checkbox label="expires_at">过期时间</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue';
import { useSessionManagementColumnVisibility } from '../../composables/useSessionManagementColumnVisibility';
import { ElMessage, ElMessageBox, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus';
import { Search, Refresh, Delete, Setting } from '@element-plus/icons-vue';
import { 
  getMySessions, 
  revokeMySession, 
  revokeAllMySessions,
  getBlacklist 
} from '@/api/session';
import { useAuthStore } from '@/store';
import { formatDate } from '@/utils/date';
import { logger } from '@/utils/logger';

// 认证store
const authStore = useAuthStore();
const isAdmin = computed(() => authStore.isAdmin);

// 标签页
const activeTab = ref('sessions');

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility
} = useSessionManagementColumnVisibility();

// 会话相关
const loading = ref(false);
const revokingAll = ref(false);
const sessions = ref([]);
const sessionsPage = ref(1);
const sessionsPageSize = ref(10);
const sessionsTotal = ref(0);

// 黑名单相关
const blacklistLoading = ref(false);
const blacklist = ref([]);
const blacklistPage = ref(1);
const blacklistPageSize = ref(10);
const blacklistTotal = ref(0);
const blacklistSearchForm = ref({
  user_id: null
});

// 标签页切换
const handleTabChange = (tabName) => {
  if (tabName === 'sessions') {
    fetchSessions();
  } else if (tabName === 'blacklist' && isAdmin.value) {
    fetchBlacklist();
  }
};

// 获取会话列表
const fetchSessions = async () => {
  loading.value = true;
  try {
    const result = await getMySessions({
      page: sessionsPage.value,
      page_size: sessionsPageSize.value
    });
    sessions.value = result.data || [];
    sessionsTotal.value = result.total || 0;
  } catch (error) {
    ElMessage.error('获取会话列表失败');
  } finally {
    loading.value = false;
  }
};

// 撤销指定会话
const handleRevokeSession = async (session) => {
  try {
    await ElMessageBox.confirm(
      `确定要撤销此会话吗？\nIP地址: ${session.ip_address || '-'}\n设备: ${session.device_info || '-'}`,
      '确认撤销',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );

    session._revoking = true;
    await revokeMySession(session.id);
    ElMessage.success('会话已撤销');
    await fetchSessions();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('撤销会话失败');
    }
  } finally {
    session._revoking = false;
  }
};

// 撤销所有其他会话
const handleRevokeAllSessions = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要撤销所有其他会话吗？当前会话将保留。',
      '确认撤销',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );

    revokingAll.value = true;
    const result = await revokeAllMySessions();
    ElMessage.success(result?.message || `已撤销 ${result?.revoked_count ?? 0} 个会话`);
    await fetchSessions();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('撤销会话失败');
    }
  } finally {
    revokingAll.value = false;
  }
};

// 会话分页
const handleSessionsPageChange = (page) => {
  sessionsPage.value = page;
  fetchSessions();
};

const handleSessionsSizeChange = (size) => {
  sessionsPageSize.value = size;
  sessionsPage.value = 1;
  fetchSessions();
};

// 获取黑名单列表
const fetchBlacklist = async () => {
  if (!isAdmin.value) {
    return;
  }

  blacklistLoading.value = true;
  try {
    const params = {
      page: blacklistPage.value,
      page_size: blacklistPageSize.value
    };
    
    if (blacklistSearchForm.value.user_id) {
      params.user_id = blacklistSearchForm.value.user_id;
    }

    const result = await getBlacklist(params);
    blacklist.value = result.data || [];
    blacklistTotal.value = result.total || 0;
  } catch (error) {
    ElMessage.error('获取黑名单列表失败');
  } finally {
    blacklistLoading.value = false;
  }
};

// 重置黑名单筛选
const resetBlacklistFilter = () => {
  blacklistSearchForm.value.user_id = null;
  blacklistPage.value = 1;
  fetchBlacklist();
};

// 黑名单分页
const handleBlacklistPageChange = (page) => {
  blacklistPage.value = page;
  fetchBlacklist();
};

const handleBlacklistSizeChange = (size) => {
  blacklistPageSize.value = size;
  blacklistPage.value = 1;
  fetchBlacklist();
};

// 初始化
onMounted(() => {
  // 加载列显示设置
  loadColumnVisibility()
  fetchSessions();
});
</script>

<style scoped>
.session-management-container {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-left h1 {
  margin: 0 0 10px 0;
  font-size: 24px;
  font-weight: 600;
}

.stats-info {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.stat-item {
  font-size: 14px;
}

.stat-label {
  color: #666;
}

.stat-value {
  font-weight: 600;
  color: #333;
}

.stat-value.success {
  color: #67c23a;
}

.stat-value.danger {
  color: #f56c6c;
}

.filter-card {
  margin-bottom: 20px;
}

.filter-form {
  margin: 0;
}

.data-table-card {
  margin-bottom: 20px;
}

.table-header {
  font-weight: 600;
  font-size: 16px;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.text-muted {
  color: #909399;
  font-size: 14px;
}

:deep(.el-tabs__header) {
  margin-bottom: 20px;
}
</style>

