<!--
  主布局：顶栏、侧边栏与内容区
  @file components/Layout/MainLayout.vue
-->
<template>
  <!-- 页面主模板 -->
<el-container class="main-container">
    <!-- 桌面端侧边栏 -->
    <el-aside width="200px" class="sidebar desktop-sidebar" v-if="isAuthenticated && isDesktop">
      <Sidebar />
    </el-aside>
    
    <!-- 移动端/平板端抽屉菜单 -->
    <el-drawer
      v-model="drawerVisible"
      :with-header="false"
      direction="ltr"
      :size="isTablet ? '320px' : '85%'"
      class="mobile-drawer"
      :z-index="1080"
      :modal="true"
      :close-on-click-modal="true"
      :close-on-press-escape="true"
      :show-close="false"
    >
      <div class="drawer-header">
        <h3 class="drawer-title">菜单</h3>
        <el-button
          @click="drawerVisible = false"
          :icon="Close"
          text
          circle
          class="drawer-close-btn"
          aria-label="关闭菜单"
        ></el-button>
      </div>
      <div class="drawer-menu-scroll">
        <Sidebar
          v-if="drawerVisible"
          :key="drawerMenuKey"
          in-drawer
          @menu-click="handleMenuClick"
        />
      </div>
    </el-drawer>
    
    <el-container>
      <el-header class="header">
        <div class="header-content">
          <!-- 菜单按钮独立于 header-left，避免 flex 压缩 + overflow 裁切 -->
          <el-button
            @click="toggleSidebar"
            class="menu-trigger"
            type="primary"
            aria-label="打开导航菜单"
            title="打开导航菜单"
          >
            <el-icon class="menu-trigger-icon"><Menu /></el-icon>
            <span class="menu-trigger-label">菜单</span>
          </el-button>
          <div class="header-left">
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
        <div v-if="routeNavigating" class="route-progress-bar" aria-hidden="true"></div>
        <router-view v-slot="{ Component, route: viewRoute }">
          <keep-alive :max="20">
            <component :is="Component" :key="viewRoute.fullPath" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue';
import { useRoute } from 'vue-router';
import { useAuthStore } from '../../store';
import { useDevice } from '../../composables/useDevice';
import { disableDoubleTapZoom, useViewportHeight } from '../../composables/useMobileTouch';
import { detectIOS } from '../../composables/useDevice';
import { routeNavigating } from '../../composables/useRouteLoading';
import { ElContainer, ElAside, ElHeader, ElMain, ElIcon, ElButton, ElTag, ElMessageBox, ElDrawer } from 'element-plus';
import { Menu, User, SwitchButton, Close } from '@element-plus/icons-vue';
import Sidebar from './Sidebar.vue';

const route = useRoute();
const authStore = useAuthStore();
const { isDesktop, isTablet, isMobile, isMobileOrTablet } = useDevice();
useViewportHeight();
const isAuthenticated = computed(() => authStore.isAuthenticated);
const drawerVisible = ref(false);
const drawerOpenSeq = ref(0);

// 每次打开 drawer 强制 remount 菜单，确保 default-openeds 与当前路由一致（iOS 尤其需要）
const drawerMenuKey = computed(() => `${route.path}-${drawerOpenSeq.value}`);

watch(drawerVisible, (open) => {
  if (open) {
    drawerOpenSeq.value += 1;
  }
});

// iOS / 移动端：抽屉打开时锁定背景滚动（Safari 下 Element Plus lock-scroll 常失效）
let lockedScrollY = 0;
watch(drawerVisible, async (open) => {
  if (!isMobileOrTablet.value) return;

  if (open) {
    lockedScrollY = window.scrollY;
    document.body.classList.add('drawer-open-scroll-lock');
    document.body.style.top = `-${lockedScrollY}px`;
    await nextTick();
    setTimeout(() => {
      document.querySelector('.drawer-menu-scroll .el-menu-item.is-active')
        ?.scrollIntoView({ block: 'center' });
    }, 120);
  } else {
    document.body.classList.remove('drawer-open-scroll-lock');
    document.body.style.top = '';
    window.scrollTo(0, lockedScrollY);
  }
});

// 用户显示名称（优先显示全名，否则显示用户名）
const userDisplayName = computed(() => {
  const userInfo = authStore.userInfo;
  return userInfo?.full_name || userInfo?.username || '用户';
});

// 切换抽屉菜单（仅移动端/平板端）
const toggleSidebar = () => {
  drawerVisible.value = !drawerVisible.value;
};

