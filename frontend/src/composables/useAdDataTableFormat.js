/**
 * 广告数据表格字段格式化
 * @file composables/useAdDataTableFormat.js
 *
 * 提供百分比、货币、CPC 合计行等表格列 formatter，区分管理员与客户视图。
 */
import { formatAdTableCurrency, formatAdTableCurrencyAmount } from '../utils/currencyFormat';
import { createPercentTableFormatter } from '../utils/percentFormat';

/**
 * @param {Object} options
 * @param {() => boolean} [options.getIsAdmin] 是否管理员（影响 CPC 合计算法）
 * @param {'weighted'|'sum'} [options.cpcSummaryMode] CPC 合计：weighted=收益/点击，sum=列求和
 */
/**
 * 组合式函数 - 广告数据表格字段格式化
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useAdDataTableFormat(options = {}) {
  const getIsAdmin = options.getIsAdmin ?? (() => false);
  const cpcSummaryMode = options.cpcSummaryMode ?? 'weighted';

  const formatPercentage = createPercentTableFormatter({ asRatio: false });

  const formatCurrency = formatAdTableCurrency;

  const getSummaries = (param) => {
    const { columns, data } = param;
    const sums = [];
    const isAdmin = getIsAdmin();

    columns.forEach((column, index) => {
      if (index === 0) {
        sums[index] = '合计';
        return;
      }

      const prop = column.property;
      const values = data.map((item) => Number(item[prop]) || 0);

      if (!values.every((value) => Number.isNaN(value))) {
        if (prop === 'request_count' || prop === 'match_count' || prop === 'display_count' || prop === 'click_count') {
          sums[index] = values.reduce((prev, curr) => {
            const value = Number(curr);
            return !Number.isNaN(value) ? prev + curr : prev;
          }, 0).toLocaleString();
        } else if (prop === 'cpc') {
          if (cpcSummaryMode === 'sum') {
            const sum = values.reduce((prev, curr) => {
              const value = Number(curr);
              return !Number.isNaN(value) ? prev + curr : prev;
            }, 0);
            sums[index] = formatAdTableCurrencyAmount(sum);
          } else {
            const totalClick = data.reduce((sum, item) => sum + (Number(item.click_count) || 0), 0);
            const totalRevenue = data.reduce((sum, item) => {
              if (isAdmin) {
                return sum + (Number(item.revenue_before_deduct) || 0);
              }
              return sum + (Number(item.revenue_after_deduct) || 0);
            }, 0);
            const cpc = totalClick > 0 ? totalRevenue / totalClick : 0;
            sums[index] = formatAdTableCurrencyAmount(cpc);
          }
        } else if (prop === 'pageviews') {
          sums[index] = values.reduce((prev, curr) => {
            const value = Number(curr);
            return !Number.isNaN(value) ? prev + curr : prev;
          }, 0).toLocaleString();
        } else if (prop === 'revenue_after_deduct' || prop === 'revenue_before_deduct') {
          const sum = values.reduce((prev, curr) => {
            const value = Number(curr);
            return !Number.isNaN(value) ? prev + curr : prev;
          }, 0);
          sums[index] = formatAdTableCurrencyAmount(sum);
        } else if (prop === 'coverage_rate') {
          const totalRequest = data.reduce((sum, item) => sum + (Number(item.request_count) || 0), 0);
          const totalMatch = data.reduce((sum, item) => sum + (Number(item.match_count) || 0), 0);
          const rate = totalRequest > 0 ? (totalMatch / totalRequest) * 100 : 0;
          sums[index] = `${rate.toFixed(2)}%`;
        } else if (prop === 'display_rate') {
          const totalMatch = data.reduce((sum, item) => sum + (Number(item.match_count) || 0), 0);
          const totalDisplay = data.reduce((sum, item) => sum + (Number(item.display_count) || 0), 0);
          const rate = totalMatch > 0 ? (totalDisplay / totalMatch) * 100 : 0;
          sums[index] = `${rate.toFixed(2)}%`;
        } else if (prop === 'click_rate') {
          const totalDisplay = data.reduce((sum, item) => sum + (Number(item.display_count) || 0), 0);
          const totalClick = data.reduce((sum, item) => sum + (Number(item.click_count) || 0), 0);
          const rate = totalDisplay > 0 ? (totalClick / totalDisplay) * 100 : 0;
          sums[index] = `${rate.toFixed(2)}%`;
        } else if (prop === 'viewability_rate') {
          let totalWeighted = 0;
          let totalWeight = 0;
          data.forEach((item) => {
            const viewabilityRate = Number(item.viewability_rate) || 0;
            const clickCount = Number(item.click_count) || 0;
            if (viewabilityRate > 0 && clickCount > 0) {
              totalWeighted += viewabilityRate * clickCount;
              totalWeight += clickCount;
            }
          });
          const rate = totalWeight > 0 ? totalWeighted / totalWeight : 0;
          sums[index] = `${rate.toFixed(2)}%`;
        } else if (prop === 'ecpm_after_deduct') {
          const totalDisplay = data.reduce((sum, item) => sum + (Number(item.display_count) || 0), 0);
          const totalRevenue = data.reduce((sum, item) => sum + (Number(item.revenue_after_deduct) || 0), 0);
          const ecpm = totalDisplay > 0 ? (totalRevenue / totalDisplay) * 1000 : 0;
          sums[index] = formatAdTableCurrencyAmount(ecpm);
        } else if (prop === 'ecpm_before_deduct') {
          const totalDisplay = data.reduce((sum, item) => sum + (Number(item.display_count) || 0), 0);
          const totalRevenue = data.reduce((sum, item) => sum + (Number(item.revenue_before_deduct) || 0), 0);
          const ecpm = totalDisplay > 0 ? (totalRevenue / totalDisplay) * 1000 : 0;
          sums[index] = formatAdTableCurrencyAmount(ecpm);
        } else {
          sums[index] = '';
        }
      } else {
        sums[index] = '';
      }
    });

    return sums;
  };

  return {
    formatPercentage,
    formatCurrency,
    getSummaries
  };
}
