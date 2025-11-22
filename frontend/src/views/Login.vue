<template>
  <div class="login-container">
    
    <div class="login-card">
      <div class="login-title">广告数据管理</div>
      <el-form ref="loginFormRef" :model="loginForm" :rules="rules" class="login-form" @submit.prevent="handleLogin" :validate-on-rule-change="false">
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            size="large"
            clearable
          ></el-input>
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            size="large"
            show-password
            clearable
          ></el-input>
        </el-form-item>
        <el-form-item class="login-actions">
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="authStore.loading"
            :disabled="authStore.loading"
            native-type="submit"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>
      <div class="login-footer">
        <span>© 2025 广告数据管理</span>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, onBeforeUnmount, onMounted, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../store';
import { ElForm, ElFormItem, ElInput, ElButton, ElMessage } from 'element-plus';
import { User, Lock } from '@element-plus/icons-vue';

// 路由实例
const router = useRouter();
// 认证Store
const authStore = useAuthStore();
// 表单引用
const loginFormRef = ref(null);
// 提交状态（防止重复提交）
const isSubmitting = ref(false);
// 组件挂载状态
const isMounted = ref(false);
// 表单数据
const loginForm = reactive({
  username: '',
  password: ''
});

// 表单验证规则
const rules = reactive({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        // 使用 try-catch 确保错误被正确捕获
        try {
          if (!value || typeof value !== 'string') {
            callback(new Error('请输入用户名'));
            return;
          }
          const trimmedValue = value.trim();
          if (trimmedValue.length < 3) {
            callback(new Error('用户名长度至少需要 3 个字符'));
          } else if (trimmedValue.length > 20) {
            callback(new Error('用户名长度不能超过 20 个字符'));
          } else {
            callback();
          }
        } catch (error) {
          // 如果发生错误，调用 callback 但不传递错误，避免 ElOnlyChild 问题
          callback();
        }
      },
      trigger: 'blur'
    }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        // 使用 try-catch 确保错误被正确捕获
        try {
          if (!value || typeof value !== 'string') {
            callback(new Error('请输入密码'));
            return;
          }
          if (value.length < 6) {
            callback(new Error('密码长度至少需要 6 个字符'));
          } else if (value.length > 32) {
            callback(new Error('密码长度不能超过 32 个字符'));
          } else {
            callback();
          }
        } catch (error) {
          // 如果发生错误，调用 callback 但不传递错误，避免 ElOnlyChild 问题
          callback();
        }
      },
      trigger: 'blur'
    }
  ]
});

// 处理登录（防止重复提交）
const handleLogin = async () => {
  // 防止重复提交
  if (isSubmitting.value || authStore.loading) {
    return;
  }
  
  // 检查组件是否仍然挂载
  if (!isMounted.value || !loginFormRef.value) {
    return;
  }
  
  try {
    // 立即设置提交状态，防止重复点击
    isSubmitting.value = true;
    
    // 等待 DOM 更新完成
    await nextTick();
    
    // 再次检查组件是否仍然挂载
    if (!isMounted.value || !loginFormRef.value) {
      return;
    }
    
    // 验证表单（validate 会自动触发所有验证规则）
    await loginFormRef.value.validate();
    
    // 验证成功，调用登录方法
    // 注意：登录成功后的跳转由 store 中的 login 方法处理（跳转到 /app/dashboard）
    const loginSuccess = await authStore.login(loginForm);
    
    // 如果登录成功，立即清除表单验证状态并重置表单，避免在页面跳转时出现验证错误
    if (loginSuccess && isMounted.value && loginFormRef.value) {
      try {
        // 使用 nextTick 确保在清除验证前 DOM 已更新
        await nextTick();
        // 再次检查组件是否仍然挂载
        if (isMounted.value && loginFormRef.value) {
          loginFormRef.value.clearValidate();
          // 重置表单数据
          loginForm.username = '';
          loginForm.password = '';
        }
      } catch (e) {
        // 忽略清除验证时的错误（可能组件已卸载）
      }
    }
  } catch (error) {
    // 验证失败或登录失败
    // Element Plus 的 validate 方法在验证失败时会抛出错误对象
    // 错误对象的格式是 { fieldName: [errorMessage] }
    // 这是正常的行为，Element Plus 会自动显示错误消息
    // 我们只需要确保错误被正确处理，不阻止后续操作
    
    // 忽略 ElOnlyChild 错误（这是 Element Plus 的内部错误，不影响功能）
    if (error && error.message && typeof error.message === 'string' && error.message.includes('ElOnlyChild')) {
      // 静默忽略这个错误
      return;
    }
    
    if (error && typeof error === 'object') {
      // 如果是表单验证错误（没有 response 属性），Element Plus 会自动处理
      // 如果是 API 错误（有 response 属性），store 中已经显示了错误消息
      if (error.response) {
        // API 错误已在 store 中处理
        // 清除表单验证状态，避免显示验证错误
        if (loginFormRef.value) {
          try {
            await nextTick();
            loginFormRef.value.clearValidate();
          } catch (e) {
            // 忽略清除验证时的错误
          }
        }
      }
      // 表单验证错误由 Element Plus 自动显示，不需要额外处理
    }
  } finally {
    // 重置提交状态
    isSubmitting.value = false;
  }
};

