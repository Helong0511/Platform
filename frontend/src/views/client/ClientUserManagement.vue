<template>
  <div class="client-user-management-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1>用户管理</h1>
    </div>

    <!-- 修改密码卡片（仅当允许修改密码时显示） -->
    <el-card class="password-card" shadow="never" v-if="canChangePassword">
      <template #header>
        <div class="card-header">
          <el-icon :size="16"><Lock /></el-icon>
          <span>修改登录密码</span>
        </div>
      </template>
      <el-form 
        ref="passwordFormRef" 
        :model="passwordForm" 
        :rules="passwordRules" 
        label-width="120px"
      >
        <el-form-item label="当前密码" prop="oldPassword">
          <el-input 
            v-model="passwordForm.oldPassword" 
            type="password" 
            placeholder="请输入当前密码" 
            show-password 
            clearable
            style="max-width: 400px;"
          ></el-input>
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input 
            v-model="passwordForm.newPassword" 
            type="password" 
            placeholder="请输入新密码（至少6位）" 
            show-password 
            clearable
            style="max-width: 400px;"
          ></el-input>
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirmPassword">
          <el-input 
            v-model="passwordForm.confirmPassword" 
            type="password" 
            placeholder="请再次输入新密码" 
            show-password 
            clearable
            style="max-width: 400px;"
          ></el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleChangePassword" :loading="passwordLoading">
            修改密码
          </el-button>
          <el-button @click="resetPasswordForm">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 客户信息卡片 -->
    <el-card class="client-info-card" shadow="never" v-if="currentUser?.client">
      <template #header>
        <div class="card-header">
          <el-icon :size="16"><UserFilled /></el-icon>
          <span>客户信息</span>
        </div>
      </template>
      <div class="client-info-content">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="客户ID">
            {{ currentUser.client.id }}
          </el-descriptions-item>
          <el-descriptions-item label="API密钥">
            <span v-if="currentUser.client.key" style="font-family: monospace; font-size: 13px;">
              {{ currentUser.client.key }}
            </span>
            <span v-else style="color: #909399;">-</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <!-- 产品信息卡片 -->
    <el-card class="products-card" shadow="never">
      <template #header>
        <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <el-icon :size="16"><Box /></el-icon>
            <span>我的产品信息</span>
          </div>
          <el-button 
            type="text" 
            :icon="Setting" 
            @click="columnSettingVisible = true"
            size="small"
          >
            列设置
          </el-button>
        </div>
      </template>
      <div v-loading="productsLoading" class="products-content">
        <el-table
          :data="products"
          border
          stripe
          style="width: 100%"
          empty-text="暂无产品信息"
        >
          <el-table-column v-if="columnVisibility.id" prop="id" label="ID" width="80" align="center"></el-table-column>
          <el-table-column v-if="columnVisibility.name" prop="name" label="产品名称" min-width="200"></el-table-column>
          <el-table-column v-if="columnVisibility.created_at" prop="created_at" label="创建时间" width="180">
            <template #default="scope">
              {{ formatDate(scope.row.created_at) }}
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="300px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="id">ID</el-checkbox>
        <el-checkbox label="name" :disabled="true">产品名称（固定显示）</el-checkbox>
        <el-checkbox label="created_at">创建时间</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { 
  ElCard, ElForm, ElFormItem, ElInput, ElButton, ElTable, ElTableColumn, 
  ElTag, ElIcon, ElMessage, ElDescriptions, ElDescriptionsItem, ElDialog, ElCheckboxGroup, ElCheckbox
} from 'element-plus';
import { Lock, Box, UserFilled, Setting } from '@element-plus/icons-vue';
import { useAuthStore } from '../../store';
import { getProductList } from '../../api/product';
import { changePassword, getCurrentUserInfo } from '../../api/user';
import { formatDate } from '../../utils/dateFormat';
import { extractErrorMessage, isErrorHandled } from '../../utils/api';
import { ensureCsrfToken } from '../../utils/csrfMutate';
import { useClientUserManagementColumnVisibility } from '../../composables/useClientUserManagementColumnVisibility';

// Store
const authStore = useAuthStore();
const router = useRouter();
const currentUser = computed(() => authStore.userInfo);

// 计算属性：是否可以修改密码
const canChangePassword = computed(() => {
  // 检查用户信息中的 password_change_enabled 字段
  // 如果字段为 true 或 undefined（向后兼容），则允许修改
  // 如果字段明确为 false，则不允许修改
  if (currentUser.value?.password_change_enabled === false) {
    return false;
  }
  // 默认允许修改（向后兼容，如果字段不存在或为 true）
  return true;
});

// 密码表单
const passwordFormRef = ref(null);
const passwordLoading = ref(false);
const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
});

// 密码验证规则
const validateConfirmPassword = (rule, value, callback) => {
  if (value !== passwordForm.newPassword) {
    callback(new Error('两次输入的密码不一致'));
  } else {
    callback();
  }
};

const passwordRules = {
  oldPassword: [
    { required: true, message: '请输入当前密码', trigger: 'blur' }
  ],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于 6 个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' }
  ]
};

// 产品列表
const products = ref([]);
const productsLoading = ref(false);

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility
} = useClientUserManagementColumnVisibility();

// 重置密码表单
const resetPasswordForm = () => {
  passwordForm.oldPassword = '';
  passwordForm.newPassword = '';
  passwordForm.confirmPassword = '';
  if (passwordFormRef.value) {
    passwordFormRef.value.clearValidate();
  }
};

