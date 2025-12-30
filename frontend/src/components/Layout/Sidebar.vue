<template>
  <el-menu
    :default-active="activeMenu"
    class="sidebar-menu"
    :background-color="bgDark"
    :text-color="textWhite"
    :active-text-color="primaryColor"
    :router="false"
    @select="handleMenuSelect"
  >
    <!-- 数据仪表：客户登录且渠道关联了客户时不显示 -->
    <el-menu-item v-if="!hasClientPublisher" index="/app/dashboard">
      <template #icon><PieChart /></template>
      <span>数据仪表</span>
    </el-menu-item>

    <!-- 广告数据：客户登录且渠道关联了客户时不显示 -->
    <el-sub-menu v-if="!hasClientPublisher" index="/app/ad-data">
      <template #title>
        <el-icon><Document /></el-icon>
        <span>广告数据</span>
      </template>
      <el-menu-item index="/app/ad-data/daily-report">
        <span>每日报表</span>
      </el-menu-item>
      <el-menu-item index="/app/ad-data/detail-report">
        <span>详细报表</span>
      </el-menu-item>
      <el-menu-item index="/app/ad-data/tb-search-data">
        <span>TB搜索数据</span>
      </el-menu-item>
    </el-sub-menu>

    <el-menu-item v-if="isAdmin" index="/app/admin/postback">
      <template #icon><Connection /></template>
      <span>Postback管理</span>
    </el-menu-item>

    <el-sub-menu v-if="isAdmin" index="/app/admin/cpl">
      <template #title>
        <el-icon><Box /></el-icon>
        <span>CPL系统</span>
      </template>
      <el-menu-item index="/app/admin/advertisers">
        <span>广告主管理</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/publishers">
        <span>渠道管理</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/offers">
        <span>Offer管理</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/caps">
        <span>Cap管理</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/discounts">
        <span>扣量管理</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/advertiser-test">
        <span>上游测试</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/affiliate-test">
        <span>下游测试</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/conversion-log">
        <span>转化日志</span>
      </el-menu-item>
    </el-sub-menu>

    <!-- 客户用户可见的CPL菜单：如果客户登录但没有关联渠道，则不显示 -->
    <el-menu-item v-if="!isAdmin && hasClientPublisher" index="/app/admin/offers">
      <template #icon><Box /></template>
      <span>Offer管理</span>
    </el-menu-item>

    <!-- 转化总览：如果客户登录但没有关联渠道，则不显示 -->
    <el-menu-item v-if="isAdmin || hasClientPublisher" index="/app/admin/conversion-summary">
      <template #icon><DataAnalysis /></template>
      <span>转化总览</span>
    </el-menu-item>

    <el-menu-item v-if="isAdmin" index="/app/admin/short-links">
      <template #icon><Link /></template>
      <span>短链接管理</span>
    </el-menu-item>

    <el-menu-item v-if="isAdmin" index="/app/admin/import-training">
      <template #icon><Upload /></template>
      <span>训练导入</span>
    </el-menu-item>

    <el-menu-item v-if="isAdmin" index="/app/admin/users">
      <template #icon><UserFilled /></template>
      <span>用户管理</span>
    </el-menu-item>

    <el-menu-item v-if="isAdmin" index="/app/admin/scheduled-tasks">
      <template #icon><Timer /></template>
      <span>定时任务</span>
    </el-menu-item>

    <el-menu-item v-if="isAdmin" index="/app/admin/audit-logs">
      <template #icon><Document /></template>
      <span>操作日志</span>
    </el-menu-item>
    
    <el-menu-item v-if="!isAdmin" index="/app/client/user-management">
      <template #icon><UserFilled /></template>
      <span>用户管理</span>
    </el-menu-item>

    <el-menu-item v-if="!isAdmin && apiEnabled" index="/app/api-documentation">
      <template #icon><Link /></template>
      <span>API对接文档</span>
    </el-menu-item>

  </el-menu>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../../store';
import { ElMenu, ElMenuItem, ElSubMenu, ElIcon } from 'element-plus';
import { PieChart, Document, UserFilled, Upload, Timer, Link, Connection, Box, DataAnalysis } from '@element-plus/icons-vue';

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();
const isAdmin = computed(() => authStore.isAdmin);

// 判断客户是否有关联的渠道（使用后端返回的has_publisher字段）
const hasClientPublisher = computed(() => {
  // 如果是管理员，不隐藏菜单
  if (isAdmin.value) return false;
  // 使用后端返回的has_publisher字段（更准确的判断）
  // 优先使用userInfo.has_publisher，如果没有则使用client.has_publisher作为后备
  return !isAdmin.value && (
    authStore.userInfo?.has_publisher === true || 
    authStore.userInfo?.client?.has_publisher === true
  );
});

// 获取 CSS 变量值
const getCSSVariable = (variableName) => {
  if (typeof window !== 'undefined') {
    return getComputedStyle(document.documentElement).getPropertyValue(variableName).trim();
  }
  return '';
};

const bgDark = ref('#2c3e50');
const textWhite = ref('#ffffff');
const primaryColor = ref('#409eff');

onMounted(() => {
  bgDark.value = getCSSVariable('--bg-dark') || '#2c3e50';
  textWhite.value = getCSSVariable('--text-white') || '#ffffff';
  primaryColor.value = getCSSVariable('--primary-color') || '#409eff';
});
// 检查客户API是否启用（从userInfo中获取api_enabled字段）
const apiEnabled = computed(() => {
  if (isAdmin.value) return false;  // 管理员不显示API菜单
  return authStore.userInfo?.api_enabled === true;  // 客户用户且API已启用
});

