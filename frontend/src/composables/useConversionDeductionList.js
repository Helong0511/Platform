import { reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  getDeductionConfigs,
  deleteDeductionConfig,
  updateDeductionConfigStatus,
  batchUpdateDeductionConfigStatus,
  batchDeleteDeductionConfigs,
} from '../api/deduction';
import { getAdvertisers } from '../api/advertiser';
import { logger } from '../utils/logger';

/**
 * 转化扣减配置列表、筛选、分页与批量操作。
 */
export function useConversionDeductionList() {
  const loading = ref(false);
  const tableData = ref([]);
  const selectedConfigs = ref([]);
  const advertiserList = ref([]);

  const searchForm = reactive({
    keyword: '',
    level: null,
    advertiser_id: null,
    is_active: null,
  });

  const pagination = reactive({
    page: 1,
    page_size: 20,
    total: 0,
  });

  const loadAdvertisers = async () => {
    try {
      let allAdvertisers = [];
      let page = 1;
      const pageSize = 100;
      let hasMore = true;

      while (hasMore) {
        const response = await getAdvertisers({ page, page_size: pageSize });
        const items = response.data || [];
        allAdvertisers = allAdvertisers.concat(items);
        const total = response.total || 0;
        hasMore = allAdvertisers.length < total && items.length > 0;
        page += 1;
      }

      advertiserList.value = allAdvertisers;
    } catch (error) {
      logger.error('加载广告主列表失败:', error);
      ElMessage.error(`加载广告主列表失败：${error.message || '未知错误'}`);
    }
  };

  const fetchData = async () => {
    loading.value = true;
    try {
      const params = {
        page: pagination.page,
        page_size: pagination.page_size,
        ...searchForm,
      };
      const response = await getDeductionConfigs(params);
      tableData.value = response.data || [];
      pagination.total = response.total || 0;
    } catch (error) {
      logger.error('获取配置列表失败:', error);
      ElMessage.error(`获取配置列表失败：${error.message || '未知错误'}`);
    } finally {
      loading.value = false;
    }
  };

  const handleSearch = () => {
    pagination.page = 1;
    fetchData();
  };

  const handleReset = () => {
    searchForm.keyword = '';
    searchForm.level = null;
    searchForm.is_active = null;
    searchForm.advertiser_id = null;
    handleSearch();
  };

  const handleStatusChange = async (row) => {
    try {
      await updateDeductionConfigStatus(row.id, row.is_active);
      ElMessage.success('状态更新成功');
    } catch (error) {
      row.is_active = !row.is_active;
      logger.error('状态更新失败:', error);
      ElMessage.error(`状态更新失败：${error.message || '未知错误'}`);
    }
  };

  const handleSelectionChange = (selection) => {
    selectedConfigs.value = selection;
  };

  const runBatch = async ({ emptyMsg, confirmTitle, confirmText, request, successLabel }) => {
    if (selectedConfigs.value.length === 0) {
      ElMessage.warning(emptyMsg);
      return;
    }
    try {
      await ElMessageBox.confirm(confirmText, confirmTitle, {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      });
      loading.value = true;
      const configIds = selectedConfigs.value.map((item) => item.id);
      const response = await request(configIds);
      const count =
        response.updated_count ?? response.deleted_count ?? configIds.length;
      ElMessage.success(`成功${successLabel} ${count} 个配置`);
      selectedConfigs.value = [];
      await fetchData();
    } catch (error) {
      if (error !== 'cancel') {
        logger.error(`${successLabel}失败:`, error);
        ElMessage.error(`${successLabel}失败：${error.message || '未知错误'}`);
      }
    } finally {
      loading.value = false;
    }
  };

  const handleBatchEnable = () =>
    runBatch({
      emptyMsg: '请先选择要启用的配置',
      confirmTitle: '确认批量启用',
      confirmText: `确定要启用选中的 ${selectedConfigs.value.length} 个配置吗？`,
      request: (configIds) =>
        batchUpdateDeductionConfigStatus({ config_ids: configIds, is_active: true }),
      successLabel: '启用',
    });

  const handleBatchDisable = () =>
    runBatch({
      emptyMsg: '请先选择要禁用的配置',
      confirmTitle: '确认批量禁用',
      confirmText: `确定要禁用选中的 ${selectedConfigs.value.length} 个配置吗？`,
      request: (configIds) =>
        batchUpdateDeductionConfigStatus({ config_ids: configIds, is_active: false }),
      successLabel: '禁用',
    });

  const handleBatchDelete = () =>
    runBatch({
      emptyMsg: '请先选择要删除的配置',
      confirmTitle: '确认批量删除',
      confirmText: `确定要删除选中的 ${selectedConfigs.value.length} 个配置吗？此操作不可恢复！`,
      request: (configIds) => batchDeleteDeductionConfigs({ config_ids: configIds }),
      successLabel: '删除',
    });

  const handleDelete = async (row) => {
    try {
      await ElMessageBox.confirm(`确定要删除配置"${row.target_name}"吗？`, '确认删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      });
      await deleteDeductionConfig(row.id);
      ElMessage.success('删除成功');
      await fetchData();
    } catch (error) {
      if (error !== 'cancel') {
        logger.error('删除失败:', error);
        ElMessage.error(`删除失败：${error.message || '未知错误'}`);
      }
    }
  };

  const handleExport = async () => {
    try {
      loading.value = true;
      const params = new URLSearchParams();
      if (searchForm.keyword) params.append('keyword', searchForm.keyword);
      if (searchForm.level) params.append('level', searchForm.level);
      if (searchForm.is_active !== null && searchForm.is_active !== undefined) {
        params.append('is_active', String(searchForm.is_active));
      }
      if (searchForm.advertiser_id) {
        params.append('advertiser_id', String(searchForm.advertiser_id));
      }
      const url = `/api/v1/conversion-deductions/export?${params.toString()}`;
      window.open(url, '_blank');
      ElMessage.success('导出请求已发送，请稍候...');
    } catch (error) {
      logger.error('导出失败:', error);
      ElMessage.error(`导出失败：${error.message || '未知错误'}`);
    } finally {
      loading.value = false;
    }
  };

  const handlePageChange = (page) => {
    pagination.page = page;
    fetchData();
  };

  const handleSizeChange = (size) => {
    pagination.page_size = Math.min(size, 100);
    pagination.page = 1;
    fetchData();
  };

  const initPage = async () => {
    await loadAdvertisers();
    await fetchData();
  };

  return {
    loading,
    tableData,
    selectedConfigs,
    advertiserList,
    searchForm,
    pagination,
    fetchData,
    handleSearch,
    handleReset,
    handleStatusChange,
    handleSelectionChange,
    handleBatchEnable,
    handleBatchDisable,
    handleBatchDelete,
    handleDelete,
    handleExport,
    handlePageChange,
    handleSizeChange,
    initPage,
  };
}
