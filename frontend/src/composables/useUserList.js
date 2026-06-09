/**
 * 组合式函数 - 用户列表：搜索、分页与批量操作
 * @file composables/useUserList.js
 */
import { ref, reactive, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { getUsers, getUserStats } from '../api/user';

function normalizeClientUser(user) {
  if (user.role !== 'client') {
    return user;
  }
  if (user.api_enabled === undefined || user.api_enabled === null) {
    user.api_enabled = false;
  } else {
    user.api_enabled =
      user.api_enabled === true || user.api_enabled === 1 || user.api_enabled === 'true';
  }
  if (user.password_change_enabled === undefined || user.password_change_enabled === null) {
    user.password_change_enabled = false;
  } else {
    user.password_change_enabled =
      user.password_change_enabled === true ||
      user.password_change_enabled === 1 ||
      user.password_change_enabled === 'true';
  }
  if (!user.client) {
    user.client = {};
  }
  if (user.client && !user.client.id && user.client_id) {
    user.client.id = user.client_id;
  }
  if (user._apiSwitchLoading === undefined) {
    user._apiSwitchLoading = false;
  }
  if (user._passwordSwitchLoading === undefined) {
    user._passwordSwitchLoading = false;
  }
  return user;
}

/**
 * 用户列表、统计与分页（含防抖/去重）。
 */
/**
 * 组合式函数 - 用户列表：搜索、分页与批量操作
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useUserList(authStore, router) {
  // users 响应式状态
  const users = ref([]);
  const loading = ref(false);
  // 统计数据
  const stats = ref(null);
  const pagination = ref({
    current: 1,
    size: 10,
    total: 0,
  });
  // 筛选表单字段
  const searchForm = reactive({
    username: '',
    role: '',
    status: '',
  });

  let fetchUsersPromise = null;
  let fetchStatsPromise = null;
  let fetchUsersTimer = null;

  const fetchUsers = async (immediate = false) => {
    if (fetchUsersPromise && !immediate) {
      return fetchUsersPromise;
    }
    if (!immediate && fetchUsersTimer) {
      clearTimeout(fetchUsersTimer);
    }

    const executeFetch = async () => {
      try {
        loading.value = true;
        if (!authStore.isAuthenticated) {
          ElMessage.warning('登录已过期，请重新登录');
          router.push('/login').catch(() => {
            window.location.href = '/login';
          });
          return;
        }
        const params = {
          page: pagination.value.current,
          page_size: pagination.value.size,
          username: searchForm.username,
          role: searchForm.role,
          status: searchForm.status,
        };
        fetchUsersPromise = getUsers(params);
        const response = await fetchUsersPromise;
        fetchUsersPromise = null;
        users.value = (response.data || []).map(normalizeClientUser);
        pagination.value.total = response.total || response.count || 0;
      } catch (error) {
        if (error.response?.status === 401) {
          loading.value = false;
          return;
        }
        fetchUsersPromise = null;
      } finally {
        loading.value = false;
        fetchUsersPromise = null;
      }
    };

    if (!immediate) {
      return new Promise((resolve) => {
        fetchUsersTimer = setTimeout(() => {
          executeFetch().then(resolve).catch(() => resolve());
        }, 300);
      });
    }
    return executeFetch();
  };

  const fetchStats = async () => {
    if (fetchStatsPromise) {
      return fetchStatsPromise;
    }
    try {
      fetchStatsPromise = getUserStats();
      stats.value = await fetchStatsPromise;
      fetchStatsPromise = null;
    } catch {
      fetchStatsPromise = null;
    }
  };

  const resetFilter = () => {
    searchForm.username = '';
    searchForm.role = '';
    searchForm.status = '';
    pagination.value.current = 1;
    fetchUsers();
  };

  const bindPaginationWatch = (isInitializing) => {
    watch(
      () => [pagination.value.current, pagination.value.size],
      ([newCurrent, newSize], [oldCurrent, oldSize]) => {
        if (isInitializing.value) {
          return;
        }
        if (newCurrent !== oldCurrent && newSize === oldSize) {
          fetchUsers();
        } else if (newSize !== oldSize) {
          if (pagination.value.current !== 1) {
            pagination.value.current = 1;
          } else {
            fetchUsers();
          }
        }
      },
      { flush: 'post' },
    );
  };

  return {
    users,
    loading,
    stats,
    pagination,
    searchForm,
    fetchUsers,
    fetchStats,
    resetFilter,
    bindPaginationWatch,
  };
}
