/**
 * TB 搜索数据表格合计行
 */
import { formatTbCurrency } from '../utils/currencyFormat';

const SUM_NUMERIC_PROPS = [
  'redirects',
  'searches',
  'monetized',
  'clicks',
  'revenue',
  'revenue_before_deduct',
  'rpm',
  'rpm_before_deduct'
];

const CURRENCY_PROPS = ['revenue', 'revenue_before_deduct', 'rpm', 'rpm_before_deduct'];

export function useTbSearchTableFormat() {
  const formatCurrency = formatTbCurrency;

  const getSummaries = (param) => {
    const { columns, data } = param;
    if (!Array.isArray(data)) {
      return columns.map(() => '');
    }

    const sums = [];
    columns.forEach((column, index) => {
      if (index === 0) {
        sums[index] = '合计';
        return;
      }
      const prop = column.property;
      if (!SUM_NUMERIC_PROPS.includes(prop)) {
        sums[index] = '';
        return;
      }
      const values = data
        .map((item) => {
          const value = item?.[prop];
          return value !== null && value !== undefined ? Number(value) : 0;
        })
        .filter((val) => !Number.isNaN(val));

      if (values.length > 0) {
        const sum = values.reduce((prev, curr) => prev + curr, 0);
        sums[index] = CURRENCY_PROPS.includes(prop) ? formatTbCurrency(sum) : sum;
      } else {
        sums[index] = '';
      }
    });
    return sums;
  };

  return { formatCurrency, getSummaries };
}
