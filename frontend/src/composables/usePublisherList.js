import { reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getPublishers } from '../api/publisher';
import { logger } from '../utils/logger';

export function usePublisherList() {
  const loading = ref(false);
  const searchKeyword = ref('');
  const filterActive = ref(null);
  const pagination = reactive({
    page: 1,
    pageSize: 20,
    total: 0,
  });
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
