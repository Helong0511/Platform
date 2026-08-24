<!--
  侧边栏导航：按角色显示菜单项
  @file components/Layout/Sidebar.vue
-->
<template>
  <!-- 页面主模板 -->
<el-menu
    :default-active="activeMenu"
    :default-openeds="defaultOpeneds"
    class="sidebar-menu"
    :class="{ 'sidebar-menu--drawer': inDrawer }"
    :background-color="bgDark"
    :text-color="textWhite"
    :active-text-color="primaryColor"
    :router="false"
    @select="handleMenuSelect"
    @open="handleSubMenuOpen"
  >
    <!-- 数据仪表：客户登录且渠道关联了客户时不显示 -->
    <el-menu-item v-if="!hasClientPublisher" index="/app/dashboard" @mouseenter="prefetchMenu('/app/dashboard')">
      <template #icon><PieChart /></template>
      <span>数据仪表</span>
    </el-menu-item>

    <!-- 广告数据：客户登录且渠道关联了客户时不显示 -->
    <el-sub-menu v-if="!hasClientPublisher" index="/app/ad-data">
      <template #title>
        <el-icon><Document /></el-icon>
        <span>广告数据</span>
      </template>
      <el-menu-item
        v-for="item in dailyReportMenuItems"
        :key="item.path"
        :index="item.path"
        @mouseenter="prefetchMenu(item.path)"
      >
        <span>{{ item.label }}</span>
      </el-menu-item>
      <el-menu-item index="/app/ad-data/tb-search-data">
        <span>TB搜索数据</span>
      </el-menu-item>
      <el-menu-item v-if="isAdmin" index="/app/admin/ad-data-rows">
        <span>明细维护</span>
      </el-menu-item>
      <el-menu-item v-if="isAdmin" index="/app/admin/ad-data-health">
        <span>健康巡检</span>
      </el-menu-item>
    </el-sub-menu>

    <el-menu-item v-if="isAdmin" index="/app/admin/postback" @mouseenter="prefetchMenu('/app/admin/postback')">
      <template #icon><Connection /></template>
      <span>Postback管理</span>
    </el-menu-item>
    <el-menu-item v-if="isAdmin" index="/app/admin/postback-ip-whitelist" @mouseenter="prefetchMenu('/app/admin/postback-ip-whitelist')">
      <template #icon><Lock /></template>
      <span>Postback IP白名单</span>
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
      <el-menu-item index="/app/admin/conversion-deductions">
        <span>扣减配置</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/deduction-stats">
        <span>扣减统计</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/deduction-logs">
        <span>扣减日志</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/affiliate-test">
        <span>下游测试</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/click-log">
        <span>短链接访问记录</span>
      </el-menu-item>
    </el-sub-menu>

    <!-- 客户用户可见的CPL菜单：如果客户登录但没有关联渠道，则不显示 -->
    <el-menu-item v-if="!isAdmin && hasClientPublisher" index="/app/admin/offers" @mouseenter="prefetchMenu('/app/admin/offers')">
      <template #icon><Box /></template>
      <span>Offer管理</span>
    </el-menu-item>

    <!-- 转化总览：如果客户登录但没有关联渠道，则不显示 -->
    <el-menu-item v-if="isAdmin || hasClientPublisher" index="/app/admin/conversion-summary" @mouseenter="prefetchMenu('/app/admin/conversion-summary')">
      <template #icon><DataAnalysis /></template>
      <span>转化总览</span>
    </el-menu-item>

    <el-menu-item v-if="isAdmin" index="/app/admin/short-links" @mouseenter="prefetchMenu('/app/admin/short-links')">
      <template #icon><Link /></template>
      <span>短链接管理</span>
    </el-menu-item>

    <el-menu-item v-if="isAdmin" index="/app/admin/import-training" @mouseenter="prefetchMenu('/app/admin/import-training')">
      <template #icon><Upload /></template>
      <span>训练导入</span>
    </el-menu-item>

    <el-menu-item v-if="isAdmin" index="/app/admin/users" @mouseenter="prefetchMenu('/app/admin/users')">
      <template #icon><UserFilled /></template>
      <span>用户管理</span>
    </el-menu-item>

    <el-menu-item v-if="isAdmin" index="/app/admin/products" @mouseenter="prefetchMenu('/app/admin/products')">
      <template #icon><Box /></template>
      <span>产品管理</span>
    </el-menu-item>

    <el-sub-menu v-if="isAdmin" index="/app/admin/system-services">
      <template #title>
        <el-icon><Setting /></el-icon>
        <span>系统服务</span>
      </template>
      <el-menu-item index="/app/admin/scheduled-tasks">
        <span>定时任务</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/gam-scheduler">
        <span>GAM 多账号配置</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/audit-logs">
        <span>操作日志</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/third-party-reports">
        <span>第三方上报日志</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/telegram-notification-config">
        <span>Telegram 通知配置</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/cache">
        <span>缓存管理</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/cloak-management">
        <span>斗篷管理</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/sessions">
        <span>会话管理</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/sensitive-path-probes">
        <span>敏感路径拦截日志</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/countries">
        <span>国家维护</span>
      </el-menu-item>
    </el-sub-menu>

    <!-- 系统监控菜单 -->
    <el-sub-menu v-if="isAdmin" index="submenu-monitoring">
      <template #title>
        <el-icon><DataLine /></el-icon>
        <span>系统监控</span>
      </template>
      <el-menu-item index="/app/admin/monitoring">
        <span>监控仪表盘</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/monitoring/alerts">
        <span>告警管理</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/monitoring/trends">
        <span>趋势分析</span>
      </el-menu-item>
      <el-menu-item index="/app/admin/optimization">
        <span>性能优化</span>
      </el-menu-item>
    </el-sub-menu>
    
    <el-menu-item v-if="!isAdmin" index="/app/client/user-management" @mouseenter="prefetchMenu('/app/client/user-management')">
      <template #icon><UserFilled /></template>
      <span>用户管理</span>
    </el-menu-item>

    <el-menu-item v-if="!isAdmin && apiEnabled" index="/app/api-documentation" @mouseenter="prefetchMenu('/app/api-documentation')">
      <template #icon><Link /></template>
      <span>API对接文档</span>
    </el-menu-item>

  </el-menu>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../../store';
