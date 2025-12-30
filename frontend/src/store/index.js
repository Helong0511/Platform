import { createPinia, defineStore } from 'pinia';
import axios from 'axios';
import { ElMessage } from 'element-plus';
import router from '../router';
import { initTimezone } from '../utils/dateFormat';
import { logger } from '../utils/logger';




const pinia = createPinia();
export default pinia;

// 配置Axios基础URL
axios.defaults.baseURL = '/';
// 设置全局默认timeout（根据设备类型动态设置）
// 检测是否为移动设备
const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
axios.defaults.timeout = isMobileDevice ? 30000 : 15000; // 移动端30秒，桌面端15秒

/**
 * 获取默认路由（根据用户角色和菜单显示情况）
 * @param {Object} userInfo - 用户信息对象
 * @returns {string} 默认路由路径
 */
export const getDefaultRoute = (userInfo) => {
  if (!userInfo) {
    return '/app/dashboard';
  }
  
  const isAdmin = userInfo.role === 'admin';
  const hasPublisher = userInfo.has_publisher === true || userInfo.client?.has_publisher === true;
  
  // 管理员：跳转到数据仪表
  if (isAdmin) {
    return '/app/dashboard';
  }
  
  // 客户用户且有关联渠道：数据仪表和广告数据被隐藏，优先跳转到转化总览
  if (hasPublisher) {
    return '/app/admin/conversion-summary';
  }
  
  // 客户用户但没有关联渠道：显示数据仪表和广告数据，跳转到数据仪表
  return '/app/dashboard';
};

/**
 * 安全清除认证信息
 * 统一处理 token 和 userInfo 的清除，确保状态一致性
 */
export const clearAuthData = () => {
  try {
    sessionStorage.removeItem('userInfo');
    // 注意：HttpOnly cookie 的清除需要由后端在 logout 接口中处理
  } catch (e) {
    logger.warn('清除认证信息时出错:', e);
  }
};

/**
 * 验证 sessionStorage 中的数据完整性
 * 如果 token 存在但 userInfo 不存在或无效，清除所有认证数据
 */
export const validateAuthData = () => {
  try {
    const userInfoStr = sessionStorage.getItem('userInfo');

    // 如果没有 userInfo，说明未登录或会话已过期
    if (!userInfoStr || userInfoStr === 'null' || userInfoStr === 'undefined') {
      return false;
    }

    // 如果 userInfo 存在，尝试解析验证
    try {
      const userInfo = JSON.parse(userInfoStr);
      // 验证 userInfo 是否为有效对象
      if (!userInfo || typeof userInfo !== 'object') {
        logger.warn('userInfo 格式无效，清除认证数据');
        clearAuthData();
        return false;
      }
    } catch (e) {
      logger.warn('解析 userInfo 失败，清除认证数据:', e);
      clearAuthData();
      return false;
    }

    return true;
  } catch (e) {
    logger.error('验证认证数据时出错:', e);
    clearAuthData();
    return false;
  }
};

