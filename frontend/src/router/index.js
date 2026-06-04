/**
 * Vue Router 路由配置模块
 * 
 * 功能说明：
 * - 定义应用的所有路由规则
 * - 实现路由懒加载（代码分割）
 * - 实现路由守卫（认证检查、权限检查）
 * - 处理路由错误和重定向
 * 
 * 路由结构：
 * - /login: 登录页（无需认证）
 * - /app: 主应用区域（需要认证）
 *   - /app/dashboard: 仪表盘
 *   - /app/ad-data/*: 广告数据相关页面
 *   - /app/admin/*: 管理员功能页面（需要管理员权限）
 *   - /app/client/*: 客户功能页面
 *   - /app/api-documentation: API文档页面
 * 
 * 权限控制：
 * - requiresAuth: 需要登录才能访问
 * - requiresAdmin: 需要管理员权限才能访问
 * - requiresPublisher: 需要管理员或有关联渠道的客户才能访问
 * 
 * @module router/index
 */

import { createRouter, createWebHistory } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useAuthStore, validateAuthData, clearAuthData, getDefaultRoute } from '../store';
import { logger } from '../utils/logger';

/**
 * 创建异步组件加载器（支持错误处理和重试）
 * 
 * 功能说明：
 * - 使用动态import实现代码分割，减少初始加载体积
 * - 添加错误处理，模块加载失败时自动重试一次
 * - 重试失败后显示友好的错误提示
 * 
 * 工作原理：
 * 1. 首次加载组件时，动态import对应的Vue组件文件
 * 2. 如果加载失败，自动重试一次
 * 3. 重试失败后，显示错误提示并抛出异常
 * 
 * @param {Function} importFn - 动态导入函数，例如 () => import('./views/Login.vue')
 * @param {string} componentName - 组件名称，用于错误日志记录
 * 
 * @returns {Function} 返回一个异步组件加载函数，供Vue Router使用
 * 
 * @example
 * const Login = createAsyncComponent(
 *   () => import('./views/Login.vue'),
 *   'Login'
 * );
 */
const createAsyncComponent = (importFn, componentName) => {
  return () => {
    return importFn().catch(error => {
      logger.error(`Failed to load component: ${componentName}`, error);
      // 尝试重新加载
      return importFn().catch(retryError => {
        logger.error(`Retry failed for component: ${componentName}`, retryError);
        ElMessage.error(`加载页面失败，请刷新页面重试`);
        // 返回一个错误组件或重定向
        throw retryError;
      });
    });
  };
};

