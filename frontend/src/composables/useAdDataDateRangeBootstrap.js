/**
 * 广告数据页日期范围初始化：默认本月，无数据时自动扩大到全部可查范围
 * @file composables/useAdDataDateRangeBootstrap.js
 */
import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getAdDataDateRange } from '../api/ad-data';
import {
  getDefaultMonthDateRange,
  isSameDateRange,
  resolveInitialAdDataDateRange
} from '../utils/dateRangeFormat';

/**
 * @param {Object} options
 * @param {import('vue').Ref} options.searchForm
 * @param {import('vue').ComputedRef<boolean>} options.isAdmin
 * @param {import('vue').Ref} options.pagination
 * @param {() => Promise<void>} options.refetch
 * @param {() => Promise<void>} [options.onDateRangeChanged] 日期被程序改写后刷新筛选项
 */
export function useAdDataDateRangeBootstrap({ searchForm, isAdmin, pagination, refetch, onDateRangeChanged }) {
  const hasAutoExpandedDateRange = ref(false);

  const getClientIdForDateRange = () => {
    if (isAdmin.value && searchForm.value.clientId) {
      return searchForm.value.clientId;
    }
    return null;
  };

  const fetchAvailableDateRange = async () =>
    getAdDataDateRange(getClientIdForDateRange());

  /** 未选手动日期时，根据库内 min/max 设置初始范围 */
  const ensureInitialDateRange = async () => {
    if (searchForm.value.dateRange?.length === 2) {
      return;
    }
    try {
      const available = await fetchAvailableDateRange();
      if (available?.min_date && available?.max_date) {
        searchForm.value.dateRange = resolveInitialAdDataDateRange(
          available.min_date,
          available.max_date
        );
      } else {
        searchForm.value.dateRange = getDefaultMonthDateRange();
      }
    } catch {
      searchForm.value.dateRange = getDefaultMonthDateRange();
    }
  };

  /**
   * 查询结果为空时：若尚未扩大到全量日期，则自动使用 [min_date, max_date] 重查一次
   */
  const handleEmptyWithDateBootstrap = async (response) => {
    if ((response.data?.length ?? 0) > 0 || pagination.value.total > 0) {
      return;
    }

    try {
      const available = await fetchAvailableDateRange();
      const fullRange =
        available?.min_date && available?.max_date
          ? [available.min_date, available.max_date]
          : null;

      if (
        fullRange &&
        !hasAutoExpandedDateRange.value &&
        !isSameDateRange(searchForm.value.dateRange, fullRange)
      ) {
        hasAutoExpandedDateRange.value = true;
        searchForm.value.dateRange = fullRange;
        pagination.value.current = 1;
        if (onDateRangeChanged) {
          await onDateRangeChanged();
        }
        await refetch();
        return;
      }

      if (fullRange) {
        ElMessage.info({
          message: `当前筛选条件下暂无数据。可查数据日期：${fullRange[0]} 至 ${fullRange[1]}，请调整日期或统计维度后重试。`,
          duration: 10000,
          showClose: true
        });
      } else {
        ElMessage.warning({
          message:
            '暂无数据。可能原因：1) 请调整日期范围；2) 产品未激活；3) 当前统计维度下无匹配数据；4) 没有查看权限。',
          duration: 8000,
          showClose: true
        });
      }
    } catch {
      ElMessage.warning({
        message: '暂无数据，请调整日期范围或统计维度后重试。',
        duration: 6000,
        showClose: true
      });
    }
  };

  const resetDateBootstrap = () => {
    hasAutoExpandedDateRange.value = false;
  };

  return {
    ensureInitialDateRange,
    handleEmptyWithDateBootstrap,
    resetDateBootstrap
  };
}