import { ElMenu, ElMenuItem, ElSubMenu, ElIcon } from 'element-plus';
import { PieChart, Document, UserFilled, Upload, Timer, Link, Connection, Box, DataAnalysis, Lock, Bell, DataLine, Setting } from '@element-plus/icons-vue';
import { prefetchRoute, prefetchAllRoutes } from '../../utils/prefetchRoutes';
import { DAILY_REPORT_MENU_ITEMS } from '../../constants/adDataDimension';

const dailyReportMenuItems = DAILY_REPORT_MENU_ITEMS;

defineProps({
  inDrawer: {
    type: Boolean,
    default: false
  }
});

/** 子菜单 group index（须与子项 index 唯一，不可复用路由路径） */
const SUBMENU_GROUP_INDEXES = new Set([
  '/app/ad-data',
  '/app/admin/cpl',
  '/app/admin/system-services',
  'submenu-monitoring'
]);

const CPL_MENU_PATHS = [
  '/app/admin/advertisers',
  '/app/admin/publishers',
  '/app/admin/offers',
  '/app/admin/caps',
  '/app/admin/discounts',
  '/app/admin/conversion-deductions',
  '/app/admin/deduction-stats',
  '/app/admin/deduction-logs',
  '/app/admin/affiliate-test',
  '/app/admin/click-log'
];

const SYSTEM_SERVICE_PATHS = [
  '/app/admin/scheduled-tasks',
  '/app/admin/gam-scheduler',
  '/app/admin/audit-logs',
  '/app/admin/third-party-reports',
  '/app/admin/telegram-notification-config',
  '/app/admin/cache',
  '/app/admin/cloak-management',
  '/app/admin/sessions',
  '/app/admin/sensitive-path-probes',
  '/app/admin/countries'
];

const MONITORING_PATHS = [
  '/app/admin/monitoring',
  '/app/admin/monitoring/alerts',
  '/app/admin/monitoring/trends',
  '/app/admin/optimization'
];

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
  // 登录后空闲预加载各菜单页 chunk，减少首次点击等待（开发/生产均启用）
  prefetchAllRoutes();
  // 预热用户信息缓存，避免首次点菜单时在守卫里等待 /users/me
  authStore.fetchUserInfo({ silent: true, force: false }).catch(() => {});
});
// 检查客户API是否启用（从userInfo中获取api_enabled字段）
const apiEnabled = computed(() => {
  if (isAdmin.value) return false;  // 管理员不显示API菜单
  return authStore.userInfo?.api_enabled === true;  // 客户用户且API已启用
});

// 点击后立即高亮目标菜单，不等待路由守卫与 chunk 加载完成
const pendingMenuPath = ref('');

watch(
  () => route.path,
  (path) => {
    if (!pendingMenuPath.value || pendingMenuPath.value === path) {
      pendingMenuPath.value = '';
    }
  }
);

// 获取当前激活的菜单项
const activeMenu = computed(() => {
  if (pendingMenuPath.value) {
    return pendingMenuPath.value;
  }
  const path = route.path;
  // 如果是广告数据相关路由，返回对应的菜单项
  if (path.startsWith('/app/ad-data')) {
    return path;
  }
  return path;
});

// 根据当前路由自动展开所在子菜单，便于移动端 drawer 内直接看到当前项
const defaultOpeneds = computed(() => {
  const path = route.path;
  const opened = [];

  if (
    path.startsWith('/app/ad-data') ||
    path.startsWith('/app/admin/ad-data')
  ) {
    opened.push('/app/ad-data');
  }
  if (CPL_MENU_PATHS.some((p) => path === p || path.startsWith(`${p}/`))) {
    opened.push('/app/admin/cpl');
  }
  if (SYSTEM_SERVICE_PATHS.some((p) => path === p || path.startsWith(`${p}/`))) {
    opened.push('/app/admin/system-services');
  }
  if (MONITORING_PATHS.some((p) => path === p || path.startsWith(`${p}/`))) {
    opened.push('submenu-monitoring');
  }

  return opened;
});

