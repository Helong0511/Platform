/**
 * 组合式函数 - 渠道列表数据
 * @file composables/usePublisherList.js
 */
import { reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getPublishers } from '../api/publisher';
import { logger } from '../utils/logger';

/**
 * 组合式函数 - 渠道列表数据
 * @returns {Object} 响应式状态与业务操作方法
 */
export function usePublisherList() {
  // 数据加载中
  const loading = ref(false);
  const searchKeyword = ref('');
  // 按激活状态筛选
  const filterActive = ref(null);
  const pagination = reactive({
    page: 1,
    pageSize: 20,
    total: 0,
  });
  // 表格当前页数据
  const tableData = ref([]);

  const loadData = async () => {
    loading.value = true;
    try {
      const params = {
        page: pagination.page,
        page_size: Math.min(pagination.pageSize, 100),
        search: searchKeyword.value || undefined,
        is_active: filterActive.value !== null ? filterActive.value : undefined,
      };
      const response = await getPublishers(params);
      tableData.value = response.data || [];
      pagination.total = response.total || 0;
    } catch (error) {
      logger.error('获取渠道列表失败:', error);
      ElMessage.error('获取数据失败');
    } finally {
      loading.value = false;
    }
  };

  const handleSearch = () => {
    pagination.page = 1;
    loadData();
  };

  const handleReset = () => {
    searchKeyword.value = '';
    filterActive.value = null;
    pagination.page = 1;
    loadData();
  };

  return {
    loading,
    searchKeyword,
    filterActive,
    pagination,
    tableData,
    loadData,
    handleSearch,
    handleReset,
  };
}