const Login = createAsyncComponent(() => import(/* webpackChunkName: "login" */ '../views/Login.vue'), 'Login');
const Dashboard = createAsyncComponent(() => import(/* webpackChunkName: "dashboard" */ '../views/Dashboard.vue'), 'Dashboard');
const AdData = createAsyncComponent(() => import(/* webpackChunkName: "ad-data" */ '../views/AdData.vue'), 'AdData');
const TBSearchData = createAsyncComponent(() => import(/* webpackChunkName: "tb-search-data" */ '../views/ad-data/TBSearchData.vue'), 'TBSearchData');
const DailyReport = createAsyncComponent(() => import(/* webpackChunkName: "daily-report" */ '../views/ad-data/DailyReport.vue'), 'DailyReport');
const MLModelManagement = createAsyncComponent(() => import(/* webpackChunkName: "ml-model" */ '../views/admin/MLModelManagement.vue'), 'MLModelManagement');
const NotFound = createAsyncComponent(() => import(/* webpackChunkName: "not-found" */ '../views/NotFound.vue'), 'NotFound');
const UserManagement = createAsyncComponent(() => import(/* webpackChunkName: "user-management" */ '../views/admin/UserManagement.vue'), 'UserManagement');
const ScheduledTaskManagement = createAsyncComponent(() => import(/* webpackChunkName: "scheduled-task" */ '../views/admin/ScheduledTaskManagement.vue'), 'ScheduledTaskManagement');
const AuditLogManagement = createAsyncComponent(() => import(/* webpackChunkName: "audit-log" */ '../views/admin/AuditLogManagement.vue'), 'AuditLogManagement');
const PostbackManagement = createAsyncComponent(() => import(/* webpackChunkName: "postback-management" */ '../views/admin/PostbackManagement.vue'), 'PostbackManagement');
const PostbackIpWhitelist = createAsyncComponent(() => import(/* webpackChunkName: "postback-ip-whitelist" */ '../views/admin/PostbackIpWhitelist.vue'), 'PostbackIpWhitelist');
const ShortLinkManagement = createAsyncComponent(() => import(/* webpackChunkName: "short-link-management" */ '../views/admin/ShortLinkManagement.vue'), 'ShortLinkManagement');
const AdvertiserManagement = createAsyncComponent(() => import(/* webpackChunkName: "advertiser-management" */ '../views/admin/AdvertiserManagement.vue'), 'AdvertiserManagement');
const PublisherManagement = createAsyncComponent(() => import(/* webpackChunkName: "publisher-management" */ '../views/admin/PublisherManagement.vue'), 'PublisherManagement');
const OfferManagement = createAsyncComponent(() => import(/* webpackChunkName: "offer-management" */ '../views/admin/OfferManagement.vue'), 'OfferManagement');
const CapManagement = createAsyncComponent(() => import(/* webpackChunkName: "cap-management" */ '../views/admin/CapManagement.vue'), 'CapManagement');
const DiscountManagement = createAsyncComponent(() => import(/* webpackChunkName: "discount-management" */ '../views/admin/DiscountManagement.vue'), 'DiscountManagement');
const ConversionDeductionManagement = createAsyncComponent(() => import(/* webpackChunkName: "conversion-deduction-management" */ '../views/admin/ConversionDeductionManagement.vue'), 'ConversionDeductionManagement');
const DeductionStats = createAsyncComponent(() => import(/* webpackChunkName: "deduction-stats" */ '../views/admin/DeductionStats.vue'), 'DeductionStats');
const DeductionLogs = createAsyncComponent(() => import(/* webpackChunkName: "deduction-logs" */ '../views/admin/DeductionLogs.vue'), 'DeductionLogs');
const AffiliateTest = createAsyncComponent(() => import(/* webpackChunkName: "affiliate-test" */ '../views/admin/AffiliateTest.vue'), 'AffiliateTest');
const ConversionSummary = createAsyncComponent(() => import(/* webpackChunkName: "conversion-summary" */ '../views/admin/ConversionSummary.vue'), 'ConversionSummary');
// ConversionLog 已废弃，功能已融合到 PostbackManagement
const ClickLog = createAsyncComponent(() => import(/* webpackChunkName: "click-log" */ '../views/admin/ClickLog.vue'), 'ClickLog');
const SessionManagement = createAsyncComponent(() => import(/* webpackChunkName: "session-management" */ '../views/admin/SessionManagement.vue'), 'SessionManagement');
const TelegramNotificationConfig = createAsyncComponent(() => import(/* webpackChunkName: "telegram-notification-config" */ '../views/admin/TelegramNotificationConfig.vue'), 'TelegramNotificationConfig');
const CacheManagement = createAsyncComponent(() => import(/* webpackChunkName: "cache-management" */ '../views/admin/CacheManagement.vue'), 'CacheManagement');
const ThirdPartyReportManagement = createAsyncComponent(() => import(/* webpackChunkName: "third-party-report" */ '../views/admin/ThirdPartyReportManagement.vue'), 'ThirdPartyReportManagement');
const CloakManagement = createAsyncComponent(() => import(/* webpackChunkName: "cloak-management" */ '../views/admin/CloakManagement.vue'), 'CloakManagement');
const SensitivePathProbeManagement = createAsyncComponent(() => import(/* webpackChunkName: "sensitive-path-probe" */ '../views/admin/SensitivePathProbeManagement.vue'), 'SensitivePathProbeManagement');
const ClientUserManagement = createAsyncComponent(() => import(/* webpackChunkName: "client-user-management" */ '../views/client/ClientUserManagement.vue'), 'ClientUserManagement');
const ApiDocumentation = createAsyncComponent(() => import(/* webpackChunkName: "api-documentation" */ '../views/ApiDocumentation.vue'), 'ApiDocumentation');
const MainLayout = createAsyncComponent(() => import(/* webpackChunkName: "layout" */ '../components/Layout/MainLayout.vue'), 'MainLayout');

/**
 * 路由规则配置
 * 
 * 路由配置说明：
 * - path: 路由路径，支持动态参数和通配符
 * - name: 路由名称，用于编程式导航
 * - component: 路由组件，使用懒加载
 * - meta: 路由元信息
 *   - requiresAuth: 是否需要认证（默认true）
 *   - requiresAdmin: 是否需要管理员权限（默认false）
 * - redirect: 重定向路径
 * - children: 嵌套路由（子路由）
 * 
 * 路由优先级：
 * 1. 精确匹配的路由优先
 * 2. 动态路由次之
 * 3. 通配符路由最后（404页面）
 */