// 认证Store
export const useAuthStore = defineStore('auth', {
  state: () => {
    // 验证认证数据完整性
    const isValid = validateAuthData();

    // 安全解析用户信息
    let userInfo = {};

    if (isValid) {
      try {
        const userInfoStr = sessionStorage.getItem('userInfo');
        if (userInfoStr) {
          userInfo = JSON.parse(userInfoStr);
        }
      } catch (e) {
        logger.warn('初始化时解析用户信息失败:', e);
        userInfo = {};
      }
    }

    return {
      userInfo: userInfo,
      isAuthenticated: isValid, // 基于 userInfo 的有效性判断
      loading: false,
      error: null
    };
  },
  getters: {
    isAdmin: (state) => state.userInfo.role === 'admin'
  },
  actions: {
    async login(credentials) {
      this.loading = true;
      this.error = null;
      try {
        // 检测是否为移动设备，移动端使用更长的超时时间
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        const timeout = isMobile ? 30000 : 15000; // 移动端30秒，桌面端15秒

        const response = await axios.post('/api/v1/auth/login', new URLSearchParams({
          username: credentials.username,
          password: credentials.password,
          grant_type: 'password'
        }), {
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
          },
          timeout: timeout
        });

        // 安全解构响应数据，防止数据格式错误导致登录失败
        const responseData = response.data || {};

        // 检查响应体格式：如果是错误格式（有 code 字段且 code !== 200），说明是业务错误
        // 这种情况不应该发生（因为错误应该返回非 200 状态码），但为了安全起见还是检查
        if (responseData.code !== undefined && responseData.code !== 200) {
          const errorMsg = responseData.detail || responseData.message || '登录失败';
          const error = new Error(errorMsg);
          error.response = {
            status: response.status,
            data: responseData
          };
          throw error;
        }

        // 正常响应格式：{access_token, token_type, user}
        // 注意：token 已经过 set-cookie 设置到 HttpOnly cookie 中
        const user_info = responseData.user;

        // 验证响应数据完整性
        if (!user_info) {
          throw new Error('登录响应数据格式错误：缺少用户信息');
        }

        // 只保存用户信息到sessionStorage (token 存储在 cookie 中)
        sessionStorage.setItem('userInfo', JSON.stringify(user_info));

        // 更新状态
        this.userInfo = user_info;
        this.isAuthenticated = true;

        ElMessage.success('登录成功');

        // 登录成功后初始化时区配置
        initTimezone().catch(() => {
          // 静默处理错误，使用默认值
        });

        // 根据用户角色和菜单显示情况跳转到合适的页面
        // 注意：路由守卫会检查token，所以这里直接跳转即可
        const defaultRoute = getDefaultRoute(user_info);
        router.push(defaultRoute).catch(err => {
          // 忽略重复导航的错误（Vue Router 的特性）
          if (err.name !== 'NavigationDuplicated') {
            // 生产环境可以记录到错误监控服务
            // 路由跳转失败已由路由系统处理
          }
        });
        return true;
      } catch (err) {
        // 处理错误信息
        let errorMsg = '登录失败';

        if (err.response) {
          // 后端返回的错误
          const status = err.response.status;
          const detail = err.response.data?.detail || err.response.data?.message;

          // 403 错误通常是权限问题（如客户被禁用、用户被禁用等）
          if (status === 403) {
            errorMsg = detail || '禁止登录，请联系管理员';
          } else if (status === 401) {
            errorMsg = detail || '用户名或密码不正确';
          } else {
            errorMsg = detail || '登录失败';
          }
        } else if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
          // 超时错误
          const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
          errorMsg = isMobile
            ? '网络连接超时，请检查网络连接或稍后重试'
            : '请求超时，请检查网络连接';
        } else if (err.message) {
          // 其他错误（包括响应数据格式错误）
          // 检查是否是权限相关的错误消息
          if (err.message.includes('禁止登录') || err.message.includes('已被禁用')) {
            errorMsg = err.message;
          } else {
            // 对于其他错误，使用通用提示
            errorMsg = '登录失败，请检查用户名和密码';
          }
        }

        this.error = errorMsg;
        // 错误消息已在axios拦截器中显示，这里不再重复显示
        // 但如果拦截器没有处理（_handled标记），则显示
        if (!err._handled) {
          ElMessage.error(errorMsg);
        }
        return false;
      } finally {
        this.loading = false;
      }
    },
    async logout() {
      // ====== 调用后端API记录退出登录日志 ======
      // 注意：即使API调用失败，也要继续清除本地状态
      try {
        const { logout } = await import('../api/user');
        await logout();
      } catch (error) {
        // API调用失败不影响退出登录流程（可能是token已过期）
        // 静默处理，不显示错误消息
      }

      // ====== 清除会话存储 ======
      // 清除token和用户信息，确保下次访问需要重新登录
      clearAuthData();

      // ====== 重置Store状态 ======
      // 清空所有认证相关的状态
      this.userInfo = {};
      this.isAuthenticated = false;

      // ====== 跳转到登录页 ======
      // 重定向到登录页面
      router.push('/login').catch(err => {
        // 忽略重复导航的错误（路由错误已由路由系统处理）
        if (err.name !== 'NavigationDuplicated') {
          // 路由跳转失败已由路由系统处理，无需额外日志
        }
      });

      ElMessage.success('已退出登录');
    },
    checkAuth() {
      // 先验证认证数据完整性
      const isValid = validateAuthData();

      // 检查会话存储中的token（如果数据有效）
      // 认证 token 现在由浏览器通过 HttpOnly Cookie 自动处理
      // 不再需要手动从 sessionStorage 提取并添加到 Header
      // 安全解析用户信息
      if (isValid) {
        try {
          const userInfoStr = sessionStorage.getItem('userInfo');
          if (userInfoStr) {
            this.userInfo = JSON.parse(userInfoStr);
          } else {
            // 如果userInfo不存在，清除所有认证数据
            clearAuthData();
            this.userInfo = {};
            this.isAuthenticated = false;
            return false;
          }
        } catch (e) {
          // JSON解析失败，清除无效数据
          logger.warn('checkAuth时解析用户信息失败，清除无效数据:', e);
          clearAuthData();
          this.userInfo = {};
          this.isAuthenticated = false;
          return false;
        }
        this.isAuthenticated = true;
        // 注意：系统使用 HttpOnly Cookie，axios 会自动携带认证信息，不需要手动设置 Authorization header
      } else {
        // 如果数据无效，确保状态一致
        this.userInfo = {};
        this.isAuthenticated = false;
        // 注意：系统使用 HttpOnly Cookie，不需要手动删除 Authorization header
      }
      return this.isAuthenticated;
    },
    async fetchUserInfo() {
      // 检查是否已认证（系统使用 HttpOnly Cookie，不需要检查 token）
      if (!this.isAuthenticated) return;

      this.loading = true;
      try {
        const response = await axios.get('/api/v1/users/me');
        // 使用统一的响应处理
        const normalized = response.data?.code === 200
          ? response.data.data
          : (response.data?.data || response.data);
        this.userInfo = normalized || {};
        sessionStorage.setItem('userInfo', JSON.stringify(this.userInfo));
      } catch (err) {
        // 如果是401错误，说明token无效，清除认证信息
        // 但不要在登录页显示错误信息
        if (err.response?.status === 401) {
          // 清除认证信息
          clearAuthData();
          this.userInfo = {};
          this.isAuthenticated = false;

          // 只在非登录页显示错误信息
          if (window.location.pathname !== '/login') {
            ElMessage.error('会话已过期，请重新登录');
            // 跳转到登录页
            router.push('/login').catch(() => { });
          }
        } else {
          // 其他错误，正常显示
          this.logout();
          if (window.location.pathname !== '/login') {
            ElMessage.error('获取用户信息失败，请重新登录');
          }
        }
      } finally {
        this.loading = false;
      }
    }
  }
});