// 处理菜单选择事件
// 注意：当 el-menu 设置了 router 属性时，它会自动处理路由导航
// 我们只需要处理菜单点击事件（用于移动端关闭抽屉）
const emit = defineEmits(['menu-click']);

const prefetchMenu = (path) => {
  if (path && typeof path === 'string') {
    prefetchRoute(path);
  }
};

const SUBMENU_PREFETCH_PATHS = {
  '/app/ad-data': () => [
    ...dailyReportMenuItems.map((item) => item.path),
    '/app/ad-data/tb-search-data',
    ...(isAdmin.value ? ['/app/admin/ad-data-rows', '/app/admin/ad-data-health'] : [])
  ],
  '/app/admin/cpl': () => [
    '/app/admin/advertisers',
    '/app/admin/publishers',
    '/app/admin/offers',
    '/app/admin/caps',
    '/app/admin/discounts',
    '/app/admin/conversion-deductions',
    '/app/admin/deduction-stats',
    '/app/admin/deduction-logs',
    '/app/admin/affiliate-test',
    '/app/admin/click-log'
  ],
  '/app/admin/system-services': () => [
    '/app/admin/scheduled-tasks',
    '/app/admin/gam-scheduler',
    '/app/admin/audit-logs',
    '/app/admin/third-party-reports',
    '/app/admin/telegram-notification-config',
    '/app/admin/cache',
    '/app/admin/cloak-management',
    '/app/admin/sessions',
    '/app/admin/sensitive-path-probes',
    '/app/admin/countries'
  ],
  'submenu-monitoring': () => [
    '/app/admin/monitoring',
    '/app/admin/monitoring/alerts',
    '/app/admin/monitoring/trends',
    '/app/admin/optimization'
  ]
};

const handleSubMenuOpen = (index) => {
  const resolver = SUBMENU_PREFETCH_PATHS[index];
  if (resolver) {
    resolver().forEach(prefetchMenu);
  }
};

const handleMenuSelect = (index) => {
  if (!index || typeof index !== 'string') {
    return;
  }

  // 子菜单 group index 不应触发导航或关闭 drawer
  if (SUBMENU_GROUP_INDEXES.has(index)) {
    return;
  }

  // 已在当前页：关闭 drawer 但无需重复导航
  if (index === route.path) {
    emit('menu-click');
    return;
  }

  // 叶子菜单项：关闭 drawer 并导航
  emit('menu-click');

  // 立即切换菜单高亮，避免「点了没反应」体感
  pendingMenuPath.value = index;
  prefetchMenu(index);
  router.push(index).catch((err) => {
    pendingMenuPath.value = '';
    if (err.name !== 'NavigationDuplicated') {
      // 静默处理导航错误
    }
  });
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

/* 抽屉内菜单：滚动由外层 drawer-menu-scroll 承担，增大触控区域 */
.sidebar-menu--drawer {
  height: auto;
  min-height: min-content;
  padding-top: var(--spacing-md);
  padding-bottom: var(--spacing-xl);
}

.sidebar-menu--drawer :deep(.el-menu-item),
.sidebar-menu--drawer :deep(.el-sub-menu__title) {
  min-height: 48px;
  padding-top: var(--spacing-sm) !important;
  padding-bottom: var(--spacing-sm) !important;
  touch-action: manipulation;
  -webkit-tap-highlight-color: rgba(255, 255, 255, 0.12);
  cursor: pointer;
}

.sidebar-menu--drawer :deep(.el-menu-item:hover),
.sidebar-menu--drawer :deep(.el-sub-menu__title:hover),
.sidebar-menu--drawer :deep(.el-menu-item:active),
.sidebar-menu--drawer :deep(.el-sub-menu__title:active) {
  transform: none !important;
}

.sidebar-menu--drawer :deep(.el-menu-item span),
.sidebar-menu--drawer :deep(.el-sub-menu__title span) {
  white-space: normal;
  overflow: visible;
  text-overflow: unset;
  line-height: var(--line-height-base);
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

/* 触摸设备优化：禁用 transform，避免 iOS/Android 点击偏移 */
@media (hover: none) and (pointer: coarse) {
  .sidebar-menu :deep(.el-menu-item),
  .sidebar-menu :deep(.el-sub-menu__title) {
    min-height: 48px;
    touch-action: manipulation;
  }
  
  .sidebar-menu :deep(.el-menu-item:hover),
  .sidebar-menu :deep(.el-sub-menu__title:hover),
  .sidebar-menu :deep(.el-menu-item:active),
  .sidebar-menu :deep(.el-sub-menu__title:active) {
    transform: none !important;
    opacity: 0.85;
    background-color: var(--bg-dark-hover);
  }
}
</style>