const routes = [
  // 根路径重定向到登录页
  { path: '/', redirect: '/login' },
  
  // 登录页（无需认证）
  { 
    path: '/login', 
    name: 'Login', 
    component: Login, 
    meta: { requiresAuth: false }  // 明确标记无需认证
  },
  {
    path: '/app',
    component: MainLayout,
    meta: { requiresAuth: true },
    children: [
      { 
        path: '', 
        redirect: '/app/dashboard'  // 默认重定向到dashboard，实际跳转由登录逻辑和路由守卫处理
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: Dashboard
      },
      {
        path: 'ad-data',
        redirect: '/app/ad-data/detail-report'
      },
      {
        path: 'ad-data/daily-report',
        name: 'DailyReport',
        component: DailyReport
      },
      {
        path: 'ad-data/detail-report',
        name: 'AdData',
        component: AdData
      },
      {
        path: 'ad-data/tb-search-data',
        name: 'TBSearchData',
        component: TBSearchData
      },
      {
        path: 'admin/users',
        name: 'UserManagement',
        component: UserManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/import-training',
        name: 'ImportTraining',
        component: MLModelManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/scheduled-tasks',
        name: 'ScheduledTaskManagement',
        component: ScheduledTaskManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/audit-logs',
        name: 'AuditLogManagement',
        component: AuditLogManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/third-party-reports',
        name: 'ThirdPartyReportManagement',
        component: ThirdPartyReportManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/postback',
        name: 'PostbackManagement',
        component: PostbackManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/postback-ip-whitelist',
        name: 'PostbackIpWhitelist',
        component: PostbackIpWhitelist,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/short-links',
        name: 'ShortLinkManagement',
        component: ShortLinkManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/advertisers',
        name: 'AdvertiserManagement',
        component: AdvertiserManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/publishers',
        name: 'PublisherManagement',
        component: PublisherManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/offers',
        name: 'OfferManagement',
        component: OfferManagement,
        meta: { requiresPublisher: true }
      },
      {
        path: 'admin/caps',
        name: 'CapManagement',
        component: CapManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/discounts',
        name: 'DiscountManagement',
        component: DiscountManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/conversion-deductions',
        name: 'ConversionDeductionManagement',
        component: ConversionDeductionManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/deduction-stats',
        name: 'DeductionStats',
        component: DeductionStats,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/deduction-logs',
        name: 'DeductionLogs',
        component: DeductionLogs,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/affiliate-test',
        name: 'AffiliateTest',
        component: AffiliateTest,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/conversion-summary',
        name: 'ConversionSummary',
        component: ConversionSummary,
        meta: { requiresPublisher: true }
      },
      {
        path: 'admin/conversion-log',
        redirect: '/app/admin/postback',
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/click-log',
        name: 'ClickLog',
        component: ClickLog,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/sessions',
        name: 'SessionManagement',
        component: SessionManagement,
        meta: { requiresAuth: true }
      },
      {
        path: 'admin/telegram-notification-config',
        name: 'TelegramNotificationConfig',
        component: TelegramNotificationConfig,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/cache',
        name: 'CacheManagement',
        component: CacheManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/cloak-management',
        name: 'CloakManagement',
        component: CloakManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/sensitive-path-probes',
        name: 'SensitivePathProbeManagement',
        component: SensitivePathProbeManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'client/user-management',
        name: 'ClientUserManagement',
        component: ClientUserManagement
      },
      {
        path: 'api-documentation',
        name: 'ApiDocumentation',
        component: ApiDocumentation
      }
    ]
  },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: NotFound }
];

// 创建路由实例
const router = createRouter({
  history: createWebHistory(),
  routes
});

/** 是否允许访问 Offer / 转化总览（与 Sidebar 菜单规则一致） */
function hasPublisherAccess(authStore) {
  if (authStore.isAdmin) return true;
  return authStore.userInfo?.has_publisher === true
    || authStore.userInfo?.client?.has_publisher === true;
}