// 处理叶子菜单项点击（移动端/平板端点击后关闭抽屉）
const handleMenuClick = () => {
  drawerVisible.value = false;
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
        appendTo: document.body, // 确保弹窗附加到 body，避免被对话框遮挡
        zIndex: 3001 // 确保 z-index 高于对话框
      }
    );

    // 执行退出登录
    authStore.logout();
  } catch {
    // 用户取消操作，不执行任何操作
  }
};

// ====== 移动端边缘滑动手势：左边缘右滑打开抽屉，左滑关闭 ======
const EDGE_SWIPE_THRESHOLD = 50;   // 滑动距离阈值（px）
const EDGE_DETECT_WIDTH = 30;      // 左边缘检测区域宽度（px）
let touchStartX = 0;
let touchStartY = 0;
let touchStartTime = 0;

const handleTouchStart = (e) => {
  // 仅在移动端/平板端启用
  if (!isMobile.value && !isTablet.value) return;
  // 抽屉打开时由 ElDrawer 自身处理关闭，不重复监听
  if (drawerVisible.value) return;
  const touch = e.touches[0];
  touchStartX = touch.clientX;
  touchStartY = touch.clientY;
  touchStartTime = Date.now();
};

const handleTouchEnd = (e) => {
  if (!isMobile.value && !isTablet.value) return;
  if (drawerVisible.value) return;
  // 起点必须在左边缘检测区域内
  if (touchStartX > EDGE_DETECT_WIDTH) return;

  const touch = e.changedTouches[0];
  const deltaX = touch.clientX - touchStartX;
  const deltaY = Math.abs(touch.clientY - touchStartY);
  const duration = Date.now() - touchStartTime;

  // 水平滑动距离需大于阈值、且大于垂直滑动、时长在合理范围（< 500ms）
  if (deltaX > EDGE_SWIPE_THRESHOLD && deltaX > deltaY * 1.5 && duration < 500) {
    drawerVisible.value = true;
  }
};

onMounted(() => {
  if (isMobileOrTablet.value) {
    disableDoubleTapZoom();
  }
  // iOS 左边缘为 Safari 返回手势，不再注册边缘滑开菜单，避免冲突
  if (detectIOS()) return;
  document.addEventListener('touchstart', handleTouchStart, { passive: true });
  document.addEventListener('touchend', handleTouchEnd, { passive: true });
});

onUnmounted(() => {
  document.removeEventListener('touchstart', handleTouchStart);
  document.removeEventListener('touchend', handleTouchEnd);
  document.body.classList.remove('drawer-open-scroll-lock');
  document.body.style.top = '';
});

// useDevice composable 已经处理了窗口大小变化监听
</script>

<style scoped>
.main-container {
  height: 100vh;
  height: calc(var(--vh, 1vh) * 100);
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

/* 移动端抽屉：el-drawer__body 样式见全局 mobile.css（teleport 场景） */

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-lg) var(--spacing-xl);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  background-color: var(--bg-dark);
  position: sticky;
  top: 0;
  z-index: 10;
}

.drawer-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-white);
}

.drawer-close-btn {
  color: var(--text-white);
  min-width: var(--touch-target-size);
  min-height: var(--touch-target-size);
}

.drawer-close-btn:hover {
  color: var(--primary-color);
  background-color: rgba(255, 255, 255, 0.1);
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

  .menu-trigger {
  flex-shrink: 0;
  min-height: 48px;
  min-width: 72px;
  padding: 0 var(--spacing-md);
  font-weight: var(--font-weight-semibold);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-light);
  touch-action: manipulation;
  display: none;
  align-items: center;
  gap: var(--spacing-xs);
  z-index: 2;
}

/* 移动端/平板：CSS 控制显示，不依赖 JS v-if，避免首屏或检测异常时菜单消失 */
@media (max-width: 1024px) {
  .menu-trigger {
    display: inline-flex !important;
  }
}

.menu-trigger-icon {
  font-size: var(--font-size-xl);
}

.menu-trigger-label {
  font-size: var(--font-size-base);
  line-height: 1;
}

.menu-trigger:active {
  opacity: 0.85;
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
  position: relative;
}

.route-progress-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  z-index: 10;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--primary-color) 50%,
    transparent 100%
  );
  background-size: 200% 100%;
  animation: route-progress-slide 1s linear infinite;
  pointer-events: none;
}

@keyframes route-progress-slide {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
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

  /* 移动端抽屉优化 */
  .drawer-header {
    padding: var(--spacing-md) var(--spacing-lg);
  }

  .drawer-title {
    font-size: var(--font-size-base);
  }

  /* 移动端头部优化 */
  .header-content {
    flex-wrap: nowrap;
    gap: var(--spacing-sm);
  }

  .header-left {
    flex: 1;
    min-width: 0;
    overflow: visible;
  }

  .header-title {
    font-size: var(--font-size-base);
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .header-right {
    flex-shrink: 0;
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