// 修改密码
const handleChangePassword = async () => {
  if (!passwordFormRef.value) return;

  try {
    // 确保CSRF令牌存在
    await ensureCsrfToken(() => getCurrentUserInfo());
    
    await passwordFormRef.value.validate();
    passwordLoading.value = true;

    await changePassword({
      old_password: passwordForm.oldPassword,
      new_password: passwordForm.newPassword
    });

    ElMessage.success('密码修改成功');
    resetPasswordForm();
  } catch (error) {
    if (!error.message?.includes('取消')) {
      if (!isErrorHandled(error)) {
        const errorMsg = extractErrorMessage(error);
        ElMessage.error(errorMsg);
      }
    }
  } finally {
    passwordLoading.value = false;
  }
};

// 获取客户信息
const fetchClientInfo = async () => {
  // 获取最新的用户信息，确保包含 password_change_enabled 字段
  try {
    const userData = await getCurrentUserInfo();
    if (userData) {
      // 更新 store 中的用户信息，包括 password_change_enabled
      authStore.userInfo = { 
        ...authStore.userInfo, 
        client: userData.client,
        password_change_enabled: userData.password_change_enabled
      };
    }
  } catch (error) {
    // 静默失败，继续使用现有信息
  }
};

// 获取产品列表
const fetchProducts = async () => {
  // 先确保客户信息已加载
  await fetchClientInfo();
  
  let clientId = currentUser.value?.client?.id;
  
  if (!clientId) {
    products.value = [];
    return;
  }

  try {
    productsLoading.value = true;
    const response = await getProductList({
      client_id: clientId,
      page_size: 100
    });
    products.value = response.data || [];
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
    products.value = [];
  } finally {
    productsLoading.value = false;
  }
};

// 初始化
onMounted(async () => {
  // 加载列显示设置
  loadColumnVisibility()
  // 路由守卫已经处理了认证检查，这里不需要重复检查
  // 延迟加载数据，让页面先渲染出来
  await nextTick();
  
  setTimeout(async () => {
    try {
      // 设置超时保护（20秒）
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => {
          reject(new Error('页面加载超时，请检查网络连接或刷新页面'));
        }, 20000);
      });
      
      await Promise.race([
        Promise.allSettled([fetchClientInfo(), fetchProducts()]),
        timeoutPromise
      ]);
    } catch (error) {
      // 超时或其他错误
      if (error.message && error.message.includes('超时')) {
        ElMessage.error(error.message);
        productsLoading.value = false;
      } else if (error.response?.status === 401) {
        // 401错误已在拦截器中处理
        productsLoading.value = false;
      } else {
        // 初始化失败时的错误处理
        if (!isErrorHandled(error)) {
          const errorMsg = extractErrorMessage(error);
          ElMessage.error(`页面初始化失败: ${errorMsg}`);
        }
        productsLoading.value = false;
      }
    }
  }, 0);
});
</script>

<style scoped>
.client-user-management-container {
  width: 100%;
  padding: 0;
}

.page-header {
  margin-bottom: var(--spacing-xl);
  padding: var(--spacing-xl);
  background-color: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.page-header h1 {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.password-card,
.client-info-card,
.products-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.password-card :deep(.el-card__body),
.client-info-card :deep(.el-card__body),
.products-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
}

.client-info-content {
  padding: var(--spacing-sm) 0;
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.card-header .el-icon {
  font-size: var(--font-size-lg);
}

.products-content {
  padding: var(--spacing-sm) 0;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .client-user-management-container {
    padding: var(--spacing-md);
  }
  
  .page-header {
    padding: var(--spacing-md);
    margin-bottom: var(--spacing-md);
  }
  
  .page-header h1 {
    font-size: var(--font-size-xl);
  }
  
  .password-card,
  .client-info-card,
  .products-card {
    margin-bottom: var(--spacing-md);
  }
  
  .password-card :deep(.el-card__body),
  .client-info-card :deep(.el-card__body),
  .products-card :deep(.el-card__body) {
    padding: var(--spacing-md);
  }
  
  .card-header {
    font-size: var(--font-size-base);
  }
  
  /* 表单移动端优化 */
  .el-form :deep(.el-form-item__label) {
    width: 100px !important;
  }
  
  .el-form :deep(.el-form-item__content) {
    width: 100% !important;
  }
  
  .el-form :deep(.el-input) {
    max-width: 100% !important;
    width: 100% !important;
  }
  
  .el-form :deep(.el-input__wrapper) {
    min-height: var(--touch-target-size);
  }
  
  .el-form :deep(.el-form-item:last-child) {
    display: flex;
    flex-direction: row;
    gap: var(--spacing-sm);
  }
  
  .el-form :deep(.el-form-item:last-child .el-button) {
    flex: 1;
    min-height: var(--touch-target-size);
  }
  
  /* 表格移动端优化 */
  .products-content {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .el-table {
    font-size: var(--font-size-sm);
    min-width: 600px;
  }
  
  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-xs) var(--spacing-sm);
    word-break: break-word;
  }
  
  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
  }
  
  /* 描述列表移动端优化 */
  .el-descriptions :deep(.el-descriptions__label) {
    width: 100px !important;
  }
  
  .el-descriptions :deep(.el-descriptions__content) {
    word-break: break-word;
  }
}
</style>

