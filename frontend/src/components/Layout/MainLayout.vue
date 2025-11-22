<template>
  <el-container class="main-container">
    <!-- 桌面端侧边栏 -->
    <el-aside width="200px" class="sidebar desktop-sidebar" v-if="isAuthenticated">
      <Sidebar />
    </el-aside>
    
    <!-- 移动端/平板端抽屉菜单 -->
    <el-drawer
      v-model="drawerVisible"
      :with-header="false"
      direction="ltr"
      :size="isTablet ? '320px' : '280px'"
      class="mobile-drawer"
      :z-index="1080"
    >
      <Sidebar @menu-click="handleMenuClick" />
    </el-drawer>
    
    <el-container>
      <el-header class="header">
        <div class="header-content">
          <div class="header-left">
            <el-button 
              @click="toggleSidebar" 
              class="menu-icon" 
              :icon="Menu"
              text
              circle
            ></el-button>
            <h1 class="header-title">广告数据平台</h1>
          </div>
          <div class="header-right">
            <!-- 用户信息 -->
            <div class="user-info">
              <el-icon class="user-icon"><User /></el-icon>
              <span class="username">{{ userDisplayName }}</span>
              <el-tag v-if="authStore.isAdmin" type="success" size="small" class="role-tag">管理员</el-tag>
            </div>
            <!-- 退出登录按钮 -->
            <el-button 
              type="danger" 
              size="small" 
              @click="handleLogout"
              :icon="SwitchButton"
              class="logout-btn"
            >
              <span class="logout-text">退出登录</span>
            </el-button>
          </div>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../../store';
import { useDevice } from '../../composables/useDevice';
import { ElContainer, ElAside, ElHeader, ElMain, ElIcon, ElButton, ElTag, ElMessageBox, ElDrawer } from 'element-plus';
import { Menu, User, SwitchButton } from '@element-plus/icons-vue';
import Sidebar from './Sidebar.vue';

const router = useRouter();
const authStore = useAuthStore();
const { deviceType, isDesktop, isTablet, isMobile } = useDevice();
const isAuthenticated = computed(() => authStore.isAuthenticated);
const isSidebarOpen = ref(true);
const drawerVisible = ref(false);

// 用户显示名称（优先显示全名，否则显示用户名）
const userDisplayName = computed(() => {
  const userInfo = authStore.userInfo;
  return userInfo?.full_name || userInfo?.username || '用户';
});

// 切换侧边栏/抽屉
const toggleSidebar = () => {
  if (isMobile.value || isTablet.value) {
    drawerVisible.value = !drawerVisible.value;
  } else {
    isSidebarOpen.value = !isSidebarOpen.value;
  }
};

// 处理菜单点击（移动端/平板端点击后关闭抽屉）
const handleMenuClick = () => {
  if (isMobile.value || isTablet.value) {
    drawerVisible.value = false;
  }
};

// 处理退出登录
const handleLogout = async () => {
  try {
    // 确认对话框
    await ElMessageBox.confirm(
      '确定要退出登录吗？',
      '提示',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    );
    
    // 执行退出登录
    authStore.logout();
  } catch {
    // 用户取消操作，不执行任何操作
  }
};

// useDevice composable 已经处理了窗口大小变化监听
</script>

<style scoped>
.main-container {
  height: 100vh;
}

.sidebar {
  background-color: var(--bg-dark);
  color: var(--text-white);
  transition: width var(--transition-base);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  width: var(--sidebar-width);
}

/* 桌面端侧边栏 */
.desktop-sidebar {
  display: flex;
}

/* 平板端和移动端隐藏侧边栏 */
@media (max-width: 1024px) {
  .desktop-sidebar {
    display: none;
  }
}

/* 移动端抽屉样式 */
.mobile-drawer :deep(.el-drawer__body) {
  padding: 0;
  background-color: var(--bg-dark);
}

.header {
  background-color: var(--bg-primary);
  border-bottom: 1px solid var(--border-lighter);
  padding: 0 var(--spacing-xl);
  height: var(--header-height);
  box-shadow: var(--shadow-light);
  position: sticky;
  top: 0;
  z-index: var(--z-index-fixed);
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
  width: 100%;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  flex: 1;
  min-width: 0; /* 允许flex子元素收缩 */
}

.menu-icon {
  font-size: var(--font-size-xl);
  cursor: pointer;
  color: var(--text-primary);
  transition: var(--transition-base);
  flex-shrink: 0;
  min-width: var(--touch-target-size);
  min-height: var(--touch-target-size);
  display: flex;
  align-items: center;
  justify-content: center;
}

.menu-icon:hover {
  color: var(--primary-color);
}

.menu-icon:active {
  opacity: 0.7;
}

.header-title {
  margin: 0;
  font-size: var(--font-size-xxl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  flex-shrink: 0;
}

.user-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  background-color: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-lighter);
}

.user-icon {
  font-size: var(--font-size-lg);
  color: var(--primary-color);
  flex-shrink: 0;
}

.username {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100px;
}

.role-tag {
  margin-left: var(--spacing-xs);
  flex-shrink: 0;
}

.logout-btn {
  border-radius: var(--radius-md);
  font-weight: var(--font-weight-medium);
  min-height: var(--touch-target-size);
}

.logout-text {
  white-space: nowrap;
}

.main-content {
  padding: var(--content-padding);
  overflow-y: auto;
  background-color: var(--bg-page);
  min-height: calc(100vh - var(--header-height));
  -webkit-overflow-scrolling: touch; /* iOS平滑滚动 */
}

/* 平板端优化 */
@media (min-width: 768px) and (max-width: 1024px) {
  .header {
    padding: 0 var(--spacing-lg);
  }
  
  .header-title {
    font-size: var(--font-size-xl);
  }
  
  .user-info {
    padding: var(--spacing-sm) var(--spacing-lg);
  }
  
  .username {
    max-width: 120px;
  }
  
  .main-content {
    padding: var(--spacing-lg);
  }
}

/* 移动端优化 */
@media (max-width: 767px) {
  .header {
    padding: 0 var(--spacing-md);
  }
  
  .header-left {
    gap: var(--spacing-md);
  }
  
  .header-title {
    font-size: var(--font-size-lg);
  }
  
  .header-right {
    gap: var(--spacing-sm);
  }
  
  .user-info {
    padding: var(--spacing-xs) var(--spacing-md);
    gap: var(--spacing-xs);
  }
  
  .username {
    display: none; /* 移动端隐藏用户名文字 */
    max-width: 60px;
    font-size: var(--font-size-xs);
  }
  
  .logout-text {
    display: none; /* 移动端只显示图标 */
  }
  
  .logout-btn {
    padding: var(--spacing-sm);
    min-width: var(--touch-target-size);
  }
  
  .main-content {
    padding: var(--mobile-content-padding);
  }
}

@media (max-width: 480px) {
  .header {
    padding: 0 var(--spacing-sm);
  }
  
  .header-title {
    font-size: var(--font-size-base);
  }
  
  .role-tag {
    display: none; /* 小屏幕隐藏角色标签 */
  }
}
</style>