// 全局错误处理器，捕获并忽略 ElOnlyChild 错误
const handleGlobalError = (event) => {
  // 忽略 Element Plus 的 ElOnlyChild 错误
  const errorMessage = event?.message || event?.error?.message || '';
  if (typeof errorMessage === 'string' && errorMessage.includes('ElOnlyChild')) {
    event.preventDefault();
    event.stopPropagation();
    return true;
  }
  return false;
};

const handleUnhandledRejection = (event) => {
  // 处理未捕获的 Promise 拒绝
  const errorMessage = event?.reason?.message || event?.reason?.error?.message || '';
  if (typeof errorMessage === 'string' && errorMessage.includes('ElOnlyChild')) {
    event.preventDefault();
    return true;
  }
  return false;
};

// 组件挂载时设置错误处理器
onMounted(() => {
  isMounted.value = true;
  window.addEventListener('error', handleGlobalError, true);
  window.addEventListener('unhandledrejection', handleUnhandledRejection, true);
});

// 组件卸载前清理
onBeforeUnmount(() => {
  // 立即标记为未挂载，防止后续操作
  isMounted.value = false;
  
  // 移除事件监听器
  window.removeEventListener('error', handleGlobalError, true);
  window.removeEventListener('unhandledrejection', handleUnhandledRejection, true);
  
  // 清除表单验证状态
  if (loginFormRef.value) {
    try {
      loginFormRef.value.clearValidate();
    } catch (e) {
      // 忽略错误
    }
  }
});
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, var(--primary-color) 0%, #764ba2 100%);
  padding: var(--spacing-xl);
}

.login-card {
  width: 100%;
  max-width: 420px;
  background-color: var(--bg-primary);
  border-radius: var(--radius-xxl);
  box-shadow: var(--shadow-dark);
  overflow: hidden;
  padding: var(--spacing-xxxxl);
  animation: slideUp 0.5s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.login-title {
  text-align: center;
  margin-bottom: var(--spacing-xxxl);
  font-size: var(--font-size-large-title);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
}

.login-form {
  padding: 0;
}

.login-form :deep(.el-form-item) {
  margin-bottom: var(--spacing-xl);
}

.login-form :deep(.el-input) {
  height: 48px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-base);
  transition: var(--transition-base);
}

.login-form :deep(.el-input:focus-within) {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px var(--primary-light);
}

.login-actions {
  margin-top: var(--spacing-xl);
}

.login-btn {
  width: 100%;
  border-radius: var(--radius-lg);
  border: none;
  height: 48px;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  background-color: var(--primary-color);
  color: var(--text-white);
  cursor: pointer;
  transition: var(--transition-base);
  box-shadow: var(--shadow-light);
}

.login-btn:hover {
  background-color: var(--primary-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-medium);
}

.login-btn:active {
  transform: translateY(0);
}

.login-footer {
  text-align: center;
  padding: var(--spacing-lg);
  margin-top: var(--spacing-xl);
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-lighter);
  border-radius: 0 0 var(--radius-xxl) var(--radius-xxl);
}

/* 移动端优化 */
@media (max-width: 767px) {
  .login-container {
    padding: var(--spacing-md);
    align-items: flex-start;
    padding-top: 20vh;
  }
  
  .login-card {
    max-width: 100%;
    padding: var(--spacing-xl);
    border-radius: var(--radius-lg);
  }
  
  .login-title {
    font-size: var(--font-size-xxl);
    margin-bottom: var(--spacing-xl);
  }
  
  .login-form :deep(.el-form-item) {
    margin-bottom: var(--spacing-lg);
  }
  
  .login-form :deep(.el-input) {
    height: var(--touch-target-size);
    font-size: var(--font-size-base);
  }
  
  .login-form :deep(.el-input__wrapper) {
    min-height: var(--touch-target-size);
  }
  
  .login-btn {
    height: var(--touch-target-size);
    font-size: var(--font-size-base);
  }
  
  .login-footer {
    padding: var(--spacing-md);
    margin-top: var(--spacing-lg);
    font-size: var(--font-size-xs);
  }
}
</style>