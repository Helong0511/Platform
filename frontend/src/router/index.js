import { createRouter, createWebHistory } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useAuthStore, validateAuthData, clearAuthData } from '../store';
import { logger } from '../utils/logger';

// 懒加载组件 - 使用动态导入实现代码分割
// 添加错误处理，确保模块加载失败时能够重试或显示友好错误
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
const ShortLinkManagement = createAsyncComponent(() => import(/* webpackChunkName: "short-link-management" */ '../views/admin/ShortLinkManagement.vue'), 'ShortLinkManagement');
const AdvertiserManagement = createAsyncComponent(() => import(/* webpackChunkName: "advertiser-management" */ '../views/admin/AdvertiserManagement.vue'), 'AdvertiserManagement');
const PublisherManagement = createAsyncComponent(() => import(/* webpackChunkName: "publisher-management" */ '../views/admin/PublisherManagement.vue'), 'PublisherManagement');
const OfferManagement = createAsyncComponent(() => import(/* webpackChunkName: "offer-management" */ '../views/admin/OfferManagement.vue'), 'OfferManagement');
const CapManagement = createAsyncComponent(() => import(/* webpackChunkName: "cap-management" */ '../views/admin/CapManagement.vue'), 'CapManagement');
const DiscountManagement = createAsyncComponent(() => import(/* webpackChunkName: "discount-management" */ '../views/admin/DiscountManagement.vue'), 'DiscountManagement');
const AdvertiserTest = createAsyncComponent(() => import(/* webpackChunkName: "advertiser-test" */ '../views/admin/AdvertiserTest.vue'), 'AdvertiserTest');
const AffiliateTest = createAsyncComponent(() => import(/* webpackChunkName: "affiliate-test" */ '../views/admin/AffiliateTest.vue'), 'AffiliateTest');
const ConversionSummary = createAsyncComponent(() => import(/* webpackChunkName: "conversion-summary" */ '../views/admin/ConversionSummary.vue'), 'ConversionSummary');
const ConversionLog = createAsyncComponent(() => import(/* webpackChunkName: "conversion-log" */ '../views/admin/ConversionLog.vue'), 'ConversionLog');
const ClientUserManagement = createAsyncComponent(() => import(/* webpackChunkName: "client-user-management" */ '../views/client/ClientUserManagement.vue'), 'ClientUserManagement');
const ApiDocumentation = createAsyncComponent(() => import(/* webpackChunkName: "api-documentation" */ '../views/ApiDocumentation.vue'), 'ApiDocumentation');
const MainLayout = createAsyncComponent(() => import(/* webpackChunkName: "layout" */ '../components/Layout/MainLayout.vue'), 'MainLayout');

// 路由规则
const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', name: 'Login', component: Login, meta: { requiresAuth: false } },
  {
    path: '/app',
    component: MainLayout,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/app/dashboard' },
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
        path: 'admin/postback',
        name: 'PostbackManagement',
        component: PostbackManagement,
        meta: { requiresAdmin: true }
      },
      {
        path: 'admin/short-links',
        name: 'ShortLinkManagement',
        component: ShortLinkManagement,
        meta: { requiresAdmin: false }
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
        meta: { requiresAdmin: true }
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
        path: 'admin/advertiser-test',
        name: 'AdvertiserTest',
        component: AdvertiserTest,
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
        meta: { requiresAdmin: false }
      },
      {
        path: 'admin/conversion-log',
        name: 'ConversionLog',
        component: ConversionLog,
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

// 路由守卫
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
      return next('/app/dashboard');
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
        ElMessage.error('没有权限访问该页面');
        // 如果是从其他页面跳转过来的，返回原页面；否则跳转到仪表盘
        const fallbackPath = from.path && from.path !== '/login' && from.path.startsWith('/app')
          ? from.path
          : '/app/dashboard';
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