// 获取当前激活的菜单项
const activeMenu = computed(() => {
  const path = route.path;
  // 如果是广告数据相关路由，返回对应的菜单项
  if (path.startsWith('/app/ad-data')) {
    return path;
  }
  return path;
});

// 处理菜单选择事件
// 注意：当 el-menu 设置了 router 属性时，它会自动处理路由导航
// 我们只需要处理菜单点击事件（用于移动端关闭抽屉）
const emit = defineEmits(['menu-click']);

const handleMenuSelect = (index) => {
  // 手动处理导航（因为 router 属性可能不工作）
  if (index && typeof index === 'string') {
    try {
      router.push(index).catch(err => {
        // 忽略重复导航错误
        if (err.name !== 'NavigationDuplicated') {
          // 静默处理导航错误
        }
      });
    } catch (e) {
      // 静默处理导航异常
    }
  }
  
  // 触发菜单点击事件（用于移动端关闭抽屉）
  emit('menu-click');
};
</script>

<style scoped>
.sidebar-menu {
  height: 100%;
  width: 100%;
  padding-top: var(--spacing-xl);
  border-right: none;
}

.sidebar-menu :deep(.el-menu-item) {
  padding: 0 var(--spacing-xl) !important;
  min-height: var(--touch-target-size);
  height: auto;
  line-height: var(--line-height-base);
  margin: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--radius-md);
  transition: var(--transition-base);
  display: flex;
  align-items: center;
}

.sidebar-menu :deep(.el-menu-item:hover) {
  background-color: var(--bg-dark-hover);
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background-color: rgba(64, 158, 255, 0.2);
  color: var(--primary-color);
  font-weight: var(--font-weight-semibold);
}

.sidebar-menu :deep(.el-menu-item .el-icon) {
  margin-right: var(--spacing-md);
  font-size: var(--font-size-lg);
}

.sidebar-menu :deep(.el-menu-item span) {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
}

.sidebar-menu :deep(.el-sub-menu) {
  margin: var(--spacing-xs) var(--spacing-md);
}

.sidebar-menu :deep(.el-sub-menu__title) {
  padding: 0 var(--spacing-xl) !important;
  min-height: var(--touch-target-size);
  height: auto;
  line-height: var(--line-height-base);
  border-radius: var(--radius-md);
  transition: var(--transition-base);
  display: flex;
  align-items: center;
}

.sidebar-menu :deep(.el-sub-menu__title:hover) {
  background-color: var(--bg-dark-hover);
}

.sidebar-menu :deep(.el-sub-menu.is-opened .el-sub-menu__title) {
  background-color: rgba(64, 158, 255, 0.1);
}

.sidebar-menu :deep(.el-sub-menu .el-menu-item) {
  padding-left: var(--spacing-xl) !important;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .sidebar-menu {
    padding-top: var(--spacing-md);
    padding-bottom: var(--spacing-lg);
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior: contain;
    flex: 1;
  }
  
  .sidebar-menu :deep(.el-menu-item) {
    min-height: var(--touch-target-size);
    height: auto;
    line-height: var(--line-height-base);
    margin: var(--spacing-xs) var(--spacing-sm);
    padding: var(--spacing-sm) var(--spacing-lg) !important;
    border-radius: var(--radius-md);
    transition: all 0.2s ease;
  }

  .sidebar-menu :deep(.el-menu-item:hover) {
    background-color: var(--bg-dark-hover);
    transform: translateX(4px);
  }

  .sidebar-menu :deep(.el-menu-item.is-active) {
    background-color: rgba(64, 158, 255, 0.25);
    color: var(--primary-color);
    font-weight: var(--font-weight-semibold);
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
  }

  .sidebar-menu :deep(.el-menu-item:active) {
    transform: scale(0.98);
    opacity: 0.9;
  }
  
  .sidebar-menu :deep(.el-menu-item .el-icon) {
    margin-right: var(--spacing-md);
    font-size: var(--font-size-lg);
    flex-shrink: 0;
  }
  
  .sidebar-menu :deep(.el-menu-item span) {
    font-size: var(--font-size-base);
    font-weight: var(--font-weight-medium);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sidebar-menu :deep(.el-sub-menu) {
    margin: var(--spacing-xs) var(--spacing-sm);
  }

  .sidebar-menu :deep(.el-sub-menu__title) {
    padding: var(--spacing-sm) var(--spacing-lg) !important;
    min-height: var(--touch-target-size);
    border-radius: var(--radius-md);
    transition: all 0.2s ease;
  }

  .sidebar-menu :deep(.el-sub-menu__title:hover) {
    background-color: var(--bg-dark-hover);
    transform: translateX(4px);
  }

  .sidebar-menu :deep(.el-sub-menu__title:active) {
    transform: scale(0.98);
    opacity: 0.9;
  }

  .sidebar-menu :deep(.el-sub-menu.is-opened .el-sub-menu__title) {
    background-color: rgba(64, 158, 255, 0.15);
  }

  .sidebar-menu :deep(.el-sub-menu .el-menu-item) {
    padding-left: calc(var(--spacing-xl) + var(--spacing-lg)) !important;
    margin-left: var(--spacing-md);
    margin-right: var(--spacing-md);
  }

  .sidebar-menu :deep(.el-sub-menu .el-menu-item.is-active) {
    background-color: rgba(64, 158, 255, 0.2);
  }
}

/* 触摸设备优化 */
@media (hover: none) and (pointer: coarse) {
  .sidebar-menu :deep(.el-menu-item) {
    min-height: var(--touch-target-size);
  }
  
  .sidebar-menu :deep(.el-menu-item:active) {
    opacity: 0.8;
    background-color: var(--bg-dark-hover);
  }
}
</style>