/**
 * 路由守卫 - 全局前置守卫
 * 
 * 功能说明：
 * 在每次路由跳转前执行，用于：
 * 1. 检查用户认证状态
 * 2. 检查用户权限（管理员权限）
 * 3. 处理未认证用户的重定向
 * 4. 处理已登录用户访问登录页的重定向
 * 
 * 执行流程：
 * 1. 如果是登录页，直接放行
 * 2. 检查路由是否需要认证（requiresAuth）
 * 3. 如果未认证，重定向到登录页
 * 4. 检查路由是否需要管理员权限（requiresAdmin）
 * 5. 如果权限不足，重定向到仪表盘或原页面
 * 6. 所有检查通过，允许访问
 * 
 * @param {Object} to - 目标路由对象
 * @param {Object} from - 来源路由对象
 * @param {Function} next - 路由跳转函数
 *   - next(): 允许访问
 *   - next('/path'): 重定向到指定路径
 *   - next(false): 取消导航
 * 
 * @example
 * // 路由守卫会自动执行，无需手动调用
 * // 当用户访问 /app/dashboard 时：
 * // 1. 检查是否已登录
 * // 2. 如果未登录，重定向到 /login
 * // 3. 如果已登录，允许访问
 */
router.beforeEach((to, from, next) => {
  try {
    // 如果是登录页，直接放行，不执行任何检查
    if (to.path === '/login' || to.path === '/') {
      return next();
    }

    // 先验证认证数据完整性（现在基于 userInfo，初始化时会自动同步）
    const isAuthenticated = validateAuthData();
    const authStore = useAuthStore();

    // ====== 需要认证的路由 ======
    if (to.meta.requiresAuth) {
      // 如果未认证，或者是 store 状态显示未登录
      if (!isAuthenticated || !authStore.isAuthenticated) {
        // 尝试执行一次 checkAuth (如果是因为 store 还没初始化)
        if (isAuthenticated && !authStore.isAuthenticated) {
          authStore.checkAuth();
        }

        // 再次检查
        if (!authStore.isAuthenticated) {
          clearAuthData();
          const shouldShowMessage = to.path !== '/login' &&
            from.path !== '/login' &&
            from.path !== '/' &&
            from.name !== null;
          if (shouldShowMessage) {
            ElMessage.warning('请登录后访问');
          }
          return next('/login');
        }
      }
    }

    // ====== 已登录用户访问登录页 ======
    if (to.path === '/login' && authStore.isAuthenticated) {
      ElMessage.info('您已登录');
      // 根据用户角色和菜单显示情况跳转到合适的页面
      const defaultRoute = getDefaultRoute(authStore.userInfo);
      return next(defaultRoute);
    }

    // ====== 管理员权限检查 ======
    // 检查路由是否需要管理员权限
    if (to.meta.requiresAdmin) {
      // 如果未认证，跳转到登录页（上面已经检查过，这里应该不会执行到）
      if (!authStore.isAuthenticated) {
        clearAuthData();
        const shouldShowMessage = to.path !== '/login' &&
          from.path !== '/login' &&
          from.path !== '/' &&
          from.name !== null;
        if (shouldShowMessage) {
          ElMessage.warning('请先登录');
        }
        return next('/login');
      }

      // 检查管理员权限
      if (!authStore.isAdmin) {
        // 如果是从其他页面跳转过来的，返回原页面；否则跳转到仪表盘
        const fallbackPath = from.path && from.path !== '/login' && from.path.startsWith('/app')
          ? from.path
          : '/app/dashboard';
        return next(fallbackPath);
      }
    }

    // ====== 渠道关联权限检查（Offer / 转化总览） ======
    if (to.meta.requiresPublisher) {
      if (!authStore.isAuthenticated) {
        clearAuthData();
        ElMessage.warning('请先登录');
        return next('/login');
      }

      if (!hasPublisherAccess(authStore)) {
        const fallbackPath = from.path && from.path !== '/login' && from.path.startsWith('/app')
          ? from.path
          : getDefaultRoute(authStore.userInfo);
        ElMessage.warning('无权访问该页面');
        return next(fallbackPath);
      }
    }

    // ====== 允许访问 ======
    next();
  } catch (error) {
    // 路由守卫出错，跳转到登录页
    // logger已在文件顶部导入，直接使用
    logger.error('路由守卫错误:', error);
    clearAuthData();
    if (to.path !== '/login') {
      ElMessage.error('系统错误，请重新登录');
      next('/login');
    } else {
      next();
    }
  }
});

export default router;