import { ref, reactive } from 'vue';

/**
 * 分页和筛选 Composable
 * 处理分页状态和筛选条件
 */
export function usePagination(initialSize = 10) {
  const pagination = ref({
    current: 1,
    size: initialSize,
    total: 0
  });

  // 筛选表单
  const searchForm = reactive({
    company_name: '',
    is_active: null,
    dateRange: []
  });

  /**
   * 重置筛选条件
   */
  const resetFilter = () => {
    searchForm.company_name = '';
    searchForm.is_active = null;
    searchForm.dateRange = [];
    pagination.value.current = 1;
  };

  /**
   * 分页大小变更
   * @param {number} val - 新的分页大小
   */
  const handleSizeChange = (val) => {
    pagination.value.size = val;
    pagination.value.current = 1;
  };

  /**
   * 当前页变更
   * @param {number} val - 新的页码
   */
  const handleCurrentChange = (val) => {
    pagination.value.current = val;
  };

  /**
   * 获取查询参数
   * @returns {Object} 查询参数对象
   */
  const getQueryParams = () => ({
    page: pagination.value.current,
    page_size: pagination.value.size,
    company_name: searchForm.company_name || undefined,
    is_active: searchForm.is_active !== null ? searchForm.is_active : undefined
  });

  return {
    pagination,
    searchForm,
    resetFilter,
    handleSizeChange,
    handleCurrentChange,
    getQueryParams
